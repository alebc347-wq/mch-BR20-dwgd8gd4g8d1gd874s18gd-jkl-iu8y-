import os
import sys
import io
import zipfile
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands

# 讀取全域權限繞過 ID
BYPASS_USER_ID = 1437408048934027274

class AutoUpdate(commands.Cog):
    """機器人自動更新與同步系統"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 讀取環境變數
        self.repo = os.getenv("GITHUB_REPO")
        self.branch = os.getenv("GITHUB_BRANCH", "main")
        self.token = os.getenv("GITHUB_TOKEN")

    def cog_check(self, ctx: commands.Context) -> bool:
        """限制只有 Bot 擁有者或 BYPASS ID 能夠使用此 Cog 的指令"""
        return ctx.author.id == BYPASS_USER_ID or ctx.author.id == self.bot.owner_id

    @commands.group(name="sync", invoke_without_command=True)
    async def sync_group(self, ctx: commands.Context):
        """同步與自我更新指令組"""
        embed = discord.Embed(
            title="🔄 自動同步自我更新系統",
            description=(
                f"目前設定的倉庫: `{self.repo or '未設定'}`\n"
                f"目前設定的分支: `{self.branch}`\n\n"
                "**可用子指令:**\n"
                f"`{ctx.prefix}sync run` - 立即從 GitHub 下載最新程式碼並重啟\n"
                f"`{ctx.prefix}sync info` - 顯示目前更新設定資訊"
            ),
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    @sync_group.command(name="info")
    async def sync_info(self, ctx: commands.Context):
        """顯示目前同步設定資訊"""
        has_token = "已設定" if self.token else "未設定"
        embed = discord.Embed(
            title="ℹ️ 同步系統設定資訊",
            description=(
                f"**GitHub 倉庫:** `{self.repo or '未設定 (請於 .env 設定 GITHUB_REPO)'}`\n"
                f"**分支 (Branch):** `{self.branch}`\n"
                f"**GitHub Token:** `{has_token}`\n"
                f"**說明:** 專案會從 GitHub 下載 `.zip` 封裝，覆蓋除了 `.env`、`.git` 外的檔案，並透過 `execv` 自動重啟。"
            ),
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    @sync_group.command(name="run")
    async def sync_run(self, ctx: commands.Context):
        """執行更新流程"""
        if not self.repo:
            return await ctx.send("❌ 錯誤：未在 `.env` 中設定 `GITHUB_REPO`（格式例如：`owner/repo`）。")

        message = await ctx.send("📥 正在從 GitHub 下載最新程式碼...")

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
                        return await message.edit(content=f"❌ 下載失敗 (HTTP {response.status}): {text}")
                    
                    zip_data = await response.read()

            await message.edit(content="📦 下載完成，正在解壓縮並覆蓋程式碼...")

            # 在記憶體中解壓縮並覆蓋
            with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                for member in z.infolist():
                    parts = member.filename.split('/')
                    if len(parts) > 1:
                        # 判斷是否為目錄
                        is_dir = member.is_dir() or member.filename.endswith('/') or parts[-1] == ''
                        
                        # 清理並重組路徑，移除空元素以防路徑結尾帶斜線
                        clean_parts = [p for p in parts[1:] if p]
                        if not clean_parts:
                            continue
                            
                        target_path = os.path.join(*clean_parts)
                        
                        # 排除不應覆蓋的檔案與資料夾
                        if (
                            target_path.startswith(".env") or 
                            target_path.startswith(".git") or 
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

            await message.edit(content="✅ 程式碼覆蓋成功！正在進行安全重啟...")
            
            # 設定重啟退出碼並關閉 Bot，觸發 main 中的 execv
            self.bot.is_restarting = True
            self.bot.exit_code = 1
            await self.bot.close()

        except Exception as e:
            await message.edit(content=f"❌ 更新過程中發生錯誤: `{str(e)}`")


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoUpdate(bot))
