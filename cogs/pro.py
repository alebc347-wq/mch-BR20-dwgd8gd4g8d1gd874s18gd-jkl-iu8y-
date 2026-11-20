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
from utils.speed_tier import speed_tier
from utils.visual_cards import render_plan_card


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
            # 立即清除 Pro 快取，0 ms 生效疾速通道
            speed_tier.invalidate_guild(interaction.guild_id)
            img_buf = await render_plan_card(interaction.guild.name, True, "即時生效")
            file = discord.File(img_buf, filename="plan_activated.png")
            embed = discord.Embed(
                title="⚡ Pro 疾速方案已啟用",
                description=(
                    f"伺服器 **{interaction.guild.name}** 已切換至 **PRO 疾速通道**。\n"
                    f"所有指令冷卻已解除（0 秒連發），並同步解鎖 24/7 音樂與無限歌單。\n\n"
                    f"啟用者：{interaction.user.mention}\n"
                    f"啟用時間：`{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC`"
                ),
                color=Colors.PRO,
            )
            embed.set_image(url="attachment://plan_activated.png")
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)
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
        is_pro = await speed_tier.is_guild_pro_fast(db, interaction.guild_id)
        if is_pro:
            return True

        # 未啟用 Pro，顯示 3.0 雙方案圖片對比卡片
        img_buf = await render_plan_card(interaction.guild.name, False)
        file = discord.File(img_buf, filename="plan_compare.png")
        embed = discord.Embed(
            title="⚡ 此功能屬於 Pro 疾速方案",
            description=(
                f"**{interaction.guild.name}** 目前使用 **FREE 標準方案**。\n"
                f"升級 **PRO 疾速方案** 即可享 0 秒指令連發、24/7 音樂不斷線與無限歌單解析。"
            ),
            color=Colors.PRO,
        )
        embed.set_image(url="attachment://plan_compare.png")
        embed.set_footer(text="倉鼠勇者 3.0 • 雙方案疾速引擎")
        
        pro_cog = interaction.client.cogs.get("Pro")
        view = ProPromotionView(pro_cog)
        
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, file=file, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, file=file, view=view, ephemeral=True)
        return False

    async def _send_plan_panel(self, interaction: discord.Interaction):
        """發送 3.0 雙方案對比圖卡與操作按鈕"""
        if not interaction.guild:
            return await interaction.response.send_message("❌ 此指令僅限在伺服器中使用。", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        is_pro = await speed_tier.is_guild_pro_fast(self.bot.db, interaction.guild_id)
        view = ProPromotionView(self, support_url=self.support_url)

        exp_text = ""
        if is_pro:
            async with self.bot.db.db.execute(
                "SELECT expires_at FROM pro_guilds WHERE guild_id = ?",
                (interaction.guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
            exp_text = row["expires_at"][:10] if (row and row["expires_at"]) else "永久有效"

        img_buf = await render_plan_card(interaction.guild.name, is_pro, exp_text)
        file = discord.File(img_buf, filename="hamster_plan_3_0.png")

        embed = discord.Embed(
            title="⚡ 倉鼠勇者 3.0 — PRO 疾速版已啟用" if is_pro else "⚡ 倉鼠勇者 3.0 — 雙方案對比",
            description=(
                f"目前方案：**{'PRO 疾速版（0 秒連發）' if is_pro else 'FREE 免費版（3.0 秒節流）'}**"
                + (f" • 到期：`{exp_text}`" if is_pro else "\n點擊下方按鈕輸入金鑰即可立即切換至疾速通道。")
            ),
            color=Colors.PRO if is_pro else Colors.PRIMARY,
        )
        embed.set_image(url="attachment://hamster_plan_3_0.png")
        embed.set_footer(text="倉鼠勇者 3.0 • Free / Pro 雙方案系統")
        await interaction.followup.send(embed=embed, file=file, view=view, ephemeral=True)

    @app_commands.command(name="pro", description="查看或啟用本伺服器的 3.0 Pro 疾速方案")
    async def pro_status(self, interaction: discord.Interaction):
        await self._send_plan_panel(interaction)

    @app_commands.command(name="plan", description="查看倉鼠勇者 3.0 免費版與 Pro 疾速版對比圖卡")
    async def plan_status(self, interaction: discord.Interaction):
        await self._send_plan_panel(interaction)

    # ─── 管理指令 (僅限 Bot Owner) ─────────────────────────────────────────

    @app_commands.command(name="pro_admin", description="管理 Pro 激活金鑰 (僅限 Bot 擁有者)")
    @app_commands.choices(action=[
        app_commands.Choice(name="產生金鑰", value="generate"),
        app_commands.Choice(name="批量產生金鑰", value="batch_generate"),
        app_commands.Choice(name="列出未使用的金鑰", value="list_unused"),
        app_commands.Choice(name="列出已使用的金鑰", value="list_used"),
    ])
    @app_commands.describe(
        action="要執行的動作",
        days="金鑰的有效天數 (預設 30 天)",
        count="批量產生的金鑰個數 (僅批量產生時有效，預設 1)",
        key="要刪除或查詢的金鑰 (選填)"
    )
    async def pro_admin(
        self,
        interaction: discord.Interaction,
        action: str,
        days: Optional[int] = 30,
        count: Optional[int] = 1,
        key: Optional[str] = None
    ):
        # 檢查是否為擁有者 (支援 Bot Owner 與 bypass user)
        is_owner = (interaction.user.id == 1437408048934027274)
        if not is_owner:
            try:
                is_owner = await self.bot.is_owner(interaction.user)
            except Exception:
                is_owner = False

        if not is_owner:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("無權限", "只有 Bot 擁有者可以使用此指令。"),
                ephemeral=True
            )

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        db = self.bot.db
        act = action.value if hasattr(action, "value") else str(action)
        act = act.strip().lower()

        try:
            if act in ("generate", "產生金鑰"):
                # 產生金鑰
                new_key = f"HERO-PRO-{uuid.uuid4().hex.upper()[:16]}"
                safe_days = max(1, min(days or 30, 365000))
                await db.add_pro_key(new_key, safe_days)
                
                embed = discord.Embed(
                    title="✨ 成功產生 Pro 激活碼",
                    description=(
                        f"🔑 **激活碼：** `{new_key}`\n"
                        f"📅 **有效天數：** {safe_days} 天\n\n"
                        f"您現在可以將此金鑰分發給用戶使用。"
                    ),
                    color=Colors.SUCCESS
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            elif act in ("batch_generate", "批量產生金鑰"):
                # 批量產生金鑰
                count_val = max(1, min(count or 1, 50))
                safe_days = max(1, min(days or 30, 365000))
                keys = []
                for _ in range(count_val):
                    new_key = f"HERO-PRO-{uuid.uuid4().hex.upper()[:16]}"
                    await db.add_pro_key(new_key, safe_days)
                    keys.append(new_key)
                
                keys_str = "\n".join([f"• `{k}`" for k in keys])
                embed = discord.Embed(
                    title=f"✨ 成功批量產生 {count_val} 組 Pro 激活碼",
                    description=(
                        f"📅 **每組有效天數：** {safe_days} 天\n\n"
                        f"🔑 **激活碼清單：**\n{keys_str}\n\n"
                        f"您現在可以將這些金鑰分發給用戶使用。"
                    ),
                    color=Colors.SUCCESS
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            elif act in ("list_unused", "列出未使用的金鑰", "list"):
                unused = await db.get_pro_keys()
                if not unused:
                    return await interaction.followup.send("目前沒有未使用的金鑰。", ephemeral=True)
                
                lines = []
                for r in unused:
                    k = r[0] if isinstance(r, (tuple, list)) else r["key"]
                    d = r[1] if isinstance(r, (tuple, list)) else r["expires_in_days"]
                    c = r[2] if isinstance(r, (tuple, list)) else r["created_at"]
                    created_display = str(c)[:19].replace("T", " ")
                    lines.append(f"• `{k}` ({d} 天) - 建立於: `{created_display}`")

                text = "\n".join(lines)
                if len(text) > 3800:
                    text = text[:3800] + f"\n... 以及更多金鑰 (共 {len(unused)} 組)"

                embed = discord.Embed(
                    title=f"📋 未使用的 Pro 金鑰列表 (共 {len(unused)} 組)",
                    description=text,
                    color=Colors.PRIMARY
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            elif act in ("list_used", "列出已使用的金鑰"):
                used = await db.get_used_keys()
                if not used:
                    return await interaction.followup.send("目前沒有已被使用的金鑰。", ephemeral=True)
                
                lines = []
                for r in used:
                    k = r[0] if isinstance(r, (tuple, list)) else r["key"]
                    g = r[1] if isinstance(r, (tuple, list)) else r["guild_id"]
                    u = r[2] if isinstance(r, (tuple, list)) else r["user_id"]
                    t = r[3] if isinstance(r, (tuple, list)) else r["used_at"]
                    used_display = str(t)[:19].replace("T", " ")
                    lines.append(f"• `{k}` - 伺服器: `{g}` (由 <@{u}> 使用) - 使用於: `{used_display}`")

                text = "\n".join(lines)
                if len(text) > 3800:
                    text = text[:3800] + f"\n... 以及更多記錄 (共 {len(used)} 筆)"

                embed = discord.Embed(
                    title=f"📋 已使用的 Pro 金鑰歷史 (共 {len(used)} 筆)",
                    description=text,
                    color=Colors.PRIMARY
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            else:
                await interaction.followup.send(f"❌ 未知的動作：`{act}`", ephemeral=True)

        except Exception as e:
            embed = EmbedFactory.error("執行失敗", f"執行 `{act}` 發生錯誤：`{e}`")
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Pro(bot))
