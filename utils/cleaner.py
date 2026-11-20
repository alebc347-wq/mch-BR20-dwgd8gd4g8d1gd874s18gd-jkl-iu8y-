"""
倉鼠勇者 3.0 — 終極磁碟與記憶體清暫存引擎 (Developer Deep Cleaner)
提供：
1. 分類式深度清理（__pycache__、data 媒體暫存、pip/yt-dlp 快取、系統暫存、SQLite WAL）
2. 記憶體級回收（gc.collect + 過期快取釋放）
3. 磁碟空間分析報告與低空間自動保護（防 Errno 28）
"""

import gc
import os
import shutil
import tempfile
from dataclasses import dataclass, field


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TEMP_DATA_EXTS = {
    ".mp3", ".wav", ".ogg", ".m4a", ".flac",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".log", ".tmp", ".bak", ".swp", ".part",
}

JUNK_FILE_EXTS = {".pyc", ".pyo", ".tmp", ".log", ".bak", ".swp"}
JUNK_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


@dataclass
class CleanupReport:
    freed_bytes: int = 0
    removed_files: int = 0
    removed_dirs: int = 0
    breakdown: dict[str, int] = field(default_factory=dict)
    gc_collected: int = 0
    disk_free_mb: float = 0.0
    disk_total_mb: float = 0.0
    disk_used_pct: float = 0.0

    def add(self, category: str, nbytes: int, files: int = 0, dirs: int = 0):
        self.freed_bytes += max(0, nbytes)
        self.removed_files += files
        self.removed_dirs += dirs
        self.breakdown[category] = self.breakdown.get(category, 0) + max(0, nbytes)

    @staticmethod
    def fmt_size(nbytes: int) -> str:
        if nbytes >= 1024 * 1024:
            return f"{nbytes / (1024 * 1024):.2f} MB"
        if nbytes >= 1024:
            return f"{nbytes / 1024:.1f} KB"
        return f"{nbytes} B"

    def to_summary(self) -> str:
        lines = [
            f"🧹 **終極清暫存完成！** 共釋放 **{self.fmt_size(self.freed_bytes)}**（移除 `{self.removed_files}` 檔、`{self.removed_dirs}` 資料夾，RAM 回收 `{self.gc_collected}` 物件）"
        ]
        non_zero = [(k, v) for k, v in self.breakdown.items() if v > 0]
        if non_zero:
            detail = " • ".join(f"{k}: `{self.fmt_size(v)}`" for k, v in sorted(non_zero, key=lambda x: -x[1]))
            lines.append(f"📊 明細：{detail}")
        if self.disk_total_mb > 0:
            lines.append(
                f"💾 目前磁碟剩餘：**{self.disk_free_mb:.1f} MB** / {self.disk_total_mb:.0f} MB（已用 `{self.disk_used_pct:.1f}%`）"
            )
        return "\n".join(lines)


def _dir_size(path: str) -> tuple[int, int]:
    total = 0
    count = 0
    for r, _, fs in os.walk(path):
        for f in fs:
            fp = os.path.join(r, f)
            try:
                total += os.path.getsize(fp)
                count += 1
            except OSError:
                pass
    return total, count


def get_disk_usage(root: str = ROOT_DIR) -> tuple[float, float, float]:
    """回傳 (free_mb, total_mb, used_pct)"""
    try:
        usage = shutil.disk_usage(root)
        total_mb = usage.total / (1024 * 1024)
        free_mb = usage.free / (1024 * 1024)
        used_pct = (usage.used / usage.total * 100.0) if usage.total else 0.0
        return free_mb, total_mb, used_pct
    except Exception:
        return 0.0, 0.0, 0.0


def get_folder_breakdown(root: str = ROOT_DIR, top_n: int = 6) -> list[tuple[str, int]]:
    """統計專案根目錄各資料夾磁碟佔用 Top N"""
    sizes: list[tuple[str, int]] = []
    try:
        for entry in os.listdir(root):
            full = os.path.join(root, entry)
            if os.path.isdir(full):
                sz, _ = _dir_size(full)
                sizes.append((f"{entry}/", sz))
            elif os.path.isfile(full):
                try:
                    sizes.append((entry, os.path.getsize(full)))
                except OSError:
                    pass
    except Exception:
        pass
    sizes.sort(key=lambda x: -x[1])
    return sizes[:top_n]


