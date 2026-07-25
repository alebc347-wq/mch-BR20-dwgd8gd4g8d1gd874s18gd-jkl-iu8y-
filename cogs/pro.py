"""
Pro 系統 Cog
提供 Pro 激活碼生成、激活碼使用、以及 Pro 狀態管理 UI
"""

import discord
from discord import app_commands
from discord.ext import commands
import uuid
from datetime import datetime, timezone
from typing import Optional

from config import Colors, Emoji
from utils.embeds import EmbedFactory


class ProActivationModal(discord.ui.Modal, title="輸入 Pro 激活碼"):
    key_input = discord.ui.TextInput(
        label="Pro 激活碼 (Pro Key)",
        placeholder="請輸入您的 Pro 激活金鑰...",
        required=True,
        min_length=10,
        max_length=100,
    )

    def __init__(self, cog: "Pro"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        key = self.key_input.value.strip()
        db = interaction.client.db
        
        success = await db.use_pro_key(key, interaction.guild_id, interaction.user.id)
        if success:
            embed = discord.Embed(
                title="✨ 恭喜！Pro 專業版已成功啟用！",
                description=(
                    f"🎉 您的伺服器 **{interaction.guild.name}** 已成功激活 Pro 權限！\n"
                    f"所有的 CPU 密集型高耗能功能（例如 24/7 模式、超長歌單解析）現已解鎖。\n\n"
                    f"👥 啟用者: {interaction.user.mention}\n"
                    f"📅 啟用時間: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} (UTC)"
                ),
                color=0xFFD700
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                embed=EmbedFactory.error("無效的金鑰", "您輸入的激活碼不存在或已被使用。"),
                ephemeral=True
            )


class ProPromotionView(discord.ui.View):
    """當用戶沒有 Pro 權限時顯示的推廣 UI 按鈕"""
    def __init__(self, cog: "Pro", support_url: str = "https://mch-mb20.base44.app/"):
        super().__init__(timeout=None)
        self.cog = cog
        
        # 獲取金鑰按鈕
        self.add_item(discord.ui.Button(
            label="獲取 Pro 金鑰",
            url=support_url,
            emoji="💎",
            style=discord.ButtonStyle.link
        ))

    @discord.ui.button(label="輸入激活碼", emoji="🔑", style=discord.ButtonStyle.success, custom_id="pro_enter_key")
    async def enter_key(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ProActivationModal(self.cog))


class Pro(commands.Cog):
    """Pro 專業版管理系統"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.support_url = "https://mch-mb20.base44.app/"  # 修改成您的獲取 Pro Key 的網址

    @staticmethod
    async def check_pro(interaction: discord.Interaction) -> bool:
        """
        全域檢查：檢查 interaction 所在的 Guild 是否已啟用 Pro 功能。
        如果沒有啟用，會自動發送精美的推廣與激活 UI。
        """
        if not interaction.guild_id:
            if interaction.response.is_done():
                await interaction.followup.send("❌ 此功能只能在伺服器中使用。", ephemeral=True)
            else:
                await interaction.response.send_message("❌ 此功能只能在伺服器中使用。", ephemeral=True)
            return False

        db = interaction.client.db
        is_pro = await db.is_guild_pro(interaction.guild_id)
        if is_pro:
            return True

        # 未啟用 Pro，顯示漂亮的 UI
        embed = discord.Embed(
            title="💎 這是 Pro 專業版專屬功能！",
            description=(
                f"此功能非常耗費伺服器 CPU 資源，為避免影響伺服器運行造成機器人中斷，"
                f"目前在您的伺服器 (**{interaction.guild.name}**) 尚未啟用 Pro 專業版。\n\n"
                f"💡 **Pro 專業版包含：**\n"
                f"• 🟢 24/7 音樂不斷線模式\n"
                f"• 📋 支援大型 YouTube / Spotify 播放清單解析 (超過 5 首歌)\n"
                f"• ⚡ 更高效與優先等級的串流解碼\n\n"
                f"請點擊下方按鈕獲取您的 Pro 金鑰以解鎖全部功能！"
            ),
            color=0xFFD700
        )
        embed.set_footer(text="勇者 2.0 • 專業版防禦機制")
        
        pro_cog = interaction.client.cogs.get("Pro")
        view = ProPromotionView(pro_cog)
        
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        return False

    # ─── 管理指令 (僅限 Bot Owner) ─────────────────────────────────────────

    @app_commands.command(name="pro_admin", description="管理 Pro 激活金鑰 (僅限 Bot 擁有者)")
    @app_commands.choices(action=[
        app_commands.Choice(name="產生金鑰", value="generate"),
        app_commands.Choice(name="列出未使用的金鑰", value="list_unused"),
        app_commands.Choice(name="列出已使用的金鑰", value="list_used"),
    ])
    @app_commands.describe(
        action="要執行的動作",
        days="金鑰的有效天數 (預設 30 天)",
        key="要刪除或查詢的金鑰 (選填)"
    )
    async def pro_admin(self, interaction: discord.Interaction, action: str, days: Optional[int] = 30, key: Optional[str] = None):
        # 檢查是否為擁有者
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message(
                embed=EmbedFactory.error("無權限", "只有 Bot 擁有者可以使用此指令。"),
                ephemeral=True
            )

        db = self.bot.db
        await interaction.response.defer(ephemeral=True)

        if action == "generate":
            # 產生金鑰
            new_key = f"HERO-PRO-{uuid.uuid4().hex.upper()[:16]}"
            await db.add_pro_key(new_key, days)
            
            embed = discord.Embed(
                title="✨ 成功產生 Pro 激活碼",
                description=(
                    f"🔑 **激活碼：** `{new_key}`\n"
                    f"📅 **有效天數：** {days} 天\n\n"
                    f"您現在可以將此金鑰分發給用戶使用。"
                ),
                color=Colors.SUCCESS
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        elif action == "list_unused":
            unused = await db.get_pro_keys()
            if not unused:
                return await interaction.followup.send("目前沒有未使用的金鑰。", ephemeral=True)
            
            text = "\n".join([f"• `{r[0]}` ({r[1]} 天) - 建立於: {r[2]}" for r in unused])
            embed = discord.Embed(
                title="📋 未使用的 Pro 金鑰列表",
                description=text,
                color=Colors.PRIMARY
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        elif action == "list_used":
            used = await db.get_used_keys()
            if not used:
                return await interaction.followup.send("目前沒有已被使用的金鑰。", ephemeral=True)
            
            text = "\n".join([
                f"• `{r[0]}` - 伺服器: `{r[1]}` (由 {self.bot.get_user(r[2]) or r[2]} 使用) - 使用於: {r[3]}"
                for r in used
            ])
            embed = discord.Embed(
                title="📋 已使用的 Pro 金鑰歷史",
                description=text,
                color=Colors.PRIMARY
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Pro(bot))
