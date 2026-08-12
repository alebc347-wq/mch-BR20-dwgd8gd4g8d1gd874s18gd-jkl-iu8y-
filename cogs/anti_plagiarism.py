import discord
from discord import app_commands
from discord.ext import commands
import datetime
from utils.database import Database

class AntiPlagiarism(commands.Cog):
    """倉鼠勇者 - 原創心血防護、反抄襲與系統安全核心模組 (Anti-Plagiarism & System Security Core)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Database = bot.db

    def is_owner_or_admin():
        """檢查是否為開發者/管理員"""
        async def predicate(interaction: discord.Interaction):
            admin_id = 1437408048934027274
            if interaction.user.id == admin_id or interaction.user.guild_permissions.administrator:
                return True
            await interaction.response.send_message("❌ 你沒有權限執行此管理指令。", ephemeral=True)
            return False
        return app_commands.check(predicate)

    @app_commands.command(name="terms", description="查看「倉鼠勇者」原創版權條款、反抄襲聲明與服務規範")
    @app_commands.command(name="copyright", description="查看「倉鼠勇者」原創版權條款、反抄襲聲明與服務規範")
    async def terms_slash(self, interaction: discord.Interaction):
        """顯示完整的版權與防抄襲聲明 Embed"""
        embed = discord.Embed(
            title="🛡️ 倉鼠勇者 原創聲明與反抄襲系統規範",
            description=(
                "為維護「倉鼠勇者」團隊原創成果與系統安全，所有使用者及伺服器管理者均須遵守以下規範。"
                "本系統已部署全域行為追蹤、水印印記與自動防護機制。"
            ),
            color=discord.Color.gold(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )

        embed.add_field(
            name="📜 1. 原創版權與行為模式防護",
            value=(
                "• **獨家文字與題庫版權**：機器人內所有題庫、規則、按鈕與回覆語句均為原創作品。\n"
                "• **禁止「行為模式」複製**：嚴禁複製考試邏輯、題型順序與架構（即使修改部分文字亦屬侵權）。\n"
                "• **Bug 特徵追蹤與印記存證**：系統植入特定文字與邏輯標記，若抄襲同款標記將直接作為違規鐵證。"
            ),
            inline=False
        )

        embed.add_field(
            name="⚔️ 2. 系統防禦與權限對齊要求",
            value=(
                "• **AntiRaidX 權限對齊**：伺服器內機器人角色權限需對齊防禦標準，權限不足時自動鎖定功能。\n"
                "• **高階管理權限控管**：嚴格控管管理訊息、身分組、頻道與封鎖成員等關鍵權限。\n"
                "• **高權限動作安全驗證**：執行敏感管理指令時需二次驗證，防範帳號濫用。"
            ),
            inline=False
        )

        embed.add_field(
            name="🤖 3. 反抄襲技術限制與反爬蟲",
            value=(
                "• **動態隨機化與冷卻**：考試與題目採動態生成/隨機排列，嚴禁連續請求 (Spamming) 爬取題庫。\n"
                "• **身分驗證與冷卻牆**：實施驗證牆與冷卻期，防止小號測試與抄襲測試。\n"
                "• **伺服器白名單與自動退群**：偵測到疑慮測試場或抄襲者伺服器時，機器人將自動退群並紀錄證據。"
            ),
            inline=False
        )

        embed.add_field(
            name="⚖️ 4. 懲罰機制與免責聲明",
            value=(
                "• **全域黑名單 (Global Blacklist)**：經證實之抄襲者與惡意伺服器列入跨伺服器全域黑名單。\n"
                "• **開發階段免責聲明**：本機器人處於持續迭代開發階段，最終解釋權歸「倉鼠勇者」團隊所有。"
            ),
            inline=False
        )

        embed.set_footer(text="🛡️ 倉鼠勇者原創防偽認證 | Anti-Plagiarism Core Enabled", icon_url=self.bot.user.display_avatar.url if self.bot.user else None)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 全域黑名單與白名單管理指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    admin_group = app_commands.Group(name="anti_plagiarism", description="防抄襲與全域安全管理指令")

    @admin_group.command(name="blacklist_add", description="[管理員] 將使用者或伺服器加入全域黑名單")
    @app_commands.describe(target_id="目標 User ID 或 Guild ID", target_type="類型 (user/guild)", reason="封鎖原因")
    async def blacklist_add(self, interaction: discord.Interaction, target_id: str, target_type: str = "user", reason: str = "抄襲/惡意破壞"):
        try:
            tid = int(target_id)
        except ValueError:
            await interaction.response.send_message("❌ 請輸入有效的 ID 數字。", ephemeral=True)
            return

        await self.db.add_global_blacklist(tid, target_type.lower(), reason, interaction.user.id)
        await interaction.response.send_message(f"✅ 已成功將 {target_type} ID `{tid}` 加入全域黑名單！原因：{reason}", ephemeral=True)

    @admin_group.command(name="blacklist_remove", description="[管理員] 將目標從全域黑名單移除")
    @app_commands.describe(target_id="目標 ID")
    async def blacklist_remove(self, interaction: discord.Interaction, target_id: str):
        try:
            tid = int(target_id)
        except ValueError:
            await interaction.response.send_message("❌ 請輸入有效的 ID 數字。", ephemeral=True)
            return

        await self.db.remove_global_blacklist(tid)
        await interaction.response.send_message(f"✅ 已成功將 ID `{tid}` 自全域黑名單中移除！", ephemeral=True)

    @admin_group.command(name="blacklist_list", description="[管理員] 查看全域黑名單列表")
    async def blacklist_list(self, interaction: discord.Interaction):
        records = await self.db.get_global_blacklist()
        if not records:
            await interaction.response.send_message("ℹ️ 當前全域黑名單為空。", ephemeral=True)
            return

        embed = discord.Embed(title="⛔ 全域黑名單記錄列表", color=discord.Color.red())
        for tid, ttype, reason, added_by, added_at in records[:25]:
            embed.add_field(
                name=f"ID: {tid} ({ttype})",
                value=f"原因: {reason}\n添加者: <@{added_by}>\n時間: {added_at[:19]}",
                inline=True
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 全域事件防護
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """當機器人被加入新伺服器時進行黑名單與安全檢測"""
        is_bg_blacklisted = await self.db.is_blacklisted(guild.id)
        is_owner_blacklisted = await self.db.is_blacklisted(guild.owner_id)

        if is_bg_blacklisted or is_owner_blacklisted:
            control_channel_id = 1473141984855199856
            channel = self.bot.get_channel(control_channel_id)
            if channel:
                embed = discord.Embed(
                    title="🚨 偵測到黑名單伺服器/擁有者邀請",
                    description=f"伺服器：`{guild.name}` ({guild.id})\n擁有者：`{guild.owner}` ({guild.owner_id})\n系統將自動離開該伺服器以維護安全。",
                    color=discord.Color.dark_red()
                )
                await channel.send(embed=embed)
            await guild.leave()

async def setup(bot: commands.Bot):
    await bot.add_cog(AntiPlagiarism(bot))
