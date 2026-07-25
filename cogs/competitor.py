"""
競爭者成員名單系統 Cog
提供部署成員名單、新增成員與移除成員功能，並自動同步更新精美 Embed 排版。
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from config import Colors, Emoji
from utils.embeds import EmbedFactory


class CompetitorSystem(commands.Cog):
    """競爭者/對手成員名單管理系統"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 核心更新方法
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def update_roster_message(self, guild: discord.Guild) -> bool:
        """重新渲染並更新/發送競爭者成員名單"""
        # 1. 取得設定
        settings = await self.db.get_competitor_settings(guild.id)
        if not settings or not settings.get('channel_id'):
            return False

        channel = guild.get_channel(settings['channel_id'])
        if not channel:
            return False

        # 2. 取得所有成員
        competitors = await self.db.get_competitors(guild.id)

        # 3. 建立精美的 Embed
        embed = discord.Embed(
            title="👥 ｜ 競爭者成員名單",
            description="本名單為戰隊記錄之競爭者成員列表，當人員異動時將即時同步更新。✨\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
            color=Colors.GAME,
            timestamp=datetime.now(timezone.utc)
        )
        
        # 右上角縮圖，依據使用者提供現成圖片
        embed.set_thumbnail(url="https://r2.uploads.tw/2026/07/2SVewGESVT.webp")

        desc_lines = []
        valid_uids = []

        for idx, comp in enumerate(competitors, 1):
            discord_id = comp['discord_id']
            roblox_id = comp['roblox_id']
            
            # 以精美的清單樣式顯示，使用 bold Discord mention 和帶背景標籤的 Roblox ID
            desc_lines.append(
                f"`{idx:02d}` ｜ <@{discord_id}>\n"
                f"↳ ✧ **Roblox ID**: `{roblox_id}`\n"
                f"───────────────────"
            )
            valid_uids.append(discord_id)

        if not desc_lines:
            embed.description += "*目前成員名單為空，請管理員使用 `/rivals` 指令登錄新成員！*"
        else:
            embed.description += "\n".join(desc_lines)

        embed.description += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        embed.set_footer(
            text=f"戰隊總人數：{len(valid_uids)} 人 ｜ 隨時自動同步",
            icon_url=self.bot.user.display_avatar.url if self.bot.user else None
        )

        # 4. 更新或發送訊息
        msg = None
        if settings.get('message_id'):
            try:
                msg = await channel.fetch_message(settings['message_id'])
                await msg.edit(embed=embed)
            except discord.NotFound:
                # 原訊息不存在，重新發送並更新設定
                msg = await channel.send(embed=embed)
                await self.db.set_competitor_settings(guild.id, channel.id, msg.id)
            except discord.Forbidden:
                # 權限不足，直接回傳 False
                return False
        else:
            msg = await channel.send(embed=embed)
            await self.db.set_competitor_settings(guild.id, channel.id, msg.id)

        return True

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Slash Commands (單一指令解決方案)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="rivals", description="競爭者成員名單管理系統")
    @app_commands.choices(action=[
        app_commands.Choice(name="部署成員名單 (deploy)", value="deploy"),
        app_commands.Choice(name="新增成員 (add)", value="add"),
        app_commands.Choice(name="移除成員 (remove)", value="remove"),
    ])
    @app_commands.describe(
        action="要執行的動作",
        member="Discord 使用者 (新增或移除成員時必填)",
        roblox_id="Roblox 帳號 (新增成員時必填)",
        channel="部署名單的目標頻道 (部署成員名單時必填)"
    )
    async def rivals_cmd(
        self,
        interaction: discord.Interaction,
        action: str,
        member: discord.User = None,
        roblox_id: str = None,
        channel: discord.TextChannel = None
    ):
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)

        if action == "deploy":
            target_channel = channel or interaction.channel
            # 寫入暫時的 channel_id 與 message_id
            await self.db.set_competitor_settings(guild.id, target_channel.id, 0)
            
            success = await self.update_roster_message(guild)
            if success:
                await interaction.followup.send(f"✅ 已成功將競爭者成員名單部署至 {target_channel.mention}！", ephemeral=True)
            else:
                await interaction.followup.send("❌ 部署失敗，請確認機器人在此頻道具有「發送訊息」與「嵌入連結」權限！", ephemeral=True)

        elif action == "add":
            if not member or not roblox_id:
                return await interaction.followup.send(
                    embed=EmbedFactory.error("規格錯誤", "新增成員時，請務必填寫 `member` (Discord 使用者) 與 `roblox_id` (Roblox 帳號)！"),
                    ephemeral=True
                )
            
            # 新增到資料庫
            await self.db.add_competitor(guild.id, member.id, roblox_id)
            
            # 自動同步更新已部署的 Roster 訊息
            await self.update_roster_message(guild)
            
            embed = EmbedFactory.success(
                "新增成功", 
                f"已成功將 {member.mention} (Roblox: `{roblox_id}`) 新增至競爭者名單！"
            )
            embed.set_thumbnail(url="https://r2.uploads.tw/2026/07/2SVewGESVT.webp")
            await interaction.followup.send(embed=embed, ephemeral=True)

        elif action == "remove":
            if not member:
                return await interaction.followup.send(
                    embed=EmbedFactory.error("規格錯誤", "移除成員時，請務必指定 `member` (Discord 使用者)！"),
                    ephemeral=True
                )

            # 從資料庫移除
            removed = await self.db.remove_competitor(guild.id, member.id)
            if not removed:
                return await interaction.followup.send(
                    embed=EmbedFactory.error("移除失敗", f"在競爭者名單中找不到 {member.mention} 的登錄紀錄。"),
                    ephemeral=True
                )
            
            # 自動同步更新已部署的 Roster 訊息
            await self.update_roster_message(guild)
            
            embed = EmbedFactory.success(
                "移除成功",
                f"已成功將 {member.mention} 自競爭者名單中移除！"
            )
            embed.set_thumbnail(url="https://r2.uploads.tw/2026/07/2SVewGESVT.webp")
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CompetitorSystem(bot))
