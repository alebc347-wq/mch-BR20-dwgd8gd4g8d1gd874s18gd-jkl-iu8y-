import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import asyncio
import aiohttp

from config import Colors, Emoji, BadgeImages
from utils.embeds import (
    EmbedFactory,
    UserProfileButton,
    MessageLogButtons,
    DeleteMessageButton,
)


class LogSettingsSelect(discord.ui.Select):
    """日誌設定的多選選單"""
    def __init__(self, guild_id: int, db):
        self.guild_id = guild_id
        self.db = db

        options = [
            discord.SelectOption(label="成員加入 (Member Join)", value="member_join", description="記錄新成員加入伺服器事件"),
            discord.SelectOption(label="成員離開 (Member Leave)", value="member_leave", description="記錄成員退出或被踢出/封禁事件"),
            discord.SelectOption(label="訊息刪除 (Message Delete)", value="message_delete", description="記錄訊息被刪除事件"),
            discord.SelectOption(label="訊息編輯 (Message Edit)", value="message_edit", description="記錄訊息內容修改事件"),
            discord.SelectOption(label="角色變更 (Role Change)", value="role_change", description="記錄成員身分組角色變動"),
            discord.SelectOption(label="語音動態 (Voice Activity)", value="voice", description="記錄加入/離開/切換語音頻道"),
            discord.SelectOption(label="正在輸入 (Is Typing)", value="typing", description="記錄成員正在打字（洗版級）"),
            discord.SelectOption(label="新訊息 (New Message)", value="new_message", description="記錄所有發送的新訊息（洗版級）"),
            discord.SelectOption(label="頻道變更 (Channel Change)", value="channel_change", description="記錄頻道的建立與刪除"),
            discord.SelectOption(label="狀態改變 (Status Change)", value="status_change", description="記錄成員的線上狀態與活動/自訂狀態變更"),
            discord.SelectOption(label="指令使用 (Command Use)", value="command_use", description="記錄成員使用機器人的指令與參數"),
            discord.SelectOption(label="音效板使用 (Soundboard Use)", value="soundboard", description="記錄成員在語音頻道中使用音效板播放音效"),
            discord.SelectOption(label="系統重啟資訊 (Restart Info)", value="restart_notifications", description="記錄 Bot 的重啟、更新與準備就緒狀態")
        ]

        super().__init__(
            placeholder="選擇要啟用的日誌項目...",
            min_values=0,
            max_values=len(options),
            options=options,
            custom_id="select_log_options"
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ 您需要「管理伺服器」權限才能變更此設定！", ephemeral=True)
            
        if not await self.db.is_guild_pro(self.guild_id):
            return await interaction.response.send_message("❌ 此伺服器尚未訂閱 Pro/Ultra 權限！", ephemeral=True)

        selected = self.values
        
        # 處理系統重啟資訊 (restart_notifications)
        restart_enabled = "restart_notifications" in selected
        await self.db.set_feature_enabled(self.guild_id, "restart_notifications", restart_enabled)

        # 處理其餘日誌事件
        log_events = [val for val in selected if val != "restart_notifications"]
        await self.db.update_guild_setting(self.guild_id, "log_events", json.dumps(log_events))

        event_names_zh = {
            "member_join": "成員加入",
            "member_leave": "成員離開",
            "message_delete": "訊息刪除",
            "message_edit": "訊息編輯",
            "role_change": "角色變更",
            "voice": "語音動態",
            "typing": "正在輸入",
            "new_message": "新訊息",
            "channel_change": "頻道變更",
            "status_change": "狀態改變",
            "command_use": "指令使用",
            "soundboard": "音效板使用",
        }
        
        enabled_list = [event_names_zh[e] for e in log_events]
        if restart_enabled:
            enabled_list.append("系統重啟資訊")

        status_desc = "、".join([f"`{name}`" for name in enabled_list]) if enabled_list else "無"

        embed = discord.Embed(
            title="⚙️ 日誌自定義設定已更新",
            description=f"此伺服器已成功更新日誌接收項目！\n\n**目前已啟用通知：**\n{status_desc}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class LogSettingsView(discord.ui.View):
    """日誌設定的互動介面 View"""
    def __init__(self, guild_id: int, db):
        super().__init__(timeout=180)
        self.select = LogSettingsSelect(guild_id, db)
        self.add_item(self.select)

    async def load_defaults(self):
        settings = await self.select.db.get_guild_settings(self.select.guild_id)
        log_events_str = settings.get("log_events")
        restart_enabled = await self.select.db.is_feature_enabled(self.select.guild_id, "restart_notifications", True)

        default_events = [
            "member_join", "member_leave", "message_delete", "message_edit",
            "role_change", "voice", "channel_change", "command_use", "soundboard"
        ]

        if log_events_str is None:
            active_events = default_events
        else:
            log_events = json.loads(log_events_str)
            if "all" in log_events:
                active_events = default_events
            else:
                all_valid_events = [
                    "member_join", "member_leave", "message_delete", "message_edit",
                    "role_change", "voice", "typing", "new_message", "channel_change", "status_change", "command_use", "soundboard"
                ]
                active_events = [e for e in log_events if e in all_valid_events]

        for option in self.select.options:
            if option.value == "restart_notifications":
                option.default = restart_enabled
            else:
                option.default = option.value in active_events


class LogConfigButton(discord.ui.View):
    """日誌設定按鈕，用於重啟與狀態變更 Embed 的底部按鈕"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="設定日誌", 
        emoji="⚙️", 
        style=discord.ButtonStyle.secondary, 
        custom_id="btn_open_log_settings"
    )
    async def open_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild_id:
            return await interaction.response.send_message("❌ 此功能只能在伺服器中使用。", ephemeral=True)
            
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ 您需要「管理伺服器」權限才能變更此設定！", ephemeral=True)
            
        db = interaction.client.db
        if not await db.is_guild_pro(interaction.guild_id):
            embed = discord.Embed(
                title="⭐ 升級為 Pro 或 Ultra",
                description=(
                    "❌ **功能受限**\n「**日誌訊息自定義功能**」僅限 **Pro** 或 **Ultra** 訂閱伺服器使用！\n"
                    "請聯絡機器人擁有者以啟用此伺服器的 Pro/Ultra 權限。"
                ),
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        view = LogSettingsView(interaction.guild_id, db)
        await view.load_defaults()
        await interaction.response.send_message("⚙️ **日誌系統自定義選單**\n請在下方下拉選單中**選擇/勾選**您想要啟用的日誌通知類型：", view=view, ephemeral=True)


class Logging(commands.GroupCog, name="log", description="日誌系統設定"):
    """日誌系統 — 記錄所有伺服器事件"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.pro_reminder_loop.start()
        self._presence_cooldowns = {}
        self._log_rate_limits = {}

    def cog_unload(self):
        self.pro_reminder_loop.cancel()

    async def ensure_log_channel(self, guild: discord.Guild):
        """確認伺服器有『顯示伺服器目前變動』私密頻道，若無則補上，並設定權限與寫入資料庫"""
        # 1. 搜尋是否有名為 "顯示伺服器目前變動" 的頻道
        channel = discord.utils.get(guild.text_channels, name="顯示伺服器目前變動")
        
        if not channel:
            # 2. 建立此頻道為私人頻道
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            }
            if guild.owner:
                overwrites[guild.owner] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            
            # 加上特定開發者 ID (1437408048934027274)
            overwrites[discord.Object(id=1437408048934027274)] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            
            # 加上伺服器管理員角色
            for role in guild.roles:
                if role.permissions.administrator:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            
            try:
                channel = await guild.create_text_channel("顯示伺服器目前變動", overwrites=overwrites)
                print(f"✅ 已在 {guild.name} 建立專屬私密日誌頻道: 顯示伺服器目前變動")
                await channel.send("🔒 **私人日誌頻道已成功設定！**\n本頻道僅限管理員、伺服器擁有者與開發者查看。伺服器變動日誌將在此處發送。", view=LogConfigButton())
            except Exception as e:
                print(f"❌ 無法在 {guild.name} 建立日誌頻道: {e}")
                return
        else:
            # 如果頻道已經存在，確保開發者 (1437408048934027274) 擁有檢視權限
            try:
                dev_target = guild.get_member(1437408048934027274)
                if dev_target:
                    overwrite = channel.overwrites_for(dev_target)
                    if overwrite.view_channel is not True or overwrite.send_messages is not True:
                        await channel.set_permissions(
                            dev_target,
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True
                        )
                        print(f"✅ 已在 {guild.name} 更新開發者日誌頻道權限")
            except Exception as e:
                print(f"⚠️ 無法在 {guild.name} 更新開發者日誌頻道權限: {e}")
        
        # 3. 將日誌頻道設定寫入資料庫，使 Bot 所有事件日誌自動發送到此處
        if channel:
            await self.db.set_log_channel(guild.id, channel.id)

    def _check_log_rate_limit(self, guild_id: int, event: str, limit_per_minute: int = 15) -> bool:
        """限制同一個公會中特定事件每分鐘發送日誌的數量，防止 429 或被 Discord 判定為濫用"""
        import time
        now = time.time()
        if guild_id not in self._log_rate_limits:
            self._log_rate_limits[guild_id] = {}
        if event not in self._log_rate_limits[guild_id]:
            self._log_rate_limits[guild_id][event] = []
            
        # 清除超過 60 秒的舊紀錄
        self._log_rate_limits[guild_id][event] = [t for t in self._log_rate_limits[guild_id][event] if now - t < 60]
        
        # 檢查數量是否超限
        if len(self._log_rate_limits[guild_id][event]) >= limit_per_minute:
            return False
            
        self._log_rate_limits[guild_id][event].append(now)
        return True

    async def _send_log(self, guild: discord.Guild, embed: discord.Embed, view: discord.ui.View = None, event: str = None):
        """發送日誌到設定的日誌頻道"""
        if event:
            limit = 20
            if event == "typing":
                limit = 5
            elif event == "new_message":
                limit = 10
            elif event in ("message_edit", "message_delete", "voice"):
                limit = 15
            elif event == "status_change":
                limit = 10
            elif event == "soundboard":
                limit = 10
                
            if not self._check_log_rate_limit(guild.id, event, limit):
                return
        log_channel_id = await self.db.get_log_channel(guild.id)
        if not log_channel_id:
            return
        
        channel = guild.get_channel(log_channel_id)
        if not channel:
            return
        
        try:
            if view:
                await channel.send(embed=embed, view=view)
            else:
                await channel.send(embed=embed)
        except discord.Forbidden:
            pass
        except discord.HTTPException as e:
            if e.status == 429:
                print(f"⚠️ 遭遇 Discord 速率限制 (429): {e}")
            else:
                print(f"⚠️ 發送日誌時發生 HTTP 錯誤: {e}")
        except Exception as e:
            print(f"⚠️ 發送日誌時發生未知錯誤: {e}")

    async def _should_log(self, guild_id: int, event: str) -> bool:
        """檢查是否應該記錄此事件"""
        # 如果未啟用 Pro 或 Ultra 權限，則不能使用日誌系統
        if not await self.db.is_guild_pro(guild_id):
            return False
            
        settings = await self.db.get_guild_settings(guild_id)
        log_events_str = settings.get("log_events")
        
        # 預設啟用的事件列表（排除 status_change、typing、new_message 以防洗版）
        default_events = [
            "member_join", "member_leave", "message_delete", "message_edit",
            "role_change", "voice", "channel_change", "command_use", "soundboard"
        ]

        if log_events_str is None:
            log_events = default_events
        else:
            log_events = json.loads(log_events_str)
            if "all" in log_events:
                log_events = default_events
                
        return event in log_events

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 事件監聽 (自動補上日誌頻道)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @commands.Cog.listener()
    async def on_ready(self):
        """當 Bot 啟動完畢，自動檢查並補上所有加入伺服器的私密日誌頻道"""
        for guild in self.bot.guilds:
            await self.ensure_log_channel(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """當 Bot 加入新伺服器時，自動建立並設定私密日誌頻道"""
        await self.ensure_log_channel(guild)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 設定指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.command(name="setup", description="手動同步並建立私密日誌頻道「顯示伺服器目前變動」")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def logsetup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.ensure_log_channel(interaction.guild)
        await interaction.followup.send("✅ 私人日誌頻道已成功檢查並設定完畢！", ephemeral=True)

    @app_commands.command(name="set", description="設定日誌頻道")
    @app_commands.describe(channel="日誌頻道")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def setlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.db.set_log_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(
            embed=EmbedFactory.success("日誌頻道已設定", f"所有事件將記錄到 {channel.mention}")
        )

    @app_commands.command(name="config", description="配置要記錄的事件")
    @app_commands.describe(events="事件類型（用逗號分隔，或輸入 all）")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def logconfig(self, interaction: discord.Interaction, events: str = "all"):
        valid_events = [
            "all", "member_join", "member_leave", "message_delete",
            "message_edit", "role_change", "voice", "typing", "new_message",
            "channel_change", "status_change", "command_use", "soundboard",
        ]
        
        if events.lower() == "all":
            event_list = ["all"]
        else:
            event_list = [e.strip().lower() for e in events.split(",")]
            invalid = [e for e in event_list if e not in valid_events]
            if invalid:
                return await interaction.response.send_message(
                    embed=EmbedFactory.error(
                        "無效的事件類型",
                        f"無效：`{'`, `'.join(invalid)}`\n"
                        f"可用：`{'`, `'.join(valid_events)}`",
                    ),
                    ephemeral=True,
                )
        
        await self.db.update_guild_setting(
            interaction.guild.id, "log_events", json.dumps(event_list)
        )
        
        await interaction.response.send_message(
            embed=EmbedFactory.success(
                "日誌配置已更新",
                f"記錄事件：`{'`, `'.join(event_list)}`",
            )
        )

    @app_commands.command(name="settings", description="開啟日誌訊息自定義功能選單")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logsettings(self, interaction: discord.Interaction):
        # 1. 驗證權限與 Pro/Ultra
        if not await self.db.is_guild_pro(interaction.guild_id):
            embed = discord.Embed(
                title="⭐ 升級為 Pro 或 Ultra",
                description=(
                    "❌ **功能受限**\n「**日誌訊息自定義功能**」僅限 **Pro** 或 **Ultra** 訂閱伺服器使用！\n"
                    "請聯絡機器人擁有者以啟用此伺服器的 Pro/Ultra 權限。"
                ),
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # 2. 顯示自定義選單 (ephemeral)
        view = LogSettingsView(interaction.guild_id, self.db)
        await view.load_defaults()
        await interaction.response.send_message(
            "⚙️ **日誌系統自定義選單**\n請在下方下拉選單中**選擇/勾選**您想要啟用的日誌通知類型：",
            view=view,
            ephemeral=True
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 事件監聽
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """成員加入"""
        if member.id == 1437408048934027274:
            await self.ensure_log_channel(member.guild)

        if not await self._should_log(member.guild.id, "member_join"):
            return
        
        embed = EmbedFactory.log_member_join(member, self.bot)
        view = UserProfileButton(member.id)
        await self._send_log(member.guild, embed, view)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """成員離開"""
        if not await self._should_log(member.guild.id, "member_leave"):
            return
        
        embed = EmbedFactory.log_member_leave(member, self.bot)
        view = UserProfileButton(member.id)
        await self._send_log(member.guild, embed, view)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """訊息刪除"""
        if not message.guild:
            return
        if message.author and message.author.bot:
            return
        if not await self._should_log(message.guild.id, "message_delete"):
            return
        
        embed = EmbedFactory.log_message_delete(message, self.bot)
        view = DeleteMessageButton(
            user_id=message.author.id if message.author else 0,
            channel_id=message.channel.id,
            guild_id=message.guild.id,
        )
        await self._send_log(message.guild, embed, view, event="message_delete")

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """處理未快取的訊息刪除"""
        if payload.cached_message:
            return  # 已在 on_message_delete 處理
            
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        if not await self._should_log(guild.id, "message_delete"):
            return

        embed = discord.Embed(
            title="🗑️ 訊息刪除（未快取）",
            description="一則較舊或未快取於 Bot 記憶體中的訊息已被刪除。",
            color=Colors.LOG_DELETE,
        )
        embed.set_thumbnail(url=BadgeImages.MSG_DELETED)
        
        channel = guild.get_channel(payload.channel_id)
        channel_mention = channel.mention if channel else f"id: {payload.channel_id}"
        embed.add_field(name="**頻道**", value=channel_mention, inline=False)
        embed.add_field(name="**訊息 ID**", value=f"`{payload.message_id}`", inline=False)
        
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        embed.add_field(name="**時間**", value=f"`{now.strftime('%Y-%m-%d %H:%M:%S')}`", inline=False)
        
        EmbedFactory._add_server_footer(embed, guild, self.bot)
        
        view = discord.ui.View()
        if channel:
            view.add_item(discord.ui.Button(
                label="前往頻道",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/channels/{guild.id}/{channel.id}",
                emoji="🔗"
            ))
        await self._send_log(guild, embed, view, event="message_delete")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """訊息編輯"""
        if not after.guild:
            return
        if after.author and after.author.bot:
            return
        if before.content == after.content:
            return
        if not await self._should_log(after.guild.id, "message_edit"):
            return
        
        embed = EmbedFactory.log_message_edit(before, after, self.bot)
        view = MessageLogButtons(
            user_id=after.author.id if after.author else 0,
            message_url=after.jump_url,
            channel_id=after.channel.id,
            guild_id=after.guild.id,
        )
        await self._send_log(after.guild, embed, view, event="message_edit")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """角色變更"""
        if before.roles == after.roles:
            return
        if not await self._should_log(after.guild.id, "role_change"):
            return
        
        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        
        if not added and not removed:
            return
        
        embed = EmbedFactory.log_role_change(after, added, removed, self.bot)
        view = UserProfileButton(after.id)
        await self._send_log(after.guild, embed, view)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """語音狀態變更"""
        if before.channel == after.channel:
            return  # 只記錄加入/離開/切換
        if not await self._should_log(member.guild.id, "voice"):
            return
        
        embed = EmbedFactory.log_voice(member, before, after, self.bot)
        view = UserProfileButton(member.id)
        await self._send_log(member.guild, embed, view, event="voice")

    @commands.Cog.listener()
    async def on_typing(self, channel: discord.abc.Messageable, user: discord.Member | discord.User, when):
        """正在輸入"""
        guild = getattr(channel, 'guild', None)
        if not guild:
            return
        if user.bot:
            return
        if not await self._should_log(guild.id, "typing"):
            return
        
        embed = EmbedFactory.log_typing(channel, user, self.bot)
        await self._send_log(guild, embed, event="typing")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """新訊息（記錄到日誌與頻道內設定觸發）"""
        if not message.guild or message.author.bot:
            return
        
        # 檢查是否在「顯示伺服器目前變動」日誌頻道中輸入「設定」
        log_channel_id = await self.db.get_log_channel(message.guild.id)
        is_log_channel = (log_channel_id and message.channel.id == log_channel_id) or (message.channel.name == "顯示伺服器目前變動")

        if is_log_channel and message.content.strip() in ["設定", "log設定", "日誌設定"]:
            embed = discord.Embed(
                title="⚙️ 日誌自定義設定",
                description="點擊下方按鈕以開啟日誌系統自定義選單：",
                color=Colors.PRIMARY,
            )
            await message.channel.send(embed=embed, view=LogConfigButton())
            return

        if not await self._should_log(message.guild.id, "new_message"):
            return
        
        embed = EmbedFactory.log_new_message(message, self.bot)
        view = DeleteMessageButton(
            user_id=message.author.id,
            message_url=message.jump_url,
            channel_id=message.channel.id,
            guild_id=message.guild.id,
        )
        await self._send_log(message.guild, embed, view, event="new_message")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        """頻道建立"""
        if not await self._should_log(channel.guild.id, "channel_change"):
            return
        
        embed = discord.Embed(
            title="頻道建立",
            color=Colors.LOG_CHAN,
        )
        embed.add_field(name="**頻道名稱**", value=f"{channel.mention} | id: {channel.id}", inline=False)
        embed.add_field(name="**類型**", value=f"`{channel.type}`", inline=True)
        
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        embed.add_field(name="**時間**", value=f"`{now.strftime('%Y-%m-%d %H:%M:%S')}`", inline=False)
        
        EmbedFactory._add_server_footer(embed, channel.guild, self.bot)
        await self._send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """頻道刪除"""
        if not await self._should_log(channel.guild.id, "channel_change"):
            return
        
        embed = discord.Embed(
            title="頻道刪除",
            color=Colors.ERROR,
        )
        embed.add_field(name="**頻道名稱**", value=f"`#{channel.name}` | id: {channel.id}", inline=False)
        embed.add_field(name="**類型**", value=f"`{channel.type}`", inline=True)
        
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        embed.add_field(name="**時間**", value=f"`{now.strftime('%Y-%m-%d %H:%M:%S')}`", inline=False)
        
        EmbedFactory._add_server_footer(embed, channel.guild, self.bot)
        await self._send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        """成員狀態或活動變更"""
        if before.bot:
            return
        if not await self._should_log(after.guild.id, "status_change"):
            return

        # 檢查 status 是否改變
        status_changed = before.status != after.status

        # 檢查活動 (CustomActivity 等)
        def get_activity_info(member: discord.Member):
            custom = None
            other_acts = []
            for act in member.activities:
                if isinstance(act, discord.CustomActivity):
                    custom = act.name or act.state
                else:
                    other_acts.append(f"{act.type.name.title()}: {act.name}")
            return custom, other_acts

        before_custom, before_others = get_activity_info(before)
        after_custom, after_others = get_activity_info(after)

        activity_changed = (before_custom != after_custom) or (before_others != after_others)

        if not status_changed and not activity_changed:
            return

        # 限制同一個成員在同一個伺服器 30 秒內只能記錄一次狀態/活動變更，防範 429 速率限制
        import time
        now = time.time()
        guild_id = after.guild.id
        member_id = after.id

        if guild_id not in self._presence_cooldowns:
            self._presence_cooldowns[guild_id] = {}

        last_time = self._presence_cooldowns[guild_id].get(member_id, 0)
        if now - last_time < 30:
            return

        self._presence_cooldowns[guild_id][member_id] = now

        embed = discord.Embed(
            title="👤 成員狀態變更",
            color=Colors.LOG_VOICE,
        )
        embed.set_author(name=f"{after.name}#{after.discriminator}", icon_url=after.display_avatar.url)
        embed.add_field(name="**成員**", value=f"{after.mention} | id: {after.id}", inline=False)

        status_names = {
            discord.Status.online: "🟢 線上 (Online)",
            discord.Status.idle: "🟡 閒置 (Idle)",
            discord.Status.dnd: "🔴 請勿打擾 (Do Not Disturb)",
            discord.Status.offline: "⚫ 離線 (Offline)"
        }

        if status_changed:
            before_str = status_names.get(before.status, str(before.status))
            after_str = status_names.get(after.status, str(after.status))
            embed.add_field(name="**線上狀態變更**", value=f"`{before_str}` ➔ `{after_str}`", inline=False)

        if activity_changed:
            before_act = f"自訂狀態: {before_custom or '無'}"
            if before_others:
                before_act += f"\n其他活動: {', '.join(before_others)}"
            
            after_act = f"自訂狀態: {after_custom or '無'}"
            if after_others:
                after_act += f"\n其他活動: {', '.join(after_others)}"
                
            embed.add_field(name="**舊活動/自訂狀態**", value=before_act, inline=True)
            embed.add_field(name="**新活動/自訂狀態**", value=after_act, inline=True)

        embed.set_thumbnail(url=BadgeImages.STATUS_CHANGE)
        EmbedFactory._add_server_footer(embed, after.guild, self.bot)

        view = LogConfigButton()
        await self._send_log(after.guild, embed, view)

    @tasks.loop(minutes=10)
    async def pro_reminder_loop(self):
        """每 10 分鐘，若伺服器非 Pro/Ultra，則發送訂閱提示"""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            try:
                if not await self.db.is_guild_pro(guild.id):
                    log_channel_id = await self.db.get_log_channel(guild.id)
                    if log_channel_id:
                        channel = guild.get_channel(log_channel_id)
                        if channel:
                            embed = discord.Embed(
                                title="⭐ 升級為 Pro 或 Ultra",
                                description=(
                                    "💡 **系統提示**：此伺服器目前使用免費版日誌系統。\n"
                                    "訂閱 **Pro** 或 **Ultra** 即可解鎖「**日誌訊息自定義功能**」，客製化各類日誌的發送，保持頻道整潔！"
                                ),
                                color=Colors.WARNING
                            )
                            view = LogConfigButton()
                            await channel.send(embed=embed, view=view)
            except discord.HTTPException as e:
                print(f"HTTP Error in pro_reminder_loop for guild {guild.id}: {e}")
                # 如果是 5xx 伺服器錯誤（例如 503 Service Unavailable），直接中斷本次 loop，避免重複向其他公會發送請求並洗版
                if e.status >= 500:
                    print("⚠️ 偵測到 Discord API 5xx 伺服器錯誤，中斷本次 pro_reminder_loop。")
                    break
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                print(f"Network Error in pro_reminder_loop for guild {guild.id}: {e}")
                print("⚠️ 偵測到網路或 Proxy 連線錯誤，中斷本次 pro_reminder_loop。")
                break
            except Exception as e:
                print(f"Error in pro_reminder_loop for guild {guild.id}: {e}")

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        """記錄前綴指令的使用"""
        if not ctx.guild:
            return
        if not await self._should_log(ctx.guild.id, "command_use"):
            return

        embed = discord.Embed(
            title="🤖 執行前綴指令",
            color=Colors.PRIMARY,
        )
        embed.set_author(name=f"{ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        embed.add_field(name="**使用者**", value=f"{ctx.author.mention} | id: {ctx.author.id}", inline=True)
        embed.add_field(name="**頻道**", value=ctx.channel.mention, inline=True)
        embed.add_field(name="**指令內容**", value=f"`{ctx.message.content}`", inline=False)

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        embed.add_field(name="**時間**", value=f"`{now.strftime('%Y-%m-%d %H:%M:%S')}`", inline=False)

        EmbedFactory._add_server_footer(embed, ctx.guild, self.bot)
        await self._send_log(ctx.guild, embed)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """記錄斜線指令的使用"""
        if interaction.type != discord.InteractionType.application_command:
            return
        if not interaction.guild:
            return
        if not await self._should_log(interaction.guild.id, "command_use"):
            return

        cmd_name = interaction.command.name if interaction.command else interaction.data.get("name", "未知指令")
        options = interaction.data.get("options", [])

        def parse_options(opts):
            args = []
            for opt in opts:
                if "value" in opt:
                    args.append(f"{opt['name']}: `{opt['value']}`")
                elif "options" in opt:
                    sub_args = parse_options(opt["options"])
                    args.append(f"{opt['name']} [{', '.join(sub_args)}]")
            return args

        args_list = parse_options(options)
        args_str = ", ".join(args_list) if args_list else "無"

        embed = discord.Embed(
            title="🤖 執行斜線指令",
            color=Colors.PRIMARY,
        )
        embed.set_author(name=f"{interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="**使用者**", value=f"{interaction.user.mention} | id: {interaction.user.id}", inline=True)
        embed.add_field(name="**頻道**", value=interaction.channel.mention if interaction.channel else "未知頻道", inline=True)
        embed.add_field(name="**指令名稱**", value=f"`/{cmd_name}`", inline=False)
        embed.add_field(name="**參數內容**", value=args_str, inline=False)

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        embed.add_field(name="**時間**", value=f"`{now.strftime('%Y-%m-%d %H:%M:%S')}`", inline=False)

        EmbedFactory._add_server_footer(embed, interaction.guild, self.bot)
        await self._send_log(interaction.guild, embed)

    @commands.Cog.listener()
    async def on_socket_raw_dispatch(self, msg: dict):
        """監聽 Discord Gateway 原始事件以捕捉音效板使用 (VOICE_CHANNEL_EFFECT_SEND)"""
        if msg.get("t") == "VOICE_CHANNEL_EFFECT_SEND":
            data = msg.get("d", {})
            if not data or "sound_id" not in data:
                return
            
            try:
                guild_id = int(data.get("guild_id", 0))
            except (ValueError, TypeError):
                return

            if not guild_id or not await self._should_log(guild_id, "soundboard"):
                return

            guild = self.bot.get_guild(guild_id)
            if not guild:
                return

            try:
                user_id = int(data.get("user_id", 0))
                channel_id = int(data.get("channel_id", 0))
            except (ValueError, TypeError):
                return

            sound_id = data.get("sound_id")
            
            member = guild.get_member(user_id)
            channel = guild.get_channel(channel_id)

            user_mention = member.mention if member else f"id: {user_id}"
            user_name = member.name if member else f"User {user_id}"
            channel_mention = channel.mention if channel else f"id: {channel_id}"

            embed = discord.Embed(
                title="🔊 音效板使用紀錄",
                color=Colors.LOG_VOICE,
            )
            if member:
                embed.set_author(name=user_name, icon_url=member.display_avatar.url)
            else:
                embed.set_author(name=user_name)

            embed.add_field(name="**使用者**", value=f"{user_mention} | id: {user_id}", inline=True)
            embed.add_field(name="**語音頻道**", value=channel_mention, inline=True)
            if sound_id:
                embed.add_field(name="**音效 ID**", value=f"`{sound_id}`", inline=False)

            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            embed.add_field(name="**時間**", value=f"`{now.strftime('%Y-%m-%d %H:%M:%S')}`", inline=False)

            EmbedFactory._add_server_footer(embed, guild, self.bot)
            await self._send_log(guild, embed, event="soundboard")


async def setup(bot: commands.Bot):
    await bot.add_cog(Logging(bot))
