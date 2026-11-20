"""
倉鼠勇者 3.0 — 開發者中控、極速上傳熱部署與終極清暫存系統
提供：
- /dev panel   : 互動式開發者控制台（清暫存、磁碟分析、熱重載、打包、GitHub 同步）
- /dev clean   : 終極磁碟 + SQLite + RAM 深度清暫存
- /dev disk    : 磁碟剩餘容量與專案各資料夾佔用 Top 6
- /dev reload  : 免重啟熱重載單一或全部 Cogs
- /dev upload  : Discord 直接上傳單一 .py 檔案（自動熱重載）或 .zip 更新包（安全解壓重啟）
- 自動低空間守護 (auto_disk_guard)：每 30 分鐘檢查磁碟空間，低於 150 MB 自動深度清理防 Errno 28
"""

import asyncio
import io
import os
import sys
import zipfile
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import BOT_VERSION, Colors, OWNER_ID
from utils.cleaner import (
    CleanupReport,
    get_disk_usage,
    get_folder_breakdown,
    run_async_cleanup,
)

BYPASS_USER_ID = 1437408048934027274
LOW_DISK_THRESHOLD_MB = 150.0


def _safe_extract_path(base_dir: str, rel_path: str) -> str | None:
    """防範 Zip Slip 路徑穿越，確保所有解壓縮與上傳目標路徑嚴格位於專案根目錄內"""
    norm = os.path.normpath(rel_path).replace("\\", "/")
    if norm.startswith(("/", "..")) or "/../" in f"/{norm}/":
        return None
    abs_base = os.path.abspath(base_dir)
    abs_target = os.path.abspath(os.path.join(abs_base, norm))
    if not (abs_target == abs_base or abs_target.startswith(abs_base + os.sep)):
        return None
    return abs_target


