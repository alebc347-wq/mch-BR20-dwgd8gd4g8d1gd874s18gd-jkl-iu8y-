"""
抽獎系統 Cog
建立、參加、結束、重抽抽獎
支援：排程倒數預告、需要身份組、禁止身份組
"""

import re
import discord
from discord import app_commands
from discord.ext import commands, tasks
import random
import json
from datetime import datetime, timezone, timedelta

from config import Colors, Emoji, parse_time, format_timedelta
from utils.embeds import EmbedFactory

# 台灣時區 UTC+8
TZ_TW = timezone(timedelta(hours=8))


def parse_start_at(time_str: str) -> datetime | None:
    """
    解析台灣時間字串為 UTC datetime。
    支援格式：
      2026/8/5 pm 7:00
      2026/8/5 am 12:00
      2026-8-5 pm 7:30
    """
    # 正規化分隔符與空白
    s = time_str.strip().replace("-", "/")
    # 嘗試匹配 yyyy/m/d [am|pm] h:mm
    pattern = re.compile(
        r"(\d{4})/(\d{1,2})/(\d{1,2})\s+(am|pm)\s+(\d{1,2}):(\d{2})",
        re.IGNORECASE,
    )
    m = pattern.match(s)
    if not m:
        return None

    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    meridiem = m.group(4).lower()
    hour, minute = int(m.group(5)), int(m.group(6))

    # am/pm → 24h
    if meridiem == "am":
        if hour == 12:
            hour = 0
    else:  # pm
        if hour != 12:
            hour += 12

    try:
        dt_tw = datetime(year, month, day, hour, minute, 0, tzinfo=TZ_TW)
    except ValueError:
        return None

    return dt_tw.astimezone(timezone.utc)


def format_tw_time(dt_utc: datetime) -> str:
    """將 UTC datetime 轉為台灣時間字串（用於 Embed 顯示）。"""
    dt_tw = dt_utc.astimezone(TZ_TW)
    hour = dt_tw.hour
    minute = dt_tw.minute
    if hour < 12:
        meridiem = "上午"
        h12 = hour if hour != 0 else 12
    else:
        meridiem = "下午"
        h12 = hour - 12 if hour != 12 else 12
    return f"{dt_tw.year}/{dt_tw.month}/{dt_tw.day} {meridiem} {h12}:{minute:02d}（台灣時間）"


def _role_hint_lines(required_role_id: int | None, blocked_role_id: int | None, guild: discord.Guild) -> str:
    """回傳身份組限制說明字串（供 Embed description 使用）。"""
    lines = []
    if required_role_id:
        r = guild.get_role(required_role_id)
        name = r.mention if r else f"<@&{required_role_id}>"
        lines.append(f"🔒 **需要身份組：{name}**")
    if blocked_role_id:
        r = guild.get_role(blocked_role_id)
        name = r.mention if r else f"<@&{blocked_role_id}>"
        lines.append(f"🚫 **禁止身份組：{name}**")
    return "\n".join(lines)


