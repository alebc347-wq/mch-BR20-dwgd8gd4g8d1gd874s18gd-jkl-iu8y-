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

    @commands.command(name="v", aliases=["version", "ver", "changelog"])
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

    @app_commands.command(name="version", description="ℹ️ 查看機器人目前版本與最新更新紀錄履歷")
    async def slash_version(self, interaction: discord.Interaction):
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

    async def run_update_process(self, update_status_func) -> bool:
        """核心更新與重啟流程 (支援 git pull 與 Zip API 雙重備援)"""
        await update_status_func("🚀 正在啟動升級更新流程...")

        # 優先嘗試 Git Pull 方式
        git_success = False
        try:
            await update_status_func("🔄 嘗試使用 `git pull` 進行高效程式碼同步...")
            proc = await asyncio.create_subprocess_exec(
                "git", "pull", "origin", self.branch,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            out_str = stdout.decode("utf-8", errors="ignore").strip()
            err_str = stderr.decode("utf-8", errors="ignore").strip()

            if proc.returncode == 0:
                git_success = True
                await update_status_func(f"✅ `git pull` 同步成功！\n```\n{out_str}\n```")
        except Exception as e:
            print(f"⚠️ git pull 嘗試失敗: {e}")

        # 如果 Git Pull 失敗或不支援，切換至 GitHub Zip API 下載模式
        if not git_success:
            if not self.repo:
                await update_status_func("❌ 錯誤：未在 `.env` 中設定 `GITHUB_REPO`。")
                return False

            await update_status_func("📥 正在透過 GitHub API 下載最新程式碼 Zip 包...")

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
                            
                            if (
                                target_path.startswith(".env") or 
                                target_path.startswith(".git") or 
                                target_path.startswith("data/") or
                                target_path.startswith("data\\") or
                                target_path == "deploy_config.json"
                            ):
                                continue
                                
                            if is_dir:
                                os.makedirs(target_path, exist_ok=True)
                            else:
                                dir_name = os.path.dirname(target_path)
                                if dir_name:
                                    os.makedirs(dir_name, exist_ok=True)
                                with open(target_path, "wb") as f:
                                    f.write(z.read(member))

                await update_status_func("✅ Zip 程式碼解壓與覆蓋成功！")
            except Exception as e:
                await update_status_func(f"❌ Zip 更新模式出錯: `{str(e)}`")
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