class DevControlPanelView(discord.ui.View):
    """倉鼠勇者 3.0 開發者中控互動面板"""

    def __init__(self, cog: "AutoUpdate"):
        super().__init__(timeout=300)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if await self.cog._is_dev(interaction.user):
            return True
        await interaction.response.send_message("❌ 僅限 Bot 開發者操作此面板。", ephemeral=True)
        return False

    @discord.ui.button(label="🧹 終極清暫存", style=discord.ButtonStyle.success, row=0)
    async def btn_clean(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        report = await self.cog.run_cleanup_report(remove_update_pack=False)
        embed = discord.Embed(
            title="🧹 3.0 終極清暫存報告",
            description=report.to_summary(),
            color=Colors.SUCCESS,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="💾 磁碟佔用分析", style=discord.ButtonStyle.secondary, row=0)
    async def btn_disk(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = self.cog._build_disk_embed()
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="🔄 熱重載全部 Cogs", style=discord.ButtonStyle.primary, row=0)
    async def btn_reload_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        ok_cnt, failed = await self.cog._reload_extensions(None)
        desc = f"✅ 已成功熱重載 **`{ok_cnt}`** 個模組（免重啟生效）。"
        if failed:
            desc += "\n\n⚠️ 失敗項目：\n" + "\n".join(f"• `{name}`: `{err}`" for name, err in failed[:8])
        embed = discord.Embed(
            title="🔄 3.0 熱重載結果",
            description=desc,
            color=Colors.SUCCESS if not failed else Colors.WARNING,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="📦 產生更新包", style=discord.ButtonStyle.secondary, row=1)
    async def btn_pack(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            from build_update_pack import build_pack
            zip_path = await asyncio.to_thread(build_pack, True)
            size_kb = os.path.getsize(zip_path) / 1024
            file = discord.File(zip_path, filename="update_pack.zip")
            embed = discord.Embed(
                title="📦 3.0 超輕量更新包",
                description=f"✅ 已打包完成（`{size_kb:.2f} KB`，內含 SHA-256 `manifest.json`）。\n可直接搭配 `/dev upload` 或 `.apply` 熱套用。",
                color=Colors.PRIMARY,
            )
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 打包失敗：`{e}`", ephemeral=True)

    @discord.ui.button(label="🚀 GitHub 同步更新", style=discord.ButtonStyle.danger, row=1)
    async def btn_sync(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        status_msg = await interaction.followup.send("🚀 正在啟動 GitHub 同步更新流程...", ephemeral=True, wait=True)

        async def update_status(text: str):
            try:
                await status_msg.edit(content=text)
            except Exception:
                pass

        await self.cog.run_update_process(update_status)


class AutoUpdate(commands.Cog):
    """倉鼠勇者 3.0 開發者中控、自動更新、上傳熱部署與終極清暫存系統"""

    dev_group = app_commands.Group(name="dev", description="🛠️ 倉鼠勇者 3.0 開發者專屬工具（清暫存、上傳、熱重載）")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.repo = os.getenv("GITHUB_REPO", "alebc347-wq/mch-BR20-dwgd8gd4g8d1gd874s18gd-jkl-iu8y-")
        self.branch = os.getenv("GITHUB_BRANCH", "main")
        self.token = os.getenv("GITHUB_TOKEN")
        self.auto_disk_guard.start()

    def cog_unload(self):
        self.auto_disk_guard.cancel()

    async def _is_dev(self, user: discord.User | discord.Member) -> bool:
        if user.id == BYPASS_USER_ID or (OWNER_ID and user.id == OWNER_ID):
            return True
        return await self.bot.is_owner(user)

    def cog_check(self, ctx: commands.Context) -> bool:
        """限制只有 Bot 擁有者或 BYPASS ID 能夠使用此 Cog 的前綴指令"""
        return ctx.author.id == BYPASS_USER_ID or ctx.author.id == self.bot.owner_id or (OWNER_ID and ctx.author.id == OWNER_ID)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 自動低空間磁碟守護（防 Wispbyte Errno 28）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @tasks.loop(minutes=30)
    async def auto_disk_guard(self):
        """每 30 分鐘檢查磁碟空間，剩餘低於 150 MB 時自動執行終極清暫存"""
        try:
            free_mb, total_mb, used_pct = get_disk_usage()
            if total_mb > 0 and free_mb < LOW_DISK_THRESHOLD_MB:
                print(f"⚠️ [DiskGuard] 偵測到磁碟空間偏低 ({free_mb:.1f} MB 剩餘 / {used_pct:.1f}% 已用)，自動執行終極清暫存...")
                rep = await self.run_cleanup_report(remove_update_pack=True)
                print(f"✅ [DiskGuard] 自動清理完畢：釋放 {rep.fmt_size(rep.freed_bytes)}，目前剩餘 {rep.disk_free_mb:.1f} MB")
        except Exception as e:
            print(f"⚠️ [DiskGuard] 檢查異常: {e}")

    @auto_disk_guard.before_loop
    async def before_disk_guard(self):
        await self.bot.wait_until_ready()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 核心輔助方法
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def get_current_git_commit(self) -> str:
        """取得本地最新的 Git Commit Hash 與訊息"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "log", "-1", "--oneline",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                return stdout.decode("utf-8", errors="ignore").strip()
        except Exception:
            pass
        return "未知 Version / 非 Git 倉庫"

    async def run_cleanup_report(self, remove_update_pack: bool = False) -> CleanupReport:
        db_conn = getattr(getattr(self.bot, "db", None), "db", None)
        return await run_async_cleanup(
            db_conn=db_conn,
            include_system_caches=True,
            remove_update_pack=remove_update_pack,
        )

    async def run_cleanup(self) -> str:
        """相容舊版介面：執行終極清暫存並回傳摘要字串"""
        report = await self.run_cleanup_report(remove_update_pack=False)
        return report.to_summary()

    def _build_disk_embed(self) -> discord.Embed:
        free_mb, total_mb, used_pct = get_disk_usage()
        breakdown = get_folder_breakdown(top_n=6)
        bar_len = 16
        filled = int(bar_len * min(max(used_pct / 100.0, 0.0), 1.0))
        bar = "█" * filled + "░" * (bar_len - filled)

        lines = [
            f"`[{bar}]` **{used_pct:.1f}%** 已使用",
            f"剩餘空間：**{free_mb:.1f} MB** / 總容量：{total_mb:.0f} MB",
            "",
            "**專案空間佔用 Top 6：**",
        ]
        for name, sz in breakdown:
            lines.append(f"• `{name:<18}` — `{CleanupReport.fmt_size(sz)}`")

        server_id = os.getenv("SERVER_ID", "local")
        embed = discord.Embed(
            title=f"💾 磁碟與空間診斷 ({server_id})",
            description="\n".join(lines),
            color=Colors.SUCCESS if free_mb >= LOW_DISK_THRESHOLD_MB else Colors.ERROR,
        )
        embed.set_footer(text=f"倉鼠勇者 {BOT_VERSION} • 低於 {int(LOW_DISK_THRESHOLD_MB)} MB 將自動觸發清暫存")
        return embed

    async def _reload_extensions(self, cog_name: str | None) -> tuple[int, list[tuple[str, str]]]:
        """熱重載單一或全部已載入的 Cog 模組"""
        targets = (
            [cog_name if cog_name.startswith("cogs.") else f"cogs.{cog_name}"]
            if cog_name
            else list(self.bot.extensions.keys())
        )
        ok_cnt = 0
        failed: list[tuple[str, str]] = []
        for ext in targets:
            try:
                if ext in self.bot.extensions:
                    await self.bot.reload_extension(ext)
                else:
                    await self.bot.load_extension(ext)
                ok_cnt += 1
            except Exception as e:
                failed.append((ext, f"{type(e).__name__}: {e}"))
        return ok_cnt, failed

    def _extract_zip_safely(self, zip_bytes: bytes, skip_assets: bool = False) -> int:
        """安全解壓縮更新包至專案目錄（含防 Zip Slip 與保護 .env / data/）"""
        extracted = 0
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            names = [m.filename for m in z.infolist() if m.filename]
            # 判斷是否為 GitHub zipball (所有檔案都在同一個頂層資料夾內)
            has_single_root = bool(names) and all("/" in n for n in names) and len({n.split("/", 1)[0] for n in names}) == 1

            for member in z.infolist():
                raw = member.filename
                if has_single_root:
                    parts = raw.split("/", 1)
                    if len(parts) < 2 or not parts[1]:
                        continue
                    rel = parts[1]
                else:
                    rel = raw

                rel_norm = rel.replace("\\", "/").lstrip("/")
                if not rel_norm or rel_norm == "manifest.json":
                    continue
                if (
                    rel_norm.startswith((".env", ".git/", ".git", "data/", "tests/"))
                    or rel_norm == "deploy_config.json"
                ):
                    continue
                if skip_assets and rel_norm.endswith((".md", ".txt", ".png", ".jpg", ".webp")):
                    continue

                safe_target = _safe_extract_path(".", rel_norm)
                if not safe_target:
                    continue

                if member.is_dir() or rel_norm.endswith("/"):
                    os.makedirs(safe_target, exist_ok=True)
                else:
                    parent = os.path.dirname(safe_target)
                    if parent:
                        os.makedirs(parent, exist_ok=True)
                    if os.path.exists(safe_target):
                        try:
                            os.remove(safe_target)
                        except OSError:
                            pass
                    with open(safe_target, "wb") as f:
                        f.write(z.read(member))
                    extracted += 1
        return extracted

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # /dev 開發者專屬 Slash 指令群組
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @dev_group.command(name="panel", description="開啟倉鼠勇者 3.0 開發者中控互動面板")
    async def dev_panel(self, interaction: discord.Interaction):
        if not await self._is_dev(interaction.user):
            return await interaction.response.send_message("❌ 僅限 Bot 開發者使用。", ephemeral=True)

        commit_info = await self.get_current_git_commit()
        free_mb, total_mb, used_pct = get_disk_usage()
        server_id = os.getenv("SERVER_ID", "local")
        embed = discord.Embed(
            title=f"🛠️ 倉鼠勇者 {BOT_VERSION} 開發者中控台",
            description=(
                f"🖥️ **節點**：`{server_id}`\n"
                f"🏷️ **Git Commit**：`{commit_info}`\n"
                f"💾 **磁碟剩餘**：`{free_mb:.1f} MB` / `{total_mb:.0f} MB`（已用 `{used_pct:.1f}%`）\n"
                f"🧩 **已載入模組**：`{len(self.bot.extensions)}` 個\n\n"
                "提示：可使用 `/dev upload` 直接上傳 `.py` 單檔即時熱部署，或上傳 `.zip` 更新包自動套用。"
            ),
            color=Colors.PRIMARY,
        )
        await interaction.response.send_message(embed=embed, view=DevControlPanelView(self), ephemeral=True)

    @dev_group.command(name="clean", description="立即執行終極清暫存（磁碟 + SQLite + RAM 快取）")
    @app_commands.describe(remove_pack="是否一併刪除根目錄的 update_pack.zip（預設否）")
    async def dev_clean(self, interaction: discord.Interaction, remove_pack: bool = False):
        if not await self._is_dev(interaction.user):
            return await interaction.response.send_message("❌ 僅限 Bot 開發者使用。", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        report = await self.run_cleanup_report(remove_update_pack=remove_pack)
        embed = discord.Embed(
            title="🧹 3.0 終極清暫存完成",
            description=report.to_summary(),
            color=Colors.SUCCESS,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @dev_group.command(name="disk", description="查看主機磁碟剩餘空間與專案佔用 Top 6")
    async def dev_disk(self, interaction: discord.Interaction):
        if not await self._is_dev(interaction.user):
            return await interaction.response.send_message("❌ 僅限 Bot 開發者使用。", ephemeral=True)
        await interaction.response.send_message(embed=self._build_disk_embed(), ephemeral=True)

    @dev_group.command(name="reload", description="免重啟熱重載單一或全部 Cog 模組")
    @app_commands.describe(cog="模組名稱（例如 general 或 cogs.general；留空則熱重載全部）")
    async def dev_reload(self, interaction: discord.Interaction, cog: str | None = None):
        if not await self._is_dev(interaction.user):
            return await interaction.response.send_message("❌ 僅限 Bot 開發者使用。", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ok_cnt, failed = await self._reload_extensions(cog)
        desc = f"✅ 已成功熱重載 **`{ok_cnt}`** 個模組。"
        if failed:
            desc += "\n\n⚠️ 失敗項目：\n" + "\n".join(f"• `{name}`: `{err}`" for name, err in failed[:10])
        embed = discord.Embed(
            title="🔄 模組熱重載結果",
            description=desc,
            color=Colors.SUCCESS if not failed else Colors.WARNING,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @dev_group.command(name="upload", description="直接上傳 .py 單檔熱部署或 .zip 更新包（免開主機面板）")
    @app_commands.describe(
        file="要上傳的 .py 模組檔或 .zip 更新包",
        target_dir="單檔 .py 目標目錄（預設 cogs，可選 cogs / utils / root）",
        auto_reload="上傳後是否自動熱重載或重啟（預設開啟）",
    )
    @app_commands.choices(target_dir=[
        app_commands.Choice(name="cogs/（功能模組）", value="cogs"),
        app_commands.Choice(name="utils/（核心工具）", value="utils"),
        app_commands.Choice(name="根目錄（main.py / config.py）", value="root"),
    ])
    async def dev_upload(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        target_dir: str = "cogs",
        auto_reload: bool = True,
    ):
        if not await self._is_dev(interaction.user):
            return await interaction.response.send_message("❌ 僅限 Bot 開發者使用。", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        fname = os.path.basename(file.filename)
        raw_bytes = await file.read()

        # 1. ZIP 更新包模式
        if fname.lower().endswith(".zip"):
            try:
                await self.run_cleanup_report(remove_update_pack=False)
                count = await asyncio.to_thread(self._extract_zip_safely, raw_bytes, False)
                if auto_reload:
                    await interaction.followup.send(
                        f"✅ 更新包 `{fname}` 已安全覆蓋 **`{count}`** 個檔案，正在執行熱重啟 (execv)...",
                        ephemeral=True,
                    )
                    self.bot.is_restarting = True
                    self.bot.exit_code = 1
                    await self.bot.close()
                else:
                    await interaction.followup.send(
                        f"✅ 更新包 `{fname}` 已覆蓋 **`{count}`** 個檔案（未自動重啟，可手動 `/dev reload`）。",
                        ephemeral=True,
                    )
            except Exception as e:
                await interaction.followup.send(f"❌ 解壓更新包失敗：`{e}`", ephemeral=True)
            return

        # 2. 單一 .py 模組熱部署模式
        if not fname.lower().endswith(".py"):
            return await interaction.followup.send("❌ 僅支援上傳 `.py` 程式碼或 `.zip` 更新包。", ephemeral=True)

        # 語法預檢，防止上傳壞掉的檔案
        try:
            compile(raw_bytes.decode("utf-8"), fname, "exec")
        except Exception as syn_err:
            return await interaction.followup.send(f"❌ 語法預檢失敗，已拒絕覆蓋：\n```py\n{syn_err}\n```", ephemeral=True)

        rel_target = fname if target_dir == "root" else os.path.join(target_dir, fname)
        safe_target = _safe_extract_path(".", rel_target)
        if not safe_target:
            return await interaction.followup.send("❌ 無效的目標檔案路徑。", ephemeral=True)

        os.makedirs(os.path.dirname(safe_target), exist_ok=True)
        with open(safe_target, "wb") as f:
            f.write(raw_bytes)

        msg = f"✅ 已上傳並覆蓋 `{rel_target.replace(os.sep, '/')}`（通過語法檢查）。"
        if auto_reload and target_dir == "cogs":
            ext_name = f"cogs.{os.path.splitext(fname)[0]}"
            ok_cnt, failed = await self._reload_extensions(ext_name)
            if ok_cnt > 0:
                msg += f"\n🔄 已自動熱重載 `{ext_name}`，新程式碼已即時生效！"
            else:
                msg += f"\n⚠️ 熱重載失敗：`{failed[0][1] if failed else '未知錯誤'}`"
        elif auto_reload and target_dir in ("utils", "root"):
            msg += "\nℹ️ 核心檔案已更新，建議執行 `/dev reload` 或 `/restart` 以套用全部依賴。"

        await interaction.followup.send(msg, ephemeral=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 版本履歷 (/changelog & .v)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_changelog_embed(self, commit_info: str) -> discord.Embed:
        embed = discord.Embed(
            title=f"🚀 倉鼠勇者 {BOT_VERSION} — 極速視覺版更新履歷",
            description=(
                f"📌 **當前版本**：`v{BOT_VERSION}`\n"
                f"🏷️ **Git Commit**：`{commit_info}`\n"
                f"🌐 **GitHub 倉庫**：`{self.repo}` (`{self.branch}`)\n\n"
                "1. ⚡ **雙方案極速分流引擎（Free vs Pro）**\n"
                "   • 記憶體 TTL 快取加速 Pro 查詢，Pro 享 **0 秒極速連發**，免費版為 3.0 秒標準節流。\n"
                "   • 新增 `/plan` 雙方案對比視覺卡。\n\n"
                "2. 🎨 **3.0 全新程式化圖片 UI**\n"
                "   • `/help`、`/plan`、`/ping`、`/health`、`/userinfo`、`/serverinfo`、`/version` 全面升級深石板 × 暖琥珀高速圖卡。\n\n"
                "3. 🧹 **零洗版淨化與假延遲移除**\n"
                "   • 移除每 10 分鐘 Pro 廣告推播、打字/新訊/狀態洗版日誌、聊天誤觸與 27 秒假進度條。\n\n"
                "4. 🛠️ **開發者超強上傳與終極清暫存**\n"
                "   • 新增 `/dev panel`、`/dev upload`（直接上傳 `.py` 語法預檢並即時熱重載）、`/dev reload`、`/dev clean`、`/dev disk` 與 30 分鐘自動低空間守護。"
            ),
            color=Colors.PRIMARY,
        )
        embed.set_footer(text=f"倉鼠勇者 {BOT_VERSION} • 極速雙方案架構")
        return embed

    @commands.command(name="v", aliases=["ver", "changelog"])
    async def version_command(self, ctx: commands.Context):
        commit_info = await self.get_current_git_commit()
        await ctx.send(embed=self._build_changelog_embed(commit_info))

    @app_commands.command(name="changelog", description="查看倉鼠勇者 3.0 最新更新紀錄與版本履歷")
    async def slash_changelog(self, interaction: discord.Interaction):
        commit_info = await self.get_current_git_commit()
        await interaction.response.send_message(embed=self._build_changelog_embed(commit_info))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 傳統前綴指令相容 (.sync / .pack / .apply / .clean)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @commands.group(name="sync", invoke_without_command=True)
    async def sync_group(self, ctx: commands.Context):
        commit_info = await self.get_current_git_commit()
        embed = discord.Embed(
            title="🔄 倉鼠勇者 3.0 自動同步與更新系統",
            description=(
                f"**目前版本 (Commit):** `{commit_info}`\n"
                f"**GitHub 倉庫:** `{self.repo}` (`{self.branch}`)\n\n"
                "**可用指令:**\n"
                f"`{ctx.prefix}sync run` — 清理磁碟 + GitHub 同步並熱重啟\n"
                f"`{ctx.prefix}clean` — 終極清暫存（磁碟 + SQLite + RAM）\n"
                f"`{ctx.prefix}pack` / `{ctx.prefix}apply` — 產生或套用超輕量更新包\n"
                "`/dev panel` — 開啟 3.0 互動式開發者控制台"
            ),
            color=Colors.PRIMARY,
        )
        await ctx.send(embed=embed)

    @sync_group.command(name="info")
    async def sync_info(self, ctx: commands.Context):
        commit_info = await self.get_current_git_commit()
        has_token = "已設定" if self.token else "未設定"
        embed = discord.Embed(
            title="ℹ️ 系統更新與版本資訊",
            description=(
                f"**當前版本:** `{commit_info}`\n"
                f"**GitHub 倉庫:** `{self.repo}`\n"
                f"**分支:** `{self.branch}`\n"
                f"**GitHub Token:** `{has_token}`"
            ),
            color=Colors.PRIMARY,
        )
        await ctx.send(embed=embed)

    async def run_update_process(self, update_status_func) -> bool:
        """核心更新與重啟流程：終極清暫存 → git fetch & reset → (Zip 備援)"""
        await update_status_func("🚀 正在啟動 3.0 升級更新流程...")

        await update_status_func("🧹 Step 0/3: 正在執行終極清暫存...")
        cleanup_result = await self.run_cleanup()
        await update_status_func(cleanup_result)

        git_success = False
        if os.path.isdir(".git"):
            try:
                await update_status_func("🔄 Step 1/3: Git 增量同步 (`fetch --depth 1` + `reset --hard`)...")
                proc_fetch = await asyncio.create_subprocess_exec(
                    "git", "fetch", "--depth", "1", "origin", self.branch,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc_fetch.communicate()

                proc_reset = await asyncio.create_subprocess_exec(
                    "git", "reset", "--hard", f"origin/{self.branch}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_r, stderr_r = await proc_reset.communicate()
                out_str = stdout_r.decode("utf-8", errors="ignore").strip()

                proc_clean = await asyncio.create_subprocess_exec(
                    "git", "clean", "-fd",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc_clean.communicate()

                if proc_reset.returncode == 0:
                    git_success = True
                    await update_status_func(f"✅ Git 增量同步成功！\n```\n{out_str or 'HEAD 已更新至最新版本'}\n```")
                else:
                    git_err_str = stderr_r.decode("utf-8", errors="ignore").strip()
                    await update_status_func(f"⚠️ Git reset 失敗 ({proc_reset.returncode})，切換 Zip 備援...\n```\n{git_err_str}\n```")
            except Exception as e:
                await update_status_func(f"⚠️ Git 指令不可用: `{e}`，切換至 Zip 備援模式...")
        else:
            await update_status_func("ℹ️ 未偵測到 `.git`，使用 GitHub API Zip 模式同步...")

        if not git_success:
            if not self.repo:
                await update_status_func("❌ 錯誤：未在 `.env` 中設定 `GITHUB_REPO`。")
                return False

            await update_status_func("📥 Step 2/3: 透過 GitHub API 下載最新程式碼 Zip...")
            headers = {
                "User-Agent": "HamsterHero-3.0-AutoUpdater",
                "Accept": "application/vnd.github+json",
            }
            if self.token:
                headers["Authorization"] = f"token {self.token}"

            url = f"https://api.github.com/repos/{self.repo}/zipball/{self.branch}"
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
                    async with session.get(url, headers=headers) as response:
                        if response.status != 200:
                            text = await response.text()
                            await update_status_func(f"❌ 下載失敗 (HTTP {response.status}): {text[:200]}")
                            return False
                        zip_data = await response.read()

                await self.run_cleanup_report(remove_update_pack=True)
                await update_status_func("📦 Zip 下載完成，正在安全解壓縮覆蓋程式碼...")
                count = await asyncio.to_thread(self._extract_zip_safely, zip_data, True)
                await update_status_func(f"✅ Zip 安全解壓覆蓋成功（共 `{count}` 檔）！")
            except OSError as e:
                if getattr(e, "errno", None) == 28 or "No space left" in str(e):
                    server_id = os.getenv("SERVER_ID", "未知")
                    await update_status_func(
                        f"❌ **磁碟空間不足 (Errno 28)** — 節點 `{server_id}`\n"
                        "已觸發終極清暫存，請使用 `/dev clean remove_pack:True` 釋放更多空間後重試。"
                    )
                else:
                    await update_status_func(f"❌ Zip 更新失敗: `{e}`")
                return False
            except Exception as e:
                await update_status_func(f"❌ Zip 更新失敗: `{e}`")
                return False

        await update_status_func("🔄 正在啟動系統熱重啟流程 (execv)...")
        try:
            await self.bot.change_presence(
                status=discord.Status.dnd,
                activity=discord.Game("正在升級重啟中..."),
            )
            await asyncio.sleep(1.5)
        except Exception:
            pass

        self.bot.is_restarting = True
        self.bot.exit_code = 1
        await self.bot.close()
        return True

    @commands.command(name="pack", aliases=["更新包", "buildpack"])
    async def pack_command(self, ctx: commands.Context):
        """生成並發送 3.0 超輕量更新包 (.pack)"""
        try:
            from build_update_pack import build_pack
            zip_path = await asyncio.to_thread(build_pack, True)
            size_kb = os.path.getsize(zip_path) / 1024
            file = discord.File(zip_path, filename="update_pack.zip")
            embed = discord.Embed(
                title=f"📦 倉鼠勇者 {BOT_VERSION} 超輕量更新包",
                description=(
                    f"✅ 更新包生成成功（`{size_kb:.2f} KB`，含 SHA-256 `manifest.json`）。\n"
                    "可透過 `/dev upload` 或 `.apply` 直接套用並熱重啟，或上傳至主機根目錄解壓。"
                ),
                color=Colors.SUCCESS,
            )
            await ctx.send(embed=embed, file=file)
        except Exception as e:
            await ctx.send(f"❌ 生成更新包失敗: `{e}`")

    @sync_group.command(name="pack")
    async def sync_pack(self, ctx: commands.Context):
        await self.pack_command(ctx)

    @commands.command(name="apply", aliases=["套用", "applypack"])
    async def apply_command(self, ctx: commands.Context):
        """從附件或根目錄安全套用 update_pack.zip 並熱重啟 (.apply)"""
        zip_bytes = None
        if ctx.message.attachments:
            att = ctx.message.attachments[0]
            if att.filename.lower().endswith(".zip"):
                zip_bytes = await att.read()

        zip_path = "update_pack.zip"
        if not zip_bytes and os.path.exists(zip_path):
            try:
                with open(zip_path, "rb") as f:
                    zip_bytes = f.read()
            except OSError:
                pass

        if not zip_bytes:
            return await ctx.send("❌ 未找到更新包！請上傳 `.zip` 附件並輸入 `.apply`（或使用 `/dev upload`）。")

        msg = await ctx.send("📦 正在執行清暫存並安全解壓縮更新包...")
        try:
            await self.run_cleanup_report(remove_update_pack=False)
            count = await asyncio.to_thread(self._extract_zip_safely, zip_bytes, False)
            await msg.edit(content=f"✅ 更新包套用成功（覆蓋 `{count}` 檔）！正在執行熱重啟 (execv)...")
            self.bot.is_restarting = True
            self.bot.exit_code = 1
            await self.bot.close()
        except Exception as e:
            await msg.edit(content=f"❌ 套用更新包失敗: `{e}`")

    @sync_group.command(name="apply")
    async def sync_apply(self, ctx: commands.Context):
        await self.apply_command(ctx)

    @commands.command(name="clean", aliases=["清理", "diskclean"])
    async def clean_command(self, ctx: commands.Context):
        """立即執行終極清暫存 (.clean)"""
        server_id = os.getenv("SERVER_ID", "local")
        msg = await ctx.send(f"🧹 **[{server_id}]** 正在執行 3.0 終極清暫存...")
        report = await self.run_cleanup()
        await msg.edit(content=f"**[{server_id}]** {report}")

    @sync_group.command(name="clean")
    async def sync_clean(self, ctx: commands.Context):
        await self.clean_command(ctx)

    @sync_group.command(name="run")
    async def sync_run(self, ctx: commands.Context):
        message = None

        async def update_status(text: str):
            nonlocal message
            if not message:
                message = await ctx.send(text)
            else:
                await message.edit(content=text)

        await self.run_update_process(update_status)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoUpdate(bot))