def run_sync_cleanup(
    root: str = ROOT_DIR,
    include_system_caches: bool = True,
    remove_update_pack: bool = False,
) -> CleanupReport:
    """同步執行深度磁碟與記憶體清理（可在 CLI、啟動腳本或 asyncio.to_thread 呼叫）"""
    report = CleanupReport()

    # 1. 清理專案內 __pycache__ / .pytest_cache / 殘留暫存檔
    for r, dirs, files in os.walk(root, topdown=False):
        if ".git" in r.split(os.sep):
            continue
        for d in dirs:
            if d in JUNK_DIR_NAMES:
                full = os.path.join(r, d)
                sz, cnt = _dir_size(full)
                try:
                    shutil.rmtree(full, ignore_errors=True)
                    report.add("Python 快取", sz, files=cnt, dirs=1)
                except Exception:
                    pass
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in JUNK_FILE_EXTS:
                fp = os.path.join(r, fname)
                try:
                    sz = os.path.getsize(fp)
                    os.remove(fp)
                    report.add("殘留暫存檔", sz, files=1)
                except OSError:
                    pass

    # 2. 清理 data/ 內暫存媒體與 WAL/SHM（絕對保留 .db 與 .json）
    data_dir = os.path.join(root, "data")
    if os.path.isdir(data_dir):
        for fname in os.listdir(data_dir):
            if fname.endswith((".json", ".db")):
                continue
            fp = os.path.join(data_dir, fname)
            ext = os.path.splitext(fname)[1].lower()
            if os.path.isfile(fp) and (ext in TEMP_DATA_EXTS or fname.endswith((".db-wal", ".db-shm"))):
                try:
                    sz = os.path.getsize(fp)
                    os.remove(fp)
                    report.add("data 暫存媒體", sz, files=1)
                except OSError:
                    pass

    # 3. 清理 scratch/ 與 logs/
    for junk_top in ("scratch", "logs"):
        jpath = os.path.join(root, junk_top)
        if os.path.isdir(jpath):
            sz, cnt = _dir_size(jpath)
            try:
                shutil.rmtree(jpath, ignore_errors=True)
                report.add("工作暫存目錄", sz, files=cnt, dirs=1)
            except Exception:
                pass

    # 4. 可選：清理根目錄舊的 update_pack.zip
    if remove_update_pack:
        up_zip = os.path.join(root, "update_pack.zip")
        if os.path.isfile(up_zip):
            try:
                sz = os.path.getsize(up_zip)
                os.remove(up_zip)
                report.add("舊更新包", sz, files=1)
            except OSError:
                pass

    # 5. 系統 / pip / yt-dlp 快取清理（容器救星）
    if include_system_caches:
        cache_dir = os.path.expanduser("~/.cache")
        if os.path.isdir(cache_dir):
            for sub in ("pip", "yt-dlp", "fontconfig"):
                target = os.path.join(cache_dir, sub)
                if os.path.isdir(target):
                    sz, cnt = _dir_size(target)
                    try:
                        shutil.rmtree(target, ignore_errors=True)
                        report.add(f"{sub} 快取", sz, files=cnt, dirs=1)
                    except Exception:
                        pass

        tmp_dir = tempfile.gettempdir()
        if os.path.isdir(tmp_dir) and tmp_dir != "/":
            try:
                for fname in os.listdir(tmp_dir):
                    if fname.startswith(("tmp", "pip-", "discord-", "hamster-")):
                        fp = os.path.join(tmp_dir, fname)
                        try:
                            if os.path.isfile(fp):
                                sz = os.path.getsize(fp)
                                os.remove(fp)
                                report.add("系統暫存", sz, files=1)
                            elif os.path.isdir(fp):
                                sz, cnt = _dir_size(fp)
                                shutil.rmtree(fp, ignore_errors=True)
                                report.add("系統暫存", sz, files=cnt, dirs=1)
                        except OSError:
                            pass
            except Exception:
                pass

    # 6. 記憶體回收
    report.gc_collected = gc.collect()
    report.disk_free_mb, report.disk_total_mb, report.disk_used_pct = get_disk_usage(root)
    return report


async def run_async_cleanup(
    db_conn=None,
    root: str = ROOT_DIR,
    include_system_caches: bool = True,
    remove_update_pack: bool = False,
) -> CleanupReport:
    """非同步完整清暫存：磁碟 + 系統快取 + SQLite 瘦身 + 記憶體快取回收"""
    import asyncio

    # 先執行 SQLite checkpoint 與增量壓縮（避免鎖定檔案）
    if db_conn is not None:
        try:
            await db_conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            await db_conn.execute("PRAGMA incremental_vacuum;")
            await db_conn.execute("PRAGMA optimize;")
        except Exception:
            pass

    # 清理記憶體級快取
    try:
        from utils.speed_tier import speed_tier
        speed_tier.clear_all()
    except Exception:
        pass

    return await asyncio.to_thread(
        run_sync_cleanup,
        root,
        include_system_caches,
        remove_update_pack,
    )


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", write_through=True)
    rep = run_sync_cleanup(include_system_caches=False)
    print(rep.to_summary())