class GiveawayJoinButton(discord.ui.View):
    """抽獎參加按鈕"""
    def __init__(self, giveaway_id: int):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="🎉 參加抽獎", style=discord.ButtonStyle.success, custom_id="giveaway_join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = interaction.client.db
        giveaway = await db.get_giveaway(self.giveaway_id)
        if not giveaway:
            return await interaction.response.send_message("❌ 找不到此抽獎，可能已被刪除。", ephemeral=True)

        member = interaction.user
        guild = interaction.guild

        # ── 1. 身份組檢查 ──────────────────────────────────────
        blocked_role_id = giveaway.get("blocked_role_id")
        required_role_id = giveaway.get("required_role_id")

        if blocked_role_id:
            blocked_role = guild.get_role(blocked_role_id)
            if blocked_role and blocked_role in member.roles:
                return await interaction.response.send_message(
                    f"🚫 你無法參加此抽獎！\n擁有 **{blocked_role.name}** 身份組的人不能參加。",
                    ephemeral=True,
                )

        if required_role_id:
            required_role = guild.get_role(required_role_id)
            if required_role and required_role not in member.roles:
                return await interaction.response.send_message(
                    f"🔒 你沒有資格參加此抽獎！\n需要擁有 **{required_role.name}** 身份組才能參加。",
                    ephemeral=True,
                )

        # ── 2. 加入抽獎 ────────────────────────────────────────
        result = await db.add_giveaway_entry(self.giveaway_id, member.id)

        if result:
            await interaction.response.send_message(
                f"{Emoji.PARTY} 你已成功參加抽獎！",
                ephemeral=True,
            )

            # 更新 Embed 中的參加人數
            giveaway = await db.get_giveaway(self.giveaway_id)
            if giveaway:
                entries = json.loads(giveaway["entries"])
                host = guild.get_member(giveaway["host_id"])

                ends_at = datetime.fromisoformat(giveaway["ends_at"])
                remaining = ends_at - datetime.now(timezone.utc)
                remaining_str = format_timedelta(remaining) if remaining.total_seconds() > 0 else "即將結束"

                role_hint = _role_hint_lines(
                    giveaway.get("required_role_id"),
                    giveaway.get("blocked_role_id"),
                    guild,
                )

                embed = EmbedFactory.giveaway(
                    prize=giveaway["prize"],
                    host=host or member,
                    duration=remaining_str,
                    winners=giveaway["winners_count"],
                    entries=len(entries),
                    role_hint=role_hint,
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
        self.check_scheduled_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()
        self.check_scheduled_giveaways.cancel()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 後台任務
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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

    @tasks.loop(seconds=30)
    async def check_scheduled_giveaways(self):
        """定期檢查排程抽獎（倒數預告）"""
        if not getattr(self.bot, "is_active_node", True):
            return

        try:
            pending = await self.db.get_pending_scheduled_giveaways()
        except Exception as e:
            print(f"Error fetching scheduled giveaways: {e}")
            return

        now = datetime.now(timezone.utc)

        for row in pending:
            sg = dict(row)
            try:
                starts_at = datetime.fromisoformat(sg["starts_at"])
                guild = self.bot.get_guild(sg["guild_id"])
                if not guild:
                    continue

                channel = guild.get_channel(sg["channel_id"])
                if not channel:
                    continue

                try:
                    message = await channel.fetch_message(sg["message_id"])
                except (discord.NotFound, discord.Forbidden):
                    # 預告訊息被刪，直接標記為已啟動避免重試
                    await self.db.launch_scheduled_giveaway(sg["id"])
                    continue

                if now >= starts_at:
                    # ── 時間到了，轉為正式抽獎 ──
                    ends_at = now + timedelta(seconds=sg["duration_seconds"])
                    host = guild.get_member(sg["host_id"])

                    role_hint = _role_hint_lines(
                        sg.get("required_role_id"),
                        sg.get("blocked_role_id"),
                        guild,
                    )

                    embed = EmbedFactory.giveaway(
                        prize=sg["prize"],
                        host=host or guild.me,
                        duration=format_timedelta(timedelta(seconds=sg["duration_seconds"])),
                        winners=sg["winners_count"],
                        entries=0,
                        role_hint=role_hint,
                    )

                    giveaway_id = await self.db.create_giveaway(
                        guild_id=sg["guild_id"],
                        channel_id=sg["channel_id"],
                        message_id=sg["message_id"],
                        host_id=sg["host_id"],
                        prize=sg["prize"],
                        winners_count=sg["winners_count"],
                        ends_at=ends_at.isoformat(),
                        required_role_id=sg.get("required_role_id"),
                        blocked_role_id=sg.get("blocked_role_id"),
                    )

                    view = GiveawayJoinButton(giveaway_id)
                    await message.edit(embed=embed, view=view)
                    await self.db.launch_scheduled_giveaway(sg["id"])

                else:
                    # ── 更新倒數 Embed ──
                    remaining = starts_at - now
                    host = guild.get_member(sg["host_id"])
                    role_hint = _role_hint_lines(
                        sg.get("required_role_id"),
                        sg.get("blocked_role_id"),
                        guild,
                    )
                    embed = self._make_countdown_embed(
                        prize=sg["prize"],
                        host=host or guild.me,
                        starts_at=starts_at,
                        remaining=remaining,
                        winners=sg["winners_count"],
                        role_hint=role_hint,
                    )
                    try:
                        await message.edit(embed=embed)
                    except discord.Forbidden:
                        pass

            except Exception as e:
                print(f"Error processing scheduled giveaway {sg.get('id')}: {e}")

    @check_scheduled_giveaways.before_loop
    async def before_scheduled_check(self):
        await self.bot.wait_until_ready()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 工具方法
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _make_countdown_embed(
        self,
        prize: str,
        host: discord.Member,
        starts_at: datetime,
        remaining: timedelta,
        winners: int,
        role_hint: str = "",
    ) -> discord.Embed:
        """建立倒數預告 Embed。"""
        starts_str = format_tw_time(starts_at)
        remaining_str = format_timedelta(remaining) if remaining.total_seconds() > 0 else "即將開始！"

        desc_parts = [
            f"**{Emoji.GIFT} 獎品：{prize}**",
            f"⏰ **開始時間：** {starts_str}",
            f"⏳ **距離開始：** {remaining_str}",
        ]
        if role_hint:
            desc_parts.append(role_hint)

        embed = discord.Embed(
            title=f"📢 抽獎即將開始！",
            description="\n".join(desc_parts),
            color=Colors.GIVEAWAY,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="**主辦者**", value=host.mention, inline=True)
        embed.add_field(name="**中獎人數**", value=f"`{winners}`", inline=True)
        embed.set_footer(text="時間到後將自動開放參加")
        return embed

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
        required_role="需要擁有此身份組才能參加（可選）",
        blocked_role="擁有此身份組者不能參加（可選）",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_start(
        self,
        interaction: discord.Interaction,
        prize: str,
        duration: str,
        winners: int = 1,
        required_role: discord.Role = None,
        blocked_role: discord.Role = None,
    ):
        td = parse_time(duration)
        if td is None:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("時間格式錯誤", "正確格式：`30min` / `1h` / `1d`"),
                ephemeral=True,
            )

        ends_at = datetime.now(timezone.utc) + td
        duration_str = format_timedelta(td)

        role_hint = _role_hint_lines(
            required_role.id if required_role else None,
            blocked_role.id if blocked_role else None,
            interaction.guild,
        )

        embed = EmbedFactory.giveaway(
            prize=prize,
            host=interaction.user,
            duration=duration_str,
            winners=winners,
            entries=0,
            role_hint=role_hint,
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
            required_role_id=required_role.id if required_role else None,
            blocked_role_id=blocked_role.id if blocked_role else None,
        )

        # 添加按鈕
        view = GiveawayJoinButton(giveaway_id)
        await message.edit(view=view)

    @giveaway_group.command(name="schedule", description="排程抽獎（設定未來開始時間，倒數後自動開始）")
    @app_commands.describe(
        prize="獎品名稱",
        start_at="開始時間，格式：2026/8/5 pm 7:00（台灣時間）",
        duration="抽獎持續時間 (例: 1h, 30min)",
        winners="中獎人數",
        required_role="需要擁有此身份組才能參加（可選）",
        blocked_role="擁有此身份組者不能參加（可選）",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_schedule(
        self,
        interaction: discord.Interaction,
        prize: str,
        start_at: str,
        duration: str,
        winners: int = 1,
        required_role: discord.Role = None,
        blocked_role: discord.Role = None,
    ):
        # 解析開始時間
        starts_at_utc = parse_start_at(start_at)
        if starts_at_utc is None:
            return await interaction.response.send_message(
                embed=EmbedFactory.error(
                    "時間格式錯誤",
                    "請使用格式：`2026/8/5 pm 7:00` 或 `2026/8/5 am 7:30`（台灣時間）",
                ),
                ephemeral=True,
            )

        now = datetime.now(timezone.utc)
        if starts_at_utc <= now:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("時間必須在未來", f"指定時間 `{start_at}` 已過去，請重新設定。"),
                ephemeral=True,
            )

        # 解析持續時間
        td = parse_time(duration)
        if td is None:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("持續時間格式錯誤", "正確格式：`30min` / `1h` / `1d`"),
                ephemeral=True,
            )

        remaining = starts_at_utc - now
        role_hint = _role_hint_lines(
            required_role.id if required_role else None,
            blocked_role.id if blocked_role else None,
            interaction.guild,
        )

        # 發送倒數預告 Embed（無按鈕）
        countdown_embed = self._make_countdown_embed(
            prize=prize,
            host=interaction.user,
            starts_at=starts_at_utc,
            remaining=remaining,
            winners=winners,
            role_hint=role_hint,
        )

        await interaction.response.send_message(embed=countdown_embed)
        message = await interaction.original_response()

        # 儲存排程到資料庫
        await self.db.create_scheduled_giveaway(
            guild_id=interaction.guild.id,
            channel_id=interaction.channel.id,
            message_id=message.id,
            host_id=interaction.user.id,
            prize=prize,
            winners_count=winners,
            duration_seconds=int(td.total_seconds()),
            starts_at=starts_at_utc.isoformat(),
            required_role_id=required_role.id if required_role else None,
            blocked_role_id=blocked_role.id if blocked_role else None,
        )

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

            value_lines = [
                f"**中獎人數：** `{giveaway['winners_count']}`",
                f"**參加人數：** `{len(entries)}`",
                f"**剩餘時間：** {remaining_str}",
            ]
            if giveaway.get("required_role_id"):
                r = interaction.guild.get_role(giveaway["required_role_id"])
                value_lines.append(f"🔒 需要：{r.mention if r else '未知身份組'}")
            if giveaway.get("blocked_role_id"):
                r = interaction.guild.get_role(giveaway["blocked_role_id"])
                value_lines.append(f"🚫 禁止：{r.mention if r else '未知身份組'}")

            embed.add_field(
                name=f"#{giveaway['id']} — {giveaway['prize']}",
                value="\n".join(value_lines),
                inline=False,
            )

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
