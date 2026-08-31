import os
import sys
import io
import zipfile
import asyncio
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands

# 讀取全域權限繞過 ID
BYPASS_USER_ID = 1437408048934027274


class AutoUpdate(commands.Cog):
    """高級機器人自動更新與同步系統"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.repo = os.getenv("GITHUB_REPO", "alebc347-wq/mch-BR20-dwgd8gd4g8d1gd874s18gd-jkl-iu8y-")
        self.branch = os.getenv("GITHUB_BRANCH", "main")
        self.token = os.getenv("GITHUB_TOKEN")

    def cog_check(self, ctx: commands.Context) -> bool:
        """限制只有 Bot 擁有者或 BYPASS ID 能夠使用此 Cog 的前綴指令"""
        return ctx.author.id == BYPASS_USER_ID or ctx.author.id == self.bot.owner_id

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

    @commands.command(name="v", aliases=["ver", "changelog"])
    async def version_command(self, ctx: commands.Context):
        """顯示機器人版本與最新更新履歷"""
        commit_info = await self.get_current_git_commit()
        embed = discord.Embed(
            title="🚀 勇者 2.0 系統版本與最新更新履歷",
            description=(
                f"📌 **當前發行版本:** `v2.5.0-Release`\n"
                f"🏷️ **Git Commit:** `{commit_info}`\n"
                f"🌐 **GitHub 倉庫:** `{self.repo}` (`{self.branch}`)\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "✨ **【最新更新履歷 (Release Changelog)】** ✨\n\n"
                "1. 🎉 **歡迎 & 離開圖文通知系統**\n"
                "   • 新增 `/tool welcome_setup` 與 `/tool leave_setup`。\n"
                "   • 支援自訂歡迎/離開文字、動態變數（`{user}`, `{guild}`, `{count}`）與 GIF/圖片網址。\n\n"
                "2. 🏆 **聊天等級系統 (Leveling 1 ~ 10)**\n"
                "   • 發言自動累積經驗升等（包含升等亮眼通告 Embed）。\n"
                "   • 自動檢測與創建「聊天等級 1」至「聊天等級 10」角色組，並精確放置於身分組最底部層級。\n"
                "   • 升等自動賦予新等級身分組並自動清理舊身分組。\n"
                "   • 提供 `/tool rank` 查詢個人經驗與等級進度條。\n\n"
                "3. ⚔️ **戰隊考試 200 等免試直過政策**\n"
                "   • 報名表單填寫遊戲等級 >= 200 等時，自動核准通過免試，並即時自動更新戰隊成員名單。\n"
                "   • 戰隊成員名單表情符號全面升級為標準美觀 Unicode Emoji。\n"
                "   • 提供 `/member add`, `/member remove`, `/member list` 管理名單。\n\n"
                "4. 🚫 **指定違規用戶自動刪除**\n"
                "   • 自動偵測與攔截刪除特定違規使用者 (`172002275412279296`) 之發言。\n\n"
                "5. ⚡ **斜線指令階層優化與即時同步**\n"
                "   • 解決 Discord 100 個頂層斜線指令限制，指令即時同步至各伺服器。"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text="勇者 2.0 高可用系統 ｜ 隨時自動同步最優化版本")
        await ctx.send(embed=embed)

    @app_commands.command(name="changelog", description="ℹ️ 查看機器人最新更新紀錄與版本履歷")
    async def slash_changelog(self, interaction: discord.Interaction):
        commit_info = await self.get_current_git_commit()
        embed = discord.Embed(
            title="🚀 勇者 2.0 系統版本與最新更新履歷",
            description=(
                f"📌 **當前發行版本:** `v2.5.0-Release`\n"
                f"🏷️ **Git Commit:** `{commit_info}`\n"
                f"🌐 **GitHub 倉庫:** `{self.repo}` (`{self.branch}`)\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "✨ **【最新更新履歷 (Release Changelog)】** ✨\n\n"
                "1. 🎉 **歡迎 & 離開圖文通知系統**\n"
                "   • 新增 `/tool welcome_setup` 與 `/tool leave_setup`。\n"
                "   • 支援自訂歡迎/離開文字、動態變數（`{user}`, `{guild}`, `{count}`）與 GIF/圖片網址。\n\n"
                "2. 🏆 **聊天等級系統 (Leveling 1 ~ 10)**\n"
                "   • 發言自動累積經驗升等（包含升等亮眼通告 Embed）。\n"
                "   • 自動檢測與創建「聊天等級 1」至「聊天等級 10」角色組，並精確放置於身分組最底部層級。\n"
                "   • 升等自動賦予新等級身分組並自動清理舊身分組。\n"
                "   • 提供 `/tool rank` 查詢個人經驗與等級進度條。\n\n"
                "3. ⚔️ **戰隊考試 200 等免試直過政策**\n"
                "   • 報名表單填寫遊戲等級 >= 200 等時，自動核准通過免試，並即時自動更新戰隊成員名單。\n"
                "   • 戰隊成員名單表情符號全面升級為標準美觀 Unicode Emoji。\n"
                "   • 提供 `/member add`, `/member remove`, `/member list` 管理名單。\n\n"
                "4. 🚫 **指定違規用戶自動刪除**\n"
                "   • 自動偵測與攔截刪除特定違規使用者 (`172002275412279296`) 之發言。\n\n"
                "5. ⚡ **斜線指令階層優化與即時同步**\n"
                "   • 解決 Discord 100 個頂層斜線指令限制，指令即時同步至各伺服器。"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text="勇者 2.0 高可用系統 ｜ 隨時自動同步最優化版本")
        await interaction.response.send_message(embed=embed)

    @commands.group(name="sync", invoke_without_command=True)
    async def sync_group(self, ctx: commands.Context):
        """同步與自我更新指令組"""
        commit_info = await self.get_current_git_commit()
        embed = discord.Embed(
            title="🔄 高級自動同步與更新系統",
            description=(
                f"**目前版本 (Commit):** `{commit_info}`\n"
                f"**GitHub 倉庫:** `{self.repo}`\n"
                f"**分支 (Branch):** `{self.branch}`\n\n"
                "**可用子指令:**\n"
                f"`{ctx.prefix}sync run` - 立即同步最新程式碼並安全重啟\n"
                f"`{ctx.prefix}sync info` - 顯示目前系統版本與 GitHub 狀態"
            ),
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    @sync_group.command(name="info")
    async def sync_info(self, ctx: commands.Context):
        """顯示目前同步設定資訊"""
        commit_info = await self.get_current_git_commit()
        has_token = "已設定" if self.token else "未設定"
        embed = discord.Embed(
            title="ℹ️ 系統更新與版本資訊",
            description=(
                f"**當前版本:** `{commit_info}`\n"
                f"**GitHub 倉庫:** `{self.repo}`\n"
                f"**分支 (Branch):** `{self.branch}`\n"
                f"**GitHub Token:** `{has_token}`\n\n"
                "**更新機制說明:**\n"
                "1. 優先嘗試 `git pull` 進行高效增量同步。\n"
                "2. 若環境未支援 Git，會自動切換為 GitHub API Zip 降級下載模式。\n"
                "3. 下載後自動進行全自動程式碼覆蓋與 `execv` 熱重啟。"
            ),
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    async def run_cleanup(self) -> str:
        """更新前深度清理磁碟空間：刪除 __pycache__、暫存檔、pip 快取、SQLite WAL 與暫存媒體"""
        import shutil
        import tempfile
        freed = 0

        # 1. 刪除所有 __pycache__ 目錄與殘留 .pyc/.pyo 檔案
        for root, dirs, files in os.walk(".", topdown=False):
            dirs[:] = [d for d in dirs if d != ".git"]
            for d in dirs:
                if d == "__pycache__":
                    full = os.path.join(root, d)
                    try:
                        size = sum(
                            os.path.getsize(os.path.join(full, f))
                            for f in os.listdir(full)
                            if os.path.isfile(os.path.join(full, f))
                        )
                        shutil.rmtree(full, ignore_errors=True)
                        freed += size
                    except Exception:
                        pass
            for fname in files:
                if fname.endswith((".pyc", ".pyo", ".tmp", ".log", ".bak")):
                    fpath = os.path.join(root, fname)
                    try:
                        freed += os.path.getsize(fpath)
                        os.remove(fpath)
                    except Exception:
                        pass

        # 2. 刪除 data/ 內的暫存媒體 (TTS mp3/wav、截圖 png、日誌 log)
        temp_exts = {".mp3", ".wav", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".log", ".tmp", ".bak"}
        data_dir = "data"
        if os.path.isdir(data_dir):
            for fname in os.listdir(data_dir):
                # 保留重要設定 JSON
                if fname.endswith((".json", ".db")):
                    continue
                fpath = os.path.join(data_dir, fname)
                if os.path.isfile(fpath) and os.path.splitext(fname)[1].lower() in temp_exts:
                    try:
                        freed += os.path.getsize(fpath)
                        os.remove(fpath)
                    except Exception:
                        pass

        # 3. 刪除 pip 快取目錄 (~/.cache/pip)
        pip_cache = os.path.expanduser("~/.cache")
        if os.path.isdir(pip_cache):
            try:
                for r, _, fs in os.walk(pip_cache):
                    for f in fs:
                        freed += os.path.getsize(os.path.join(r, f))
                shutil.rmtree(pip_cache, ignore_errors=True)
            except Exception:
                pass

        # 4. 刪除系統暫存目錄中的臨時檔案 (/tmp)
        tmp_dir = tempfile.gettempdir()
        if os.path.isdir(tmp_dir) and tmp_dir != "/":
            try:
                for f in os.listdir(tmp_dir):
                    if f.startswith(("tmp", "pip-", "discord-")):
                        fp = os.path.join(tmp_dir, f)
                        if os.path.isfile(fp):
                            freed += os.path.getsize(fp)
                            os.remove(fp)
                        elif os.path.isdir(fp):
                            shutil.rmtree(fp, ignore_errors=True)
            except Exception:
                pass

        # 5. 刪除 scratch/ 與暫存日誌檔案
        if os.path.isdir("scratch"):
            try:
                shutil.rmtree("scratch", ignore_errors=True)
            except Exception:
                pass

        # 6. SQLite 釋放空間與檢查點 (使用 TRUNCATE 與 checkpoint，避免 VACUUM 雙重佔用磁碟)
        try:
            db = self.bot.db.db
            if db:
                await db.execute("PRAGMA journal_mode = TRUNCATE;")
                await db.execute("PRAGMA temp_store = MEMORY;")
                await db.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                await db.execute("PRAGMA incremental_vacuum;")
        except Exception:
            pass

        # 7. 清理殘留的 db-wal / db-shm 實體檔案
        for wal_file in [os.path.join("data", "bot.db-wal"), os.path.join("data", "bot.db-shm")]:
            if os.path.exists(wal_file):
                try:
                    freed += os.path.getsize(wal_file)
                    os.remove(wal_file)
                except Exception:
                    pass

        freed_kb = freed // 1024
        freed_mb = freed_kb / 1024
        size_str = f"{freed_mb:.1f} MB" if freed_mb >= 1 else f"{freed_kb} KB"
        return f"🧹 深度磁碟清理完成！已釋放約 **{size_str}** 磁碟空間。"

    async def run_update_process(self, update_status_func) -> bool:
        """核心更新與重啟流程：先清理磁碟 → git fetch & reset → (Zip 備援)"""
        await update_status_func("🚀 正在啟動升級更新流程...")

        # Step 0: 更新前自動清理磁碟
        await update_status_func("🧹 Step 0/3: 正在深度清理磁碟暫存空間...")
        cleanup_result = await self.run_cleanup()
        await update_status_func(cleanup_result)

        # Step 1: 優先嘗試 Git 增量同步 (使用 fetch + reset --hard，零額外磁碟開銷且不衝突)
        git_success = False
        git_err_str = ""
        if os.path.isdir(".git"):
            try:
                await update_status_func("🔄 Step 1/3: 嘗試使用 Git 高效增量同步 (`fetch` + `reset --hard`)...")
                # 1. Fetch 最新 Commit
                proc_fetch = await asyncio.create_subprocess_exec(
                    "git", "fetch", "--depth", "1", "origin", self.branch,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout_f, stderr_f = await proc_fetch.communicate()

                # 2. 強制 Reset 至最新遠端 Commit (自動捨棄本地覆蓋檔案)
                proc_reset = await asyncio.create_subprocess_exec(
                    "git", "reset", "--hard", f"origin/{self.branch}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout_r, stderr_r = await proc_reset.communicate()
                out_str = stdout_r.decode("utf-8", errors="ignore").strip()

                # 3. 清理未追蹤的垃圾檔案
                proc_clean = await asyncio.create_subprocess_exec(
                    "git", "clean", "-fd",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc_clean.communicate()

                if proc_reset.returncode == 0:
                    git_success = True
                    await update_status_func(f"✅ Git 增量同步成功！\n```\n{out_str or 'HEAD 已更新至最新版本'}\n```")
                else:
                    git_err_str = stderr_r.decode("utf-8", errors="ignore").strip()
                    await update_status_func(f"⚠️ Git reset 失敗 ({proc_reset.returncode})，嘗試 Zip 備援...\n```\n{git_err_str}\n```")
            except Exception as e:
                git_err_str = str(e)
                await update_status_func(f"⚠️ Git 指令不可用: `{e}`，切換至 Zip 備援模式...")
        else:
            await update_status_func("ℹ️ 容器環境未偵測到 `.git`，使用 GitHub API Zip 模式同步...")

        # Step 2: Zip 備援模式 (git pull 失敗或未包含 .git 時才啟動)
        if not git_success:
            if not self.repo:
                await update_status_func("❌ 錯誤：未在 `.env` 中設定 `GITHUB_REPO`。")
                return False

            await update_status_func("📥 Step 2/3: 透過 GitHub API 下載最新程式碼 Zip...")

            headers = {
                "User-Agent": "Discord-Bot-Auto-Updater",
                "Accept": "application/vnd.github+json"
            }
            if self.token:
                headers["Authorization"] = f"token {self.token}"

            url = f"https://api.github.com/repos/{self.repo}/zipball/{self.branch}"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers) as response:
                        if response.status != 200:
                            text = await response.text()
                            await update_status_func(f"❌ 下載失敗 (HTTP {response.status}): {text}")
                            return False
                        zip_data = await response.read()

                # Zip 解壓縮前再次清理以保證空間
                await self.run_cleanup()
                await update_status_func("📦 Zip 下載完成，正在解壓縮並安全覆蓋程式碼...")

                with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                    for member in z.infolist():
                        parts = member.filename.split('/')
                        if len(parts) > 1:
                            is_dir = member.is_dir() or member.filename.endswith('/') or parts[-1] == ''
                            clean_parts = [p for p in parts[1:] if p]
                            if not clean_parts:
                                continue
                            target_path = os.path.join(*clean_parts)
                            
                            # 忽略不必要的檔案以保護使用者設定與節省磁碟空間
                            if (
                                target_path.startswith(".env") or
                                target_path.startswith(".git") or
                                target_path.startswith("data/") or
                                target_path.startswith("data\\") or
                                target_path.startswith("tests/") or
                                target_path.endswith((".md", ".txt", ".png", ".jpg", ".webp")) or
                                target_path == "deploy_config.json"
                            ):
                                continue

                            if is_dir:
                                os.makedirs(target_path, exist_ok=True)
                            else:
                                dir_name = os.path.dirname(target_path)
                                if dir_name:
                                    os.makedirs(dir_name, exist_ok=True)
                                # 刪除舊檔案再寫入，防止暫存雙倍佔用
                                if os.path.exists(target_path):
                                    try:
                                        os.remove(target_path)
                                    except Exception:
                                        pass
                                with open(target_path, "wb") as f:
                                    f.write(z.read(member))

                await update_status_func("✅ Zip 解壓覆蓋成功！")
            except OSError as e:
                if getattr(e, 'errno', None) == 28 or "No space left" in str(e):
                    server_id = os.getenv("SERVER_ID", "未知")
                    server_name_map = {
                        "wispbyte-1": "**1 號機 (wispbyte-1)**",
                        "wispbyte-2": "**2 號機 (wispbyte-2)**",
                    }
                    server_label = server_name_map.get(server_id, f"**{server_id}**")
                    await update_status_func(
                        f"❌ **磁碟空間不足 ([Errno 28] No space left on device)**\n"
                        f"🖥️ **發生機器：{server_label}**\n\n"
                        f"已為您執行深度磁碟釋放。請在控制台重啟機器人或再次輸入 `.clean` 進行空間回收。"
                    )
                else:
                    await update_status_func(f"❌ Zip 更新失敗: `{e}`")
                return False
            except Exception as e:
                await update_status_func(f"❌ Zip 更新失敗: `{e}`")
                return False

        # 熱重啟流程
        await update_status_func("🔄 正在啟動系統熱重啟流程 (execv)...")
        try:
            await self.bot.change_presence(
                status=discord.Status.dnd,
                activity=discord.Game("正在升級重啟中...")
            )
            await asyncio.sleep(1.5)
        except Exception:
            pass

        self.bot.is_restarting = True
        self.bot.exit_code = 1
        await self.bot.close()
        return True

    @commands.command(name="clean", aliases=["清理", "diskclean"])
    async def clean_command(self, ctx: commands.Context):
        """立即深度清理磁碟暫存與釋放空間 (.clean)"""
        server_id = os.getenv("SERVER_ID", "local")
        msg = await ctx.send(f"🧹 **[{server_id}]** 正在執行深度磁碟空間清理...")
        report = await self.run_cleanup()
        await msg.edit(content=f"**[{server_id}]** {report}")

    @sync_group.command(name="clean")
    async def sync_clean(self, ctx: commands.Context):
        """執行磁碟深度清理"""
        await self.clean_command(ctx)

    @sync_group.command(name="run")
    async def sync_run(self, ctx: commands.Context):
        """執行更新流程"""
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
