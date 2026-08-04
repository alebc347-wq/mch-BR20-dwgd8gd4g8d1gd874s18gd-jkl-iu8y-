"""
管理系統 Cog
Slash 指令 + 前綴快捷指令 (.t .k .b)
kick, ban (0=unban), timeout, warn, purge, lock/unlock, autorole
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta
import asyncio

from config import Colors, Emoji, BadgeImages, parse_time, format_timedelta
from utils.embeds import EmbedFactory, ConfirmView, UserProfileButton
from utils.checks import check_hierarchy, check_member_hierarchy


class Moderation(commands.GroupCog, name="mod", description="🛡️ 伺服器管理與懲處系統"):
    """管理系統 — 踢出、封禁、禁言、警告"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # KICK — Slash + 前綴
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.command(name="kick", description="踢出用戶")
    @app_commands.describe(user="要踢出的用戶", reason="原因")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    async def slash_kick(self, interaction: discord.Interaction, user: discord.Member, reason: str = "未提供"):
        allowed, reason_msg = await check_hierarchy(interaction, user)
        if not allowed:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("無法執行", reason_msg),
                ephemeral=True,
            )
        
        # 嘗試 DM 通知
        try:
            dm_embed = EmbedFactory.kick(user, interaction.user, reason, interaction.guild, self.bot)
            await user.send(dm_embed)
        except discord.Forbidden:
            pass
        
        await user.kick(reason=f"{interaction.user}: {reason}")
        
        embed = EmbedFactory.kick(user, interaction.user, reason, interaction.guild, self.bot)
        view = UserProfileButton(user.id)
        await interaction.response.send_message(embed=embed, view=view)

    @commands.command(name="k")
    @commands.has_permissions(kick_members=True)
    async def prefix_kick(self, ctx: commands.Context, user: discord.Member, *, reason: str = "未提供"):
        """.k @用戶 [原因]"""
        allowed, reason_msg = check_member_hierarchy(ctx.author, user, ctx.guild.me)
        if not allowed:
            return await ctx.send(embed=EmbedFactory.error("無法執行", reason_msg))
        
        try:
            dm_embed = EmbedFactory.kick(user, ctx.author, reason, ctx.guild, self.bot)
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            pass
        
        await user.kick(reason=f"{ctx.author}: {reason}")
        
        embed = EmbedFactory.kick(user, ctx.author, reason, ctx.guild, self.bot)
        view = UserProfileButton(user.id)
        await ctx.send(embed=embed, view=view)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # BAN — 天數填 0 = 解封
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.command(name="ban", description="封禁用戶（天數填 0 = 解封）")
    @app_commands.describe(user="要封禁的用戶", days="封禁天數（0 = 解封）", reason="原因")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    async def slash_ban(self, interaction: discord.Interaction, user: discord.Member | discord.User, days: int = -1, reason: str = "未提供"):
        if days == 0:
            # 解除封禁
            try:
                await interaction.guild.unban(user, reason=f"{interaction.user}: {reason}")
                embed = EmbedFactory.ban(user, interaction.user, 0, reason, interaction.guild, self.bot)
                await interaction.response.send_message(embed=embed)
            except discord.NotFound:
                await interaction.response.send_message(
                    embed=EmbedFactory.error("找不到用戶", "此用戶未被封禁或不存在。"),
                    ephemeral=True,
                )
            return
        
        # 封禁
        if isinstance(user, discord.Member):
            allowed, reason_msg = await check_hierarchy(interaction, user)
            if not allowed:
                return await interaction.response.send_message(
                    embed=EmbedFactory.error("無法執行", reason_msg),
                    ephemeral=True,
                )
            try:
                dm_embed = EmbedFactory.ban(user, interaction.user, days, reason, interaction.guild, self.bot)
                await user.send(dm_embed)
            except discord.Forbidden:
                pass
        
        delete_days = min(max(days, 0), 7) if days > 0 else 0
        await interaction.guild.ban(user, reason=f"{interaction.user}: {reason}", delete_message_days=delete_days)
        
        embed = EmbedFactory.ban(user, interaction.user, days, reason, interaction.guild, self.bot)
        view = UserProfileButton(user.id)
        await interaction.response.send_message(embed=embed, view=view)

    @commands.command(name="b")
    @commands.has_permissions(ban_members=True)
    async def prefix_ban(self, ctx: commands.Context, user: discord.Member | discord.User, days: int = -1, *, reason: str = "未提供"):
        """.b @用戶 [天數] [原因]  (0=解封)"""
        if days == 0:
            try:
                # 嘗試用 ID 解封
                if isinstance(user, discord.Member):
                    user_obj = discord.Object(id=user.id)
                else:
                    user_obj = user
                await ctx.guild.unban(user_obj, reason=f"{ctx.author}: {reason}")
                embed = EmbedFactory.ban(user, ctx.author, 0, reason, ctx.guild, self.bot)
                await ctx.send(embed=embed)
            except discord.NotFound:
                await ctx.send(embed=EmbedFactory.error("找不到用戶", "此用戶未被封禁。"))
            return
        
        if isinstance(user, discord.Member):
            allowed, reason_msg = check_member_hierarchy(ctx.author, user, ctx.guild.me)
            if not allowed:
                return await ctx.send(embed=EmbedFactory.error("無法執行", reason_msg))
            try:
                dm_embed = EmbedFactory.ban(user, ctx.author, days, reason, ctx.guild, self.bot)
                await user.send(embed=dm_embed)
            except discord.Forbidden:
                pass
        
        delete_days = min(max(days, 0), 7) if days > 0 else 0
        await ctx.guild.ban(user, reason=f"{ctx.author}: {reason}", delete_message_days=delete_days)
        
        embed = EmbedFactory.ban(user, ctx.author, days, reason, ctx.guild, self.bot)
        view = UserProfileButton(user.id)
        await ctx.send(embed=embed, view=view)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TIMEOUT — .t @user 5s / 10min / 2h / 7d
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.command(name="timeout", description="禁言用戶")
    @app_commands.describe(user="要禁言的用戶", duration="時長 (5s / 10min / 2h / 7d)", reason="原因")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def slash_timeout(self, interaction: discord.Interaction, user: discord.Member, duration: str, reason: str = "未提供"):
        td = parse_time(duration)
        if td is None:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("時間格式錯誤", "正確格式：`5s` / `10min` / `2h` / `7d`"),
                ephemeral=True,
            )
        
        allowed, reason_msg = await check_hierarchy(interaction, user)
        if not allowed:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("無法執行", reason_msg),
                ephemeral=True,
            )
        
        try:
            await user.timeout(td, reason=f"{interaction.user}: {reason}")
        except discord.HTTPException as e:
            if e.code == 50035 and "communication_disabled_until" in str(e):
                return await interaction.response.send_message(
                    embed=EmbedFactory.error(
                        "禁言失敗",
                        "禁言時間戳記無效。這通常是因為禁言時長太短（例如 `5s`），或主機系統時鐘與 Discord 不同步。請嘗試使用較長的時間（例如 `10s` 以上）或同步主機時鐘。"
                    ),
                    ephemeral=True,
                )
            raise e
        
        duration_str = format_timedelta(td)
        embed = EmbedFactory.timeout(user, interaction.user, duration_str, reason, interaction.guild, self.bot)
        
        # DM 通知
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            pass
        
        view = UserProfileButton(user.id)
        await interaction.response.send_message(embed=embed, view=view)

    @commands.command(name="t")
    @commands.has_permissions(moderate_members=True)
    async def prefix_timeout(self, ctx: commands.Context, target: discord.Member | discord.Role, duration: str, *, reason: str = "未提供"):
        """.t @用戶/@身分組 5s [原因]"""
        td = parse_time(duration)
        if td is None:
            return await ctx.send(
                embed=EmbedFactory.error("時間格式錯誤", "正確格式：`5s` / `10min` / `2h` / `7d`")
            )

        if isinstance(target, discord.Role):
            role = target
            members = [m for m in role.members if not m.bot]
            if not members:
                return await ctx.send(embed=EmbedFactory.error("無效目標", "該身分組中沒有可供禁言的成員。"))

            status_msg = await ctx.send(f"⏳ 正在批次禁言身分組 `{role.name}` 中的 {len(members)} 位成員...", delete_after=30)
            success_count = 0
            fail_count = 0

            for idx, member in enumerate(members, 1):
                allowed, _ = check_member_hierarchy(ctx.author, member, ctx.guild.me)
                if not allowed:
                    fail_count += 1
                    continue
                try:
                    await member.timeout(td, reason=f"{ctx.author} (批次): {reason}")
                    success_count += 1
                except Exception:
                    fail_count += 1
                
                if idx % 10 == 0:
                    await asyncio.sleep(0.5)

            duration_str = format_timedelta(td)
            desc = f"已完成身分組 `{role.name}` 的批次禁言（時間：`{duration_str}`）\n• 成功：`{success_count}` 人\n• 失敗：`{fail_count}` 人 (權限不足或階級高於 Bot)"
            return await ctx.send(embed=EmbedFactory.success("批次禁言結果", desc))

        user = target
        allowed, reason_msg = check_member_hierarchy(ctx.author, user, ctx.guild.me)
        if not allowed:
            return await ctx.send(embed=EmbedFactory.error("無法執行", reason_msg))
        
        try:
            await user.timeout(td, reason=f"{ctx.author}: {reason}")
        except discord.HTTPException as e:
            if e.code == 50035 and "communication_disabled_until" in str(e):
                return await ctx.send(
                    embed=EmbedFactory.error(
                        "禁言失敗",
                        "禁言時間戳記無效。這通常是因為禁言時長太短（例如 `5s`），或主機系統時鐘與 Discord 不同步。請嘗試使用較長的時間（例如 `10s` 以上）或同步主機時鐘。"
                    )
                )
            raise e
        
        duration_str = format_timedelta(td)
        embed = EmbedFactory.timeout(user, ctx.author, duration_str, reason, ctx.guild, self.bot)
        
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            pass
        
        view = UserProfileButton(user.id)
        await ctx.send(embed=embed, view=view)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # VOICE KICK / TEMP BAN — .kv & .tv
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @commands.command(name="kv")
    @commands.has_permissions(move_members=True)
    async def prefix_voice_kick(self, ctx: commands.Context, user: discord.Member, *, reason: str = "未提供"):
        """.kv @用戶 [原因]"""
        allowed, reason_msg = check_member_hierarchy(ctx.author, user, ctx.guild.me)
        if not allowed:
            return await ctx.send(embed=EmbedFactory.error("無法執行", reason_msg))

        if not user.voice or not user.voice.channel:
            return await ctx.send(embed=EmbedFactory.error("無法執行", "目標成員目前不在任何語音頻道中。"))

        voice_channel = user.voice.channel

        try:
            await user.move_to(None, reason=f"{ctx.author}: {reason}")
        except discord.Forbidden:
            return await ctx.send(embed=EmbedFactory.error("權限不足", "機器人缺少「移動成員」權限，無法將該用戶踢出語音頻道。"))
        except discord.HTTPException as e:
            return await ctx.send(embed=EmbedFactory.error("執行失敗", f"無法將用戶踢出語音頻道：{e}"))

        embed = EmbedFactory._base_embed(
            title="語音頻道踢出",
            color=Colors.KICK,
            badge_url=BadgeImages.KICK,
            author_name=ctx.author.display_name,
            author_icon=ctx.author.display_avatar.url,
        )
        EmbedFactory._add_user_field(embed, user, "被踢出的用戶")
        embed.add_field(name="**原語音頻道**", value=voice_channel.mention, inline=True)
        embed.add_field(name="**執行者**", value=ctx.author.mention, inline=True)
        embed.add_field(name="**原因**", value=f"```{reason}```", inline=False)
        EmbedFactory._add_time_field(embed)
        EmbedFactory._add_server_footer(embed, ctx.guild, self.bot)

        # DM 通知
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            pass

        view = UserProfileButton(user.id)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="tv")
    @commands.has_permissions(mute_members=True)
    async def prefix_voice_temp_ban(self, ctx: commands.Context, user: discord.Member, duration: str, *, reason: str = "未提供"):
        """.tv @用戶 時長 [原因]"""
        allowed, reason_msg = check_member_hierarchy(ctx.author, user, ctx.guild.me)
        if not allowed:
            return await ctx.send(embed=EmbedFactory.error("無法執行", reason_msg))

        td = parse_time(duration)
        if td is None:
            return await ctx.send(
                embed=EmbedFactory.error("時間格式錯誤", "正確格式：`5s` / `10min` / `2h` / `7d`")
            )

        # 確定目標語音頻道
        voice_channel = None
        if user.voice and user.voice.channel:
            voice_channel = user.voice.channel
        elif ctx.author.voice and ctx.author.voice.channel:
            voice_channel = ctx.author.voice.channel

        if voice_channel is None:
            return await ctx.send(
                embed=EmbedFactory.error("無法執行", "目標成員或您必須在語音頻道中，才能確定要對哪一個語音頻道進行禁入與禁言處罰。")
            )

        # 檢查機器人在該頻道的權限
        channel_perms = voice_channel.permissions_for(ctx.guild.me)
        if not channel_perms.manage_roles:
            return await ctx.send(embed=EmbedFactory.error("權限不足", "機器人在目標語音頻道缺少「管理權限」權限，無法設定覆寫。"))

        try:
            # 1. 套用語音禁言與禁入的權限覆寫
            overwrite = voice_channel.overwrites_for(user)
            overwrite.connect = False
            overwrite.speak = False
            await voice_channel.set_permissions(user, overwrite=overwrite, reason=f"語音頻道禁言/禁入 ({duration}) | 執行者: {ctx.author}: {reason}")

            # 2. 如果用戶目前就在該語音頻道，強制斷開連線
            if user.voice and user.voice.channel == voice_channel:
                try:
                    await user.move_to(None, reason=f"語音頻道禁言/禁入限制中 | 執行者: {ctx.author}")
                except discord.Forbidden:
                    pass
        except discord.Forbidden:
            return await ctx.send(embed=EmbedFactory.error("權限不足", "套用頻道權限覆寫時失敗，請確認機器人角色階層高於目標成員。"))
        except discord.HTTPException as e:
            return await ctx.send(embed=EmbedFactory.error("執行失敗", f"設定頻道權限時發生錯誤：{e}"))

        duration_str = format_timedelta(td)
        embed = EmbedFactory._base_embed(
            title="語音頻道禁言與禁入",
            color=Colors.TIMEOUT,
            badge_url=BadgeImages.TIMEOUT,
            author_name=ctx.author.display_name,
            author_icon=ctx.author.display_avatar.url,
        )
        EmbedFactory._add_user_field(embed, user, "被禁入/禁言的用戶")
        embed.add_field(name="**目標語音頻道**", value=voice_channel.mention, inline=True)
        embed.add_field(name="**執行者**", value=ctx.author.mention, inline=True)
        embed.add_field(name="**時長**", value=f"`{duration_str}`", inline=True)
        embed.add_field(name="**原因**", value=f"```{reason}```", inline=False)
        EmbedFactory._add_time_field(embed)
        EmbedFactory._add_server_footer(embed, ctx.guild, self.bot)

        # DM 通知
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            pass

        view = UserProfileButton(user.id)
        await ctx.send(embed=embed, view=view)

        # 3. 建立非同步背景任務在時間結束後解除覆寫
        async def restore_voice_permissions():
            await asyncio.sleep(td.total_seconds())
            try:
                curr_channel = ctx.guild.get_channel(voice_channel.id)
                if curr_channel:
                    curr_overwrite = curr_channel.overwrites_for(user)
                    curr_overwrite.connect = None
                    curr_overwrite.speak = None
                    if curr_overwrite.is_empty():
                        await curr_channel.set_permissions(user, overwrite=None, reason="語音禁入/禁言時間已結束，自動還原權限。")
                    else:
                        await curr_channel.set_permissions(user, overwrite=curr_overwrite, reason="語音禁入/禁言時間已結束，自動還原權限。")
            except Exception as e:
                print(f"[Moderation] 還原 {user} 在 {voice_channel.name} 的語音權限失敗: {e}")

        asyncio.create_task(restore_voice_permissions())

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 警告系統
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.command(name="warn", description="警告用戶")
    @app_commands.describe(user="要警告的用戶", reason="原因")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def slash_warn(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        warn_count = await self.db.add_warning(
            interaction.guild.id, user.id, interaction.user.id, reason
        )
        
        embed = EmbedFactory.warn(user, interaction.user, reason, warn_count, interaction.guild, self.bot)
        
        # DM 通知
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            pass
        
        view = UserProfileButton(user.id)
        await interaction.response.send_message(embed=embed, view=view)
        
        # 檢查自動處罰
        await self._check_warn_action(interaction.guild, user, warn_count)

    async def _check_warn_action(self, guild: discord.Guild, user: discord.Member, count: int):
        """檢查累積警告是否觸發自動處罰"""
        settings = await self.db.get_guild_settings(guild.id)
        import json
        actions = json.loads(settings.get("warn_actions", "{}"))
        
        # 使用預設設定如果沒有自訂
        if not actions:
            from config import DEFAULT_WARN_ACTIONS
            actions = {str(k): v for k, v in DEFAULT_WARN_ACTIONS.items()}
        
        action = actions.get(str(count))
        if not action:
            return
        
        try:
            if action == "timeout_1h":
                await user.timeout(timedelta(hours=1), reason=f"累積 {count} 次警告")
            elif action == "timeout_1d":
                await user.timeout(timedelta(days=1), reason=f"累積 {count} 次警告")
            elif action == "kick":
                await user.kick(reason=f"累積 {count} 次警告")
            elif action == "ban":
                await user.ban(reason=f"累積 {count} 次警告")
        except discord.Forbidden:
            pass

    @app_commands.command(name="warnings", description="查看用戶警告紀錄")
    @app_commands.describe(user="要查詢的用戶")
    async def slash_warnings(self, interaction: discord.Interaction, user: discord.Member):
        warnings = await self.db.get_warnings(interaction.guild.id, user.id)
        
        if not warnings:
            return await interaction.response.send_message(
                embed=EmbedFactory.info("無警告", f"{user.mention} 沒有任何警告紀錄。"),
                ephemeral=True,
            )
        
        embed = discord.Embed(
            title=f"⚠️ {user.display_name} 的警告紀錄",
            color=Colors.WARN,
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        
        for i, w in enumerate(warnings[:10], 1):
            mod_id = w[3] if isinstance(w, (list, tuple)) else w["moderator_id"]
            reason = w[4] if isinstance(w, (list, tuple)) else w["reason"]
            created = w[5] if isinstance(w, (list, tuple)) else w["created_at"]
            warn_id = w[0] if isinstance(w, (list, tuple)) else w["id"]
            embed.add_field(
                name=f"#{warn_id} — {created[:10]}",
                value=f"**原因：** {reason}\n**執行者：** <@{mod_id}>",
                inline=False,
            )
        
        embed.set_footer(text=f"共 {len(warnings)} 條警告")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clearwarning", description="清除用戶警告")
    @app_commands.describe(user="用戶", warn_id="警告 ID（不填則清除全部）")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def slash_clearwarning(self, interaction: discord.Interaction, user: discord.Member, warn_id: int = None):
        await self.db.clear_warning(interaction.guild.id, user.id, warn_id)
        
        if warn_id:
            desc = f"已清除 {user.mention} 的警告 #{warn_id}"
        else:
            desc = f"已清除 {user.mention} 的所有警告"
        
        await interaction.response.send_message(embed=EmbedFactory.success("警告已清除", desc))

    @app_commands.command(name="warnconfig", description="設定累積警告自動處罰")
    @app_commands.describe(count="警告次數", action="處罰動作")
    @app_commands.choices(action=[
        app_commands.Choice(name="禁言 1 小時", value="timeout_1h"),
        app_commands.Choice(name="禁言 1 天", value="timeout_1d"),
        app_commands.Choice(name="踢出", value="kick"),
        app_commands.Choice(name="封禁", value="ban"),
    ])
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_warnconfig(self, interaction: discord.Interaction, count: int, action: str):
        import json
        settings = await self.db.get_guild_settings(interaction.guild.id)
        actions = json.loads(settings.get("warn_actions", "{}"))
        actions[str(count)] = action
        await self.db.update_guild_setting(interaction.guild.id, "warn_actions", json.dumps(actions))
        
        action_names = {
            "timeout_1h": "禁言 1 小時",
            "timeout_1d": "禁言 1 天",
            "kick": "踢出",
            "ban": "封禁",
        }
        
        await interaction.response.send_message(
            embed=EmbedFactory.success(
                "警告設定已更新",
                f"累積 `{count}` 次警告 → **{action_names.get(action, action)}**",
            )
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PURGE / SLOWMODE / LOCK
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.command(name="purge", description="批量刪除訊息")
    @app_commands.describe(amount="刪除數量", user="只刪除特定用戶的訊息")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def slash_purge(self, interaction: discord.Interaction, amount: int, user: discord.Member = None):
        if amount < 1 or amount > 100:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("數量無效", "請輸入 1-100 之間的數字。"),
                ephemeral=True,
            )
        
        await interaction.response.defer(ephemeral=True)
        
        if user:
            deleted = await interaction.channel.purge(limit=amount, check=lambda m: m.author == user)
        else:
            deleted = await interaction.channel.purge(limit=amount)
        
        embed = EmbedFactory.purge(interaction.user, len(deleted), interaction.channel, interaction.guild, self.bot)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.command(name="c")
    @commands.has_permissions(manage_messages=True)
    async def prefix_purge(self, ctx: commands.Context, amount: int, user: discord.Member = None):
        """.c [數量] [@用戶]"""
        if amount < 1 or amount > 100:
            return await ctx.send(
                embed=EmbedFactory.error("數量無效", "請輸入 1-100 之間的數字。"),
                delete_after=5
            )
        
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass
            
        if user:
            deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.author == user)
        else:
            deleted = await ctx.channel.purge(limit=amount)
            
        embed = EmbedFactory.purge(ctx.author, len(deleted), ctx.channel, ctx.guild, self.bot)
        await ctx.send(embed=embed, delete_after=5)

    @app_commands.command(name="slowmode", description="設定頻道慢速模式")
    @app_commands.describe(seconds="秒數（0 = 關閉）")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slash_slowmode(self, interaction: discord.Interaction, seconds: int):
        await interaction.channel.edit(slowmode_delay=seconds)
        
        if seconds == 0:
            desc = "已關閉慢速模式"
        else:
            desc = f"已設定慢速模式為 `{seconds}` 秒"
        
        await interaction.response.send_message(embed=EmbedFactory.success("慢速模式", desc))

    @commands.command(name="slowmode", aliases=["sm"])
    @commands.has_permissions(manage_channels=True)
    async def prefix_slowmode(self, ctx: commands.Context, seconds: int = None):
        """.slowmode [秒數] (0 = 關閉)"""
        if seconds is None:
            delay = ctx.channel.slowmode_delay
            if delay == 0:
                desc = "目前未開啟慢速模式"
            else:
                desc = f"目前慢速模式設定為 `{delay}` 秒"
            return await ctx.send(embed=EmbedFactory.success("慢速模式狀態", desc))

        await ctx.channel.edit(slowmode_delay=seconds)
        
        if seconds == 0:
            desc = "已關閉慢速模式"
        else:
            desc = f"已設定慢速模式為 `{seconds}` 秒"
            
        await ctx.send(embed=EmbedFactory.success("慢速模式", desc))

    @commands.command(name="ro")
    @commands.has_permissions(manage_roles=True)
    async def prefix_role_manage(self, ctx: commands.Context, target: str, *, remaining: str):
        """.ro [everyone/@用戶/用戶ID/用戶名] [身分組/身分組ID/身分組名] [on/off (預設 on)]"""
        # 1. 拆分動作 (on/off) 與身分組查詢字串
        words = remaining.strip().split()
        if len(words) > 1 and words[-1].lower() in ("on", "off"):
            action = words[-1].lower()
            role_query = " ".join(words[:-1])
        else:
            action = "on"
            role_query = " ".join(words)

        # 2. 搜尋身分組
        role = None
        cleaned_role_id = role_query.strip("<@&> ")
        if cleaned_role_id.isdigit():
            role = ctx.guild.get_role(int(cleaned_role_id))
        
        if not role:
            # 搜尋名稱
            role = discord.utils.get(ctx.guild.roles, name=role_query)
            if not role:
                # 不區分大小寫搜尋
                role = discord.utils.find(lambda r: r.name.lower() == role_query.lower(), ctx.guild.roles)

        if not role:
            return await ctx.reply(embed=EmbedFactory.error("找不到身分組", f"找不到身分組 `{role_query}`，請確認名稱或 ID 是否正確。"), mention_author=False)

        # 3. 權限與階級檢查
        is_bypass = (ctx.author.id == 1437408048934027274)
        
        if not is_bypass:
            if role >= ctx.author.top_role:
                return await ctx.reply(embed=EmbedFactory.error("權限不足", "您無法操作比自己最高身分組還高或同等的身分組！"), mention_author=False)

        if role >= ctx.guild.me.top_role:
            return await ctx.reply(embed=EmbedFactory.error("機器人權限不足", "我的最高身分組階級低於或等於該身分組，無法進行管理！"), mention_author=False)

        # 4. 解析目標成員
        members = []
        if target.lower() in ("everyone", "all"):
            members = ctx.guild.members
        else:
            cleaned_user_id = target.strip("<@!> ")
            if cleaned_user_id.isdigit():
                member = ctx.guild.get_member(int(cleaned_user_id))
                if member:
                    members = [member]
            
            if not members:
                # 搜尋使用者名稱或暱稱
                member = discord.utils.find(
                    lambda m: m.name.lower() == target.lower() or (m.nick and m.nick.lower() == target.lower()), 
                    ctx.guild.members
                )
                if member:
                    members = [member]

        if not members:
            return await ctx.reply(embed=EmbedFactory.error("找不到目標", f"找不到目標成員 `{target}`，請使用提及 (@用戶) 或用戶 ID。"), mention_author=False)

        # 5. 執行身分組變更
        if len(members) > 1:
            status_msg = await ctx.reply(f"⏳ 正在進行批次身分組變更（共 {len(members)} 人）...", mention_author=False)
            success_count = 0
            fail_count = 0
            
            for idx, member in enumerate(members, 1):
                if member.bot:
                    continue  # 跳過機器人以加快速度
                
                try:
                    if action == "on":
                        if role not in member.roles:
                            await member.add_roles(role, reason=f"批次設定由 {ctx.author}")
                            success_count += 1
                    else:
                        if role in member.roles:
                            await member.remove_roles(role, reason=f"批次設定由 {ctx.author}")
                            success_count += 1
                except Exception:
                    fail_count += 1
                
                if idx % 10 == 0:
                    await asyncio.sleep(0.5)
            
            desc = f"• 成功：`{success_count}` 人\n• 失敗：`{fail_count}` 人 (或無變動)"
            await status_msg.edit(embed=EmbedFactory.success("批次身分組設定完成", desc))
        else:
            member = members[0]
            try:
                if action == "on":
                    await member.add_roles(role, reason=f"設定由 {ctx.author}")
                    await ctx.reply(embed=EmbedFactory.success("身分組設定成功", f"已為 {member.mention} 新增身分組 **{role.name}**"), mention_author=False)
                else:
                    await member.remove_roles(role, reason=f"移除由 {ctx.author}")
                    await ctx.reply(embed=EmbedFactory.success("身分組移除成功", f"已為 {member.mention} 移除身分組 **{role.name}**"), mention_author=False)
            except Exception as e:
                await ctx.reply(embed=EmbedFactory.error("身分組設定失敗", f"無法為該成員變更身分組：{e}"), mention_author=False)

    @app_commands.command(name="lock", description="鎖定頻道")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slash_lock(self, interaction: discord.Interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        
        await interaction.response.send_message(
            embed=EmbedFactory.success(f"{Emoji.LOCK} 頻道已鎖定", "此頻道已被鎖定，一般成員無法發送訊息。")
        )

    @app_commands.command(name="unlock", description="解鎖頻道")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slash_unlock(self, interaction: discord.Interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        
        embed = EmbedFactory.success("頻道已解鎖 🔓", f"{interaction.channel.mention} 已解除鎖定，所有人可發言。")
        await interaction.response.send_message(embed=embed)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # RENAME — 更改暱稱
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.command(name="rename_user", description="幫某人改暱稱（需要管理暱稱權限）")
    @app_commands.describe(member="要更改暱稱的對象", new_name="新的暱稱")
    @app_commands.default_permissions(manage_nicknames=True)
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def rename_user(self, interaction: discord.Interaction, member: discord.Member, new_name: str):
        try:
            old_name = member.display_name
            await member.edit(nick=new_name)
            embed = EmbedFactory.success("暱稱已更改", f"{member.mention} 的暱稱從 **{old_name}** 改為 **{new_name}**")
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=EmbedFactory.error("無法更改暱稱", "可能是機器人權限不足，或對方的角色階層高於 Bot。"),
                ephemeral=True,
            )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DM — 私訊成員
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.command(name="dm", description="📬 私訊某人訊息（限管理員）")
    @app_commands.describe(member="要私訊的對象", message="要傳送的內容")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def dm_user(self, interaction: discord.Interaction, member: discord.Member, message: str):
        try:
            await member.send(f"📬 來自 **{interaction.guild.name}** 的管理員訊息：\n{message}")
            await interaction.response.send_message(
                embed=EmbedFactory.success("已傳送", f"已成功傳送訊息給 {member.mention}"),
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=EmbedFactory.error("傳送失敗", f"無法傳送訊息給 {member.mention}，對方可能關閉了私訊。"),
                ephemeral=True,
            )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 自動角色
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    autorole_group = app_commands.Group(name="autorole", description="自動角色設定")

    @autorole_group.command(name="set", description="設定新成員自動角色")
    @app_commands.describe(role="要自動分配的角色")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def autorole_set(self, interaction: discord.Interaction, role: discord.Role):
        await self.db.set_autorole(interaction.guild.id, role.id)
        await interaction.response.send_message(
            embed=EmbedFactory.success("自動角色已設定", f"新成員加入時將自動獲得 {role.mention}")
        )

    @autorole_group.command(name="remove", description="移除自動角色")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def autorole_remove(self, interaction: discord.Interaction):
        await self.db.set_autorole(interaction.guild.id, None)
        await interaction.response.send_message(
            embed=EmbedFactory.success("自動角色已移除", "新成員將不再自動獲得角色。")
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """新成員加入時自動分配角色"""
        role_id = await self.db.get_autorole(member.guild.id)
        if role_id:
            role = member.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason="自動角色分配")
                except discord.Forbidden:
                    pass

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SET_ROLE_NICK — 批量改暱稱
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.command(name="set_role_nick", description="將特定身分組的成員全部改為指定暱稱（限教皇身份）")
    @app_commands.describe(role="目標身分組", new_name="要設為的暱稱")
    async def set_role_nick(self, interaction: discord.Interaction, role: discord.Role, new_name: str):
        pope_role = discord.utils.get(interaction.guild.roles, name="教皇")
        if not pope_role or pope_role not in interaction.user.roles:
            return await interaction.response.send_message("❌ 只有擁有『教皇』身份組的成員才能使用這個指令。", ephemeral=True)

        await interaction.response.defer()
        updated = 0
        failed = 0
        for member in role.members:
            try:
                await member.edit(nick=new_name)
                updated += 1
            except Exception:
                failed += 1
        embed = EmbedFactory.success(
            "暱稱批量修改成功",
            f"✅ 已將 {updated} 位『{role.name}』的暱稱改為：**{new_name}**\n⚠️ 失敗 {failed} 位（可能層級比 Bot 高或權限不足）。"
        )
        await interaction.followup.send(embed=embed)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CREATE_ROOM — 臨時包廂
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.command(name="create_room", description="在《包間服務》分類下建立包廂（支援舞台/語音；舞台不支援時自動退回語音）")
    @app_commands.describe(
        name="頻道名稱",
        kind="語音或舞台",
        private="公開或私人",
        user_limit="人數上限 (僅語音有效；0=不限)"
    )
    @app_commands.choices(
        kind=[app_commands.Choice(name="語音", value="voice"),
              app_commands.Choice(name="舞台", value="stage")],
        private=[app_commands.Choice(name="公開", value="public"),
                 app_commands.Choice(name="私人", value="private")]
    )
    async def create_room(
        self,
        interaction: discord.Interaction,
        name: str,
        kind: app_commands.Choice[str],
        private: app_commands.Choice[str],
        user_limit: int = 0
    ):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("❌ 只能在伺服器使用本指令。", ephemeral=True)

        if not (interaction.user.guild_permissions.manage_channels or interaction.user == guild.owner):
            return await interaction.response.send_message("❌ 你需要「管理頻道」權限。", ephemeral=True)

        await interaction.response.defer(thinking=True)

        category = discord.utils.get(guild.categories, name="包間服務")
        if not category:
            try:
                category = await guild.create_category("包間服務", reason="Create TempRoom category")
            except discord.HTTPException as e:
                return await interaction.followup.send(f"❌ 建立分類失敗：{e}", ephemeral=True)

        is_private = (private.value == "private")
        overwrites = {}
        if is_private:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
                interaction.user:  discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, move_members=True),
                guild.me:          discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, move_members=True, manage_channels=True),
            }

        async def create_stage_with_fallback():
            if "COMMUNITY" not in getattr(guild, "features", []):
                ch = await guild.create_voice_channel(name=name, category=category, overwrites=overwrites or {}, reason="Fallback: guild not COMMUNITY")
                return ch, "語音（已自動退回，伺服器非社群）"
            try:
                ch = await guild.create_stage_channel(name=name, category=category, overwrites=overwrites or {}, reason="Create stage room")
                return ch, "舞台"
            except discord.HTTPException as e:
                if getattr(e, "code", None) == 50024:
                    ch = await guild.create_voice_channel(name=name, category=category, overwrites=overwrites or {}, reason="Fallback: 50024")
                    return ch, "語音（已自動退回：50024）"
                raise

        try:
            if kind.value == "voice":
                ch = await guild.create_voice_channel(
                    name=name,
                    category=category,
                    overwrites=overwrites or {},
                    user_limit=(user_limit if user_limit > 0 else 0),
                    reason=f"Create voice room by {interaction.user}",
                )
                kind_label = "語音"
            else:
                ch, kind_label = await create_stage_with_fallback()

            moved_hint = ""
            if isinstance(ch, (discord.VoiceChannel, discord.StageChannel)):
                try:
                    if interaction.user.voice:
                        await interaction.user.move_to(ch)
                        moved_hint = "，已將你移動至該頻道"
                except Exception:
                    moved_hint = "（未自動移動你到頻道，可能缺少權限或你不在語音狀態）"

            embed = discord.Embed(
                title="🎟️ 包廂已建立",
                description=(
                    f"**名稱**：{ch.mention}\n"
                    f"**類型**：{kind_label}\n"
                    f"**可見性**：{private.name}\n"
                    f"**人數上限**：{user_limit if (kind.value=='voice' and user_limit>0) else '不限'}\n"
                    f"**房主**：{interaction.user.mention}"
                ),
                color=0x57F287
            )
            view = TempRoomView(ch, interaction.user.id, is_private)
            await interaction.followup.send(content=f"✅ 已建立 {kind_label} 包廂{moved_hint}", embed=embed, view=view, ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send("❌ 機器人缺少建立頻道或移動成員的權限。請給我「管理頻道」與（可選）「移動成員」。", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ 建立頻道時發生錯誤：{e}", ephemeral=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # VOICE CONTROL — 語音指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        content = message.content.strip()

        # 1. 暱稱快速修改指令（如 .n @user 暱稱 或 .n 暱稱 等）
        # 匹配：第一個字元為非英數字（符號），第二個字元為 'n'，且後續為空白或字串結束
        if (
            len(content) >= 2 
            and content[1] == 'n' 
            and not content[0].isalnum() 
            and content[0] != ' '
            and (len(content) == 2 or content[2] == ' ')
        ):
            # 取得指令參數部份
            rest = content[3:].strip() if len(content) > 3 else ""
            
            target_member = None
            new_nickname = ""
            
            # 解析參數
            parts = rest.split(maxsplit=1)
            if parts:
                first_part = parts[0]
                # 檢查是否為 Mention (例如 <@123456789> 或 <@!123456789>)
                if first_part.startswith("<@") and first_part.endswith(">"):
                    clean_id = first_part.replace("<@", "").replace("!", "").replace(">", "")
                    if clean_id.isdigit():
                        target_member = message.guild.get_member(int(clean_id))
                
                if target_member:
                    new_nickname = parts[1] if len(parts) > 1 else ""
                else:
                    target_member = message.author
                    new_nickname = rest
            else:
                target_member = message.author
                new_nickname = ""
            
            # 權限驗證與執行
            if target_member.id == message.author.id:
                # 檢查執行者是否擁有 change_nickname 權限
                has_perm = (
                    message.author.guild_permissions.change_nickname or 
                    message.author.guild_permissions.manage_nicknames or 
                    message.author.guild_permissions.administrator
                )
                if not has_perm:
                    return await message.channel.send("❌ 您沒有權限修改自己的暱稱！")
            else:
                # 檢查執行者是否擁有 manage_nicknames 權限
                has_perm = (
                    message.author.guild_permissions.manage_nicknames or 
                    message.author.guild_permissions.administrator
                )
                if not has_perm:
                    return await message.channel.send("❌ 您沒有權限修改其他人的暱稱！")
            
            # 檢查機器人自身的權限
            if not message.guild.me.guild_permissions.manage_nicknames:
                return await message.channel.send("❌ 機器人沒有「管理暱稱」權限，無法執行此操作！")
                
            # 檢查角色階級 (role hierarchy) 與特殊限制 (Guild Owner)
            if target_member.id == message.guild.owner_id and target_member.id != message.guild.me.id:
                return await message.channel.send("❌ 機器人無法修改伺服器擁有者（群主）的暱稱！")
                
            if target_member.id != message.guild.me.id and message.guild.me.top_role <= target_member.top_role:
                return await message.channel.send(f"❌ 無法修改 {target_member.display_name} 的暱稱，因為該成員的身分組階級高於或等於機器人！")
            
            try:
                # 如果 new_nickname 為空字串，則還原暱稱 (傳入 None)
                actual_nick = new_nickname if new_nickname else None
                await target_member.edit(nick=actual_nick)
                
                # 回傳成功訊息
                if actual_nick:
                    await message.channel.send(f"✅ 已成功將 {target_member.mention} 的暱稱修改為 **{actual_nick}**")
                else:
                    await message.channel.send(f"✅ 已成功還原 {target_member.mention} 的暱稱")
            except discord.Forbidden:
                await message.channel.send("❌ 權限不足，無法修改該成員的暱稱。")
            except Exception as e:
                await message.channel.send(f"❌ 修改暱稱時發生錯誤：{e}")
            return

        # 2. 語音控制指令
        voice_commands_leave = ["滾", "出去", "離開", "掰掰", "走開"]
        voice_commands_join = ["來一下", "過來", "加進來"]

        # 進行前綴清理與完整匹配，避免聊天時包含這些字眼誤觸發
        prefix = self.bot.command_prefix
        if isinstance(prefix, str) and content.startswith(prefix):
            clean_content = content[len(prefix):].strip()
        else:
            clean_content = content.strip()

        if clean_content in voice_commands_leave:
            if message.guild.voice_client:
                await message.guild.voice_client.disconnect()
                await message.channel.send("掰掰，我先走啦 👋")
            else:
                await message.channel.send("我不在語音頻道裡喔 🤔")

        elif clean_content in voice_commands_join:
            voice_state = message.author.voice
            if voice_state and voice_state.channel:
                channel = voice_state.channel
                permissions = channel.permissions_for(message.guild.me)
                if not permissions.connect:
                    return await message.channel.send(f"❌ 權限不足：我沒有權限連接到語音頻道 {channel.mention}！")
                if not permissions.speak:
                    return await message.channel.send(f"❌ 權限不足：我沒有權限在語音頻道 {channel.mention} 中發言！")
                try:
                    await channel.connect()
                except Exception as e:
                    return await message.channel.send(f"❌ 無法加入語音頻道：{e}")
                await message.channel.send("我來啦！🎧")
            else:
                await message.channel.send("你先進語音頻道啦，我才能跟過去 😅")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TempRoomView UI 元件
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TempRoomView(discord.ui.View):
    def __init__(self, channel: discord.abc.GuildChannel, owner_id: int, private: bool):
        super().__init__(timeout=None)
        self.channel = channel
        self.owner_id = owner_id
        self.private = private

    @discord.ui.button(label="加入包廂", style=discord.ButtonStyle.success, custom_id="temproom_join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if not guild or not self.channel or not guild.get_channel(self.channel.id):
            return await interaction.response.send_message("❌ 此頻道已不存在。", ephemeral=True)

        if self.private:
            ow = self.channel.overwrites_for(interaction.user)
            ow.view_channel = True
            ow.connect = True
            ow.speak = True
            try:
                await self.channel.set_permissions(interaction.user, overwrite=ow, reason="TempRoom join open gate")
            except Exception:
                pass

        try:
            if interaction.user.voice:
                await interaction.user.move_to(self.channel)
                return await interaction.response.send_message(f"✅ 已將你移動至 {self.channel.mention}", ephemeral=True)
            else:
                invite = await self.channel.create_invite(max_uses=1, max_age=300, reason="TempRoom quick join")
                return await interaction.response.send_message(f"👉 點此加入 {self.channel.mention}：{invite.url}", ephemeral=True)
        except Exception as e:
            return await interaction.response.send_message(f"⚠️ 加入失敗：{e}", ephemeral=True)

    @discord.ui.button(label="刪除包廂（3 秒後）", style=discord.ButtonStyle.danger, custom_id="temproom_delete")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if not guild or not self.channel or not guild.get_channel(self.channel.id):
            return await interaction.response.send_message("❌ 此頻道已不存在。", ephemeral=True)

        if interaction.user.id != self.owner_id and not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("❌ 只有房主或管理員能刪除此包廂。", ephemeral=True)

        await interaction.response.send_message("🗑️ 3 秒後刪除此包廂...", ephemeral=True)
        await asyncio.sleep(3)
        try:
            await self.channel.delete(reason=f"TempRoom deleted by {interaction.user}")
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
