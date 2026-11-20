"""
倉鼠勇者 3.0 — 開發者極輕量更新包打包工具 (Update Pack Builder 3.0)
功能：
1. 打包前自動清理 __pycache__ 與暫存垃圾檔
2. 僅打包核心程式碼 (main.py, config.py, requirements.txt, .env.example, cogs/, utils/)
3. 內嵌 manifest.json（版本、時間戳、檔案清單與 SHA-256 校驗碼）確保上傳部署完整無損
"""

import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", write_through=True)

OUTPUT_ZIP = "update_pack.zip"
INCLUDE_FILES = ["main.py", "config.py", "requirements.txt", ".env.example"]
INCLUDE_DIRS = ["cogs", "utils"]
EXCLUDE_EXTS = {".pyc", ".pyo", ".tmp", ".log", ".bak", ".swp", ".zip"}
EXCLUDE_DIRS = {"__pycache__", ".git", ".agents", "data", "tests", "scratch", ".github", ".gemini", ".pytest_cache"}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_pack(clean_first: bool = True) -> str:
    root_dir = os.path.dirname(os.path.abspath(__file__))
    zip_path = os.path.join(root_dir, OUTPUT_ZIP)

    if clean_first:
        try:
            from utils.cleaner import run_sync_cleanup
            run_sync_cleanup(root=root_dir, include_system_caches=False, remove_update_pack=True)
        except Exception:
            pass

    if os.path.exists(zip_path):
        try:
            os.remove(zip_path)
        except OSError:
            pass

    version = "3.0.0"
    try:
        from config import BOT_VERSION
        version = BOT_VERSION
    except Exception:
        pass

    manifest_files: dict[str, str] = {}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        # 1. 頂層核心檔案
        for fname in INCLUDE_FILES:
            fpath = os.path.join(root_dir, fname)
            if os.path.isfile(fpath):
                with open(fpath, "rb") as f:
                    data = f.read()
                z.writestr(fname, data)
                manifest_files[fname] = _sha256_bytes(data)

        # 2. 核心目錄 (cogs/, utils/)
        for dname in INCLUDE_DIRS:
            dir_path = os.path.join(root_dir, dname)
            if not os.path.isdir(dir_path):
                continue
            for root, dirs, files in os.walk(dir_path):
                dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
                for file in sorted(files):
                    if os.path.splitext(file)[1].lower() in EXCLUDE_EXTS or file.startswith("."):
                        continue
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, root_dir).replace("\\", "/")
                    with open(full_path, "rb") as f:
                        data = f.read()
                    z.writestr(rel_path, data)
                    manifest_files[rel_path] = _sha256_bytes(data)

        # 3. 寫入 manifest.json 校驗資訊
        manifest = {
            "version": version,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "file_count": len(manifest_files),
            "files": manifest_files,
        }
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))

    size_kb = os.path.getsize(zip_path) / 1024
    print(f"✅ [倉鼠勇者 {version}] 更新包已生成：{OUTPUT_ZIP}")
    print(f"📦 包含檔案數：{len(manifest_files)} 個 (+ manifest.json)")
    print(f"📊 檔案大小：{size_kb:.2f} KB")
    return zip_path


if __name__ == "__main__":
    build_pack(clean_first="--no-clean" not in sys.argv)
