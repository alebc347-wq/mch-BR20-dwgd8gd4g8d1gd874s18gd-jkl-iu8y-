"""
抽獎系統 Cog
建立、參加、結束、重抽抽獎
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import random
import json
from datetime import datetime, timezone, timedelta

from config import Colors, Emoji, parse_time, format_timedelta
from utils.embeds import EmbedFactory


class GiveawayJoinButton(discord.ui.View):
    """抽獎參加按鈕"""
    def __init__(self, giveaway_id: int):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="🎉 參加抽獎", style=discord.ButtonStyle.success, custom_id="giveaway_join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = interaction.client.db
        result = await db.add_giveaway_entry(self.giveaway_id, interaction.user.id)
        
        if result:
            await interaction.response.send_message(
                f"{Emoji.PARTY} 你已成功參加抽獎！",
                ephemeral=True,
            )
            
            # 更新 Embed 中的參加人數
            giveaway = await db.get_giveaway(self.giveaway_id)
            if giveaway:
                entries = json.loads(giveaway["entries"])
                guild = interaction.guild
                host = guild.get_member(giveaway["host_id"])
                
                ends_at = datetime.fromisoformat(giveaway["ends_at"])
                remaining = ends_at - datetime.now(timezone.utc)
                remaining_str = format_timedelta(remaining) if remaining.total_seconds() > 0 else "即將結束"
                
                embed = EmbedFactory.giveaway(
                    prize=giveaway["prize"],
                    host=host or interaction.user,
                    duration=remaining_str,
                    winners=giveaway["winners_count"],
                    entries=len(entries),
                )
                
                try:
                    await interaction.message.edit(embed=embed)
                except discord.Forbidden:
                    pass
        else:
            await interaction.response.send_message(
                "你已經參加過了！",
                ephemeral=True,
            )


class Giveaway(commands.GroupCog, name="giveaway", description="🎁 伺服器抽獎系統"):
    """抽獎系統"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        """定期檢查到期的抽獎"""
        if not getattr(self.bot, "is_active_node", True):
            return

        for guild in self.bot.guilds:
            try:
                active = await self.db.get_active_giveaways(guild.id)
                for giveaway_row in active:
                    giveaway = dict(giveaway_row)
                    ends_at = datetime.fromisoformat(giveaway["ends_at"])
                    
                    if datetime.now(timezone.utc) >= ends_at:
                        await self._end_giveaway(giveaway)
            except Exception as e:
                print(f"Error checking giveaways for guild {guild.id}: {e}")

    @check_giveaways.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    async def _end_giveaway(self, giveaway: dict):
        """結束抽獎並選出贏家"""
        guild = self.bot.get_guild(giveaway["guild_id"])
        if not guild:
            return
        
        channel = guild.get_channel(giveaway["channel_id"])
        if not channel:
            return
        
        entries = json.loads(giveaway["entries"])
        winners_count = giveaway["winners_count"]
        
        # 選出贏家
        winners = []
        if entries:
            winner_ids = random.sample(entries, min(winners_count, len(entries)))
            for wid in winner_ids:
                member = guild.get_member(wid)
                if member:
                    winners.append(member)
        
        # 更新原訊息
        try:
            message = await channel.fetch_message(giveaway["message_id"])
            
            embed = EmbedFactory.giveaway_ended(
                prize=giveaway["prize"],
                winners=winners,
                entries=len(entries),
            )
            
            # 停用按鈕
            disabled_view = discord.ui.View()
            disabled_btn = discord.ui.Button(
                label="🎉 抽獎已結束",
                style=discord.ButtonStyle.secondary,
                disabled=True,
            )
            disabled_view.add_item(disabled_btn)
            
            await message.edit(embed=embed, view=disabled_view)
        except (discord.NotFound, discord.Forbidden):
            pass
        
        # 發送獲獎公告
        if winners:
            winner_mentions = " ".join([w.mention for w in winners])
            announce_embed = discord.Embed(
                title=f"{Emoji.TROPHY} 抽獎結果！",
                description=f"**{Emoji.GIFT} 獎品：{giveaway['prize']}**\n\n{Emoji.CROWN} 恭喜 {winner_mentions} 中獎！",
                color=Colors.GIVEAWAY,
            )
            try:
                await channel.send(content=winner_mentions, embed=announce_embed)
            except discord.Forbidden:
                pass
        
        await self.db.end_giveaway(giveaway["id"])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    giveaway_group = app_commands.Group(name="giveaway", description="抽獎系統")

    @giveaway_group.command(name="start", description="開始抽獎")
    @app_commands.describe(
        prize="獎品名稱",
        duration="持續時間 (例: 1h, 1d, 30min)",
        winners="中獎人數",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_start(self, interaction: discord.Interaction, prize: str, duration: str, winners: int = 1):
        td = parse_time(duration)
        if td is None:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("時間格式錯誤", "正確格式：`30min` / `1h` / `1d`"),
                ephemeral=True,
            )
        
        ends_at = datetime.now(timezone.utc) + td
        duration_str = format_timedelta(td)
        
        embed = EmbedFactory.giveaway(
            prize=prize,
            host=interaction.user,
            duration=duration_str,
            winners=winners,
            entries=0,
        )
        
        # 先發送取得 message ID
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        
        # 儲存到資料庫
        giveaway_id = await self.db.create_giveaway(
            guild_id=interaction.guild.id,
            channel_id=interaction.channel.id,
            message_id=message.id,
            host_id=interaction.user.id,
            prize=prize,
            winners_count=winners,
            ends_at=ends_at.isoformat(),
        )
        
        # 添加按鈕
        view = GiveawayJoinButton(giveaway_id)
        await message.edit(view=view)

    @giveaway_group.command(name="end", description="手動結束抽獎")
    @app_commands.describe(giveaway_id="抽獎 ID")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_end(self, interaction: discord.Interaction, giveaway_id: int):
        giveaway = await self.db.get_giveaway(giveaway_id)
        
        if not giveaway:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("找不到抽獎", f"ID `{giveaway_id}` 不存在。"),
                ephemeral=True,
            )
        
        if giveaway["ended"]:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("抽獎已結束"),
                ephemeral=True,
            )
        
        await interaction.response.defer()
        await self._end_giveaway(giveaway)
        await interaction.followup.send(embed=EmbedFactory.success("抽獎已結束", f"抽獎 #{giveaway_id} 已手動結束。"))

    @giveaway_group.command(name="reroll", description="重新抽獎")
    @app_commands.describe(giveaway_id="抽獎 ID")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_reroll(self, interaction: discord.Interaction, giveaway_id: int):
        giveaway = await self.db.get_giveaway(giveaway_id)
        
        if not giveaway:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("找不到抽獎"),
                ephemeral=True,
            )
        
        entries = json.loads(giveaway["entries"])
        if not entries:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("沒有參加者"),
                ephemeral=True,
            )
        
        winners_count = giveaway["winners_count"]
        winner_ids = random.sample(entries, min(winners_count, len(entries)))
        
        winners = []
        for wid in winner_ids:
            member = interaction.guild.get_member(wid)
            if member:
                winners.append(member)
        
        if winners:
            winner_mentions = " ".join([w.mention for w in winners])
            embed = discord.Embed(
                title=f"{Emoji.TROPHY} 重新抽獎結果！",
                description=f"**{Emoji.GIFT} 獎品：{giveaway['prize']}**\n\n{Emoji.CROWN} 新的中獎者：{winner_mentions}",
                color=Colors.GIVEAWAY,
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                embed=EmbedFactory.error("找不到有效的中獎者"),
            )

    @giveaway_group.command(name="list", description="列出進行中的抽獎")
    async def giveaway_list(self, interaction: discord.Interaction):
        active = await self.db.get_active_giveaways(interaction.guild.id)
        
        if not active:
            return await interaction.response.send_message(
                embed=EmbedFactory.info("沒有進行中的抽獎"),
                ephemeral=True,
            )
        
        embed = discord.Embed(
            title=f"{Emoji.PARTY} 進行中的抽獎",
            color=Colors.GIVEAWAY,
        )
        
        for g in active:
            giveaway = dict(g)
            entries = json.loads(giveaway["entries"])
            ends_at = datetime.fromisoformat(giveaway["ends_at"])
            remaining = ends_at - datetime.now(timezone.utc)
            remaining_str = format_timedelta(remaining) if remaining.total_seconds() > 0 else "即將結束"
            
            embed.add_field(
                name=f"#{giveaway['id']} — {giveaway['prize']}",
                value=(
                    f"**中獎人數：** `{giveaway['winners_count']}`\n"
                    f"**參加人數：** `{len(entries)}`\n"
                    f"**剩餘時間：** {remaining_str}"
                ),
                inline=False,
            )
        
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
