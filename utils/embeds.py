"""
精美 Embed 工廠
仿範本風格：每個 Embed 都有華麗縮圖徽章、詳細欄位、互動按鈕
"""

import discord
from discord import ui
from datetime import datetime, timezone
from config import Colors, Emoji, BadgeImages

# 避免本機路徑 (如 assets/...) 導致 Discord API 回傳 400 Bad Request (Invalid Form Body)
_original_set_thumbnail = discord.Embed.set_thumbnail
_original_set_image = discord.Embed.set_image

def _patched_set_thumbnail(self, url):
    if url and not str(url).startswith(("http://", "https://", "attachment://")):
        return self
    return _original_set_thumbnail(self, url=url)

def _patched_set_image(self, url):
    if url and not str(url).startswith(("http://", "https://", "attachment://")):
        return self
    return _original_set_image(self, url=url)

discord.Embed.set_thumbnail = _patched_set_thumbnail
discord.Embed.set_image = _patched_set_image


class EmbedFactory:
    """統一的 Embed 建構工廠 — 所有 Bot 訊息都從這裡產生"""

    @staticmethod
    def _base_embed(
        title: str,
        description: str = "",
        color: int = Colors.PRIMARY,
        badge_url: str = "",
        author_name: str = "",
        author_icon: str = "",
        footer_text: str = "",
        footer_icon: str = "",
    ) -> discord.Embed:
        """建立基底 Embed，統一風格"""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        
        # 設定華麗縮圖徽章
        if badge_url:
            embed.set_thumbnail(url=badge_url)
        
        # 設定作者資訊
        if author_name:
            embed.set_author(name=author_name, icon_url=author_icon or discord.Embed.Empty)
        
        # 設定 Footer
        if footer_text:
            embed.set_footer(text=footer_text, icon_url=footer_icon or discord.Embed.Empty)
        
        return embed

    @staticmethod
    def _add_user_field(embed: discord.Embed, user: discord.Member | discord.User, label: str = "哪位使用者") -> discord.Embed:
        """添加標準用戶資訊欄位"""
        embed.add_field(
            name=f"**{label}**",
            value=f"{user.mention} | id: {user.id} |\n用戶",
            inline=False,
        )
        return embed

    @staticmethod
    def _add_time_field(embed: discord.Embed) -> discord.Embed:
        """添加標準時間欄位"""
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        embed.add_field(
            name="**時間**",
            value=f"`{timestamp_str}`",
            inline=False,
        )
        return embed

    @staticmethod
    def _add_server_footer(embed: discord.Embed, guild: discord.Guild, bot: discord.Client) -> discord.Embed:
        """添加標準 Footer 含伺服器 ID"""
        embed.set_footer(
            text=f"伺服器id: {guild.id}",
            icon_url=bot.user.display_avatar.url if bot.user else None,
        )
        return embed

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 通用 Embed
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @classmethod
    def success(cls, title: str = "操作成功", description: str = "") -> discord.Embed:
        return cls._base_embed(
            title=f"{Emoji.SUCCESS} {title}",
            description=description,
            color=Colors.SUCCESS,
            badge_url="",
        )

    @classmethod
    def error(cls, title: str = "操作失敗", description: str = "") -> discord.Embed:
        return cls._base_embed(
            title=f"{Emoji.ERROR} {title}",
            description=description,
            color=Colors.ERROR,
            badge_url=BadgeImages.ERROR,
        )

    @classmethod
    def warning(cls, title: str = "警告", description: str = "") -> discord.Embed:
        return cls._base_embed(
            title=f"{Emoji.WARNING} {title}",
            description=description,
            color=Colors.WARNING,
        )

    @classmethod
    def info(cls, title: str = "資訊", description: str = "") -> discord.Embed:
        return cls._base_embed(
            title=f"{Emoji.INFO} {title}",
            description=description,
            color=Colors.INFO,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 管理系統 Embed
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @classmethod
    def kick(cls, user: discord.Member, moderator: discord.Member, reason: str = "未提供", guild: discord.Guild = None, bot: discord.Client = None) -> discord.Embed:
        embed = cls._base_embed(
            title="踢出用戶",
            color=Colors.KICK,
            badge_url=BadgeImages.KICK,
            author_name=moderator.display_name,
            author_icon=moderator.display_avatar.url,
        )
        cls._add_user_field(embed, user, "被踢出的用戶")
        embed.add_field(name="**執行者**", value=f"{moderator.mention} | id: {moderator.id}", inline=False)
        embed.add_field(name="**原因**", value=f"```{reason}```", inline=False)
        cls._add_time_field(embed)
        if guild and bot:
            cls._add_server_footer(embed, guild, bot)
        return embed

    @classmethod
    def ban(cls, user: discord.Member | discord.User, moderator: discord.Member, days: int = 0, reason: str = "未提供", guild: discord.Guild = None, bot: discord.Client = None) -> discord.Embed:
        if days == 0:
            # 解除封禁
            embed = cls._base_embed(
                title="解除封禁",
                color=Colors.UNBAN,
                badge_url=BadgeImages.UNBAN,
                author_name=moderator.display_name,
                author_icon=moderator.display_avatar.url,
            )
            cls._add_user_field(embed, user, "被解封的用戶")
        else:
            embed = cls._base_embed(
                title="封禁用戶",
                color=Colors.BAN,
                badge_url=BadgeImages.BAN,
                author_name=moderator.display_name,
                author_icon=moderator.display_avatar.url,
            )
            cls._add_user_field(embed, user, "被封禁的用戶")
            if days > 0:
                embed.add_field(name="**封禁天數**", value=f"`{days}` 天", inline=True)
        
        embed.add_field(name="**執行者**", value=f"{moderator.mention} | id: {moderator.id}", inline=False)
        embed.add_field(name="**原因**", value=f"```{reason}```", inline=False)
        cls._add_time_field(embed)
        if guild and bot:
            cls._add_server_footer(embed, guild, bot)
        return embed

    @classmethod
    def timeout(cls, user: discord.Member, moderator: discord.Member, duration: str = "", reason: str = "未提供", guild: discord.Guild = None, bot: discord.Client = None) -> discord.Embed:
        embed = cls._base_embed(
            title="禁言處罰",
            color=Colors.TIMEOUT,
            badge_url=BadgeImages.TIMEOUT,
            author_name=moderator.display_name,
            author_icon=moderator.display_avatar.url,
        )
        cls._add_user_field(embed, user, "被禁言的用戶")
        embed.add_field(name="**執行者**", value=f"{moderator.mention} | id: {moderator.id}", inline=False)
        embed.add_field(name="**時長**", value=f"`{duration}`", inline=True)
        embed.add_field(name="**原因**", value=f"```{reason}```", inline=False)
        cls._add_time_field(embed)
        if guild and bot:
            cls._add_server_footer(embed, guild, bot)
        return embed

    @classmethod
    def warn(cls, user: discord.Member, moderator: discord.Member, reason: str = "", warn_count: int = 0, guild: discord.Guild = None, bot: discord.Client = None) -> discord.Embed:
        embed = cls._base_embed(
            title="警告處分",
            color=Colors.WARN,
            badge_url=BadgeImages.WARN,
            author_name=moderator.display_name,
            author_icon=moderator.display_avatar.url,
        )
        cls._add_user_field(embed, user, "被警告的用戶")
        embed.add_field(name="**執行者**", value=f"{moderator.mention} | id: {moderator.id}", inline=False)
        embed.add_field(name="**原因**", value=f"```{reason}```", inline=False)
        embed.add_field(name="**累計警告**", value=f"`{warn_count}` 次", inline=True)
        cls._add_time_field(embed)
        if guild and bot:
            cls._add_server_footer(embed, guild, bot)
        return embed

    @classmethod
    def purge(cls, moderator: discord.Member, count: int, channel: discord.TextChannel, guild: discord.Guild = None, bot: discord.Client = None) -> discord.Embed:
        embed = cls._base_embed(
            title="清除訊息",
            color=Colors.PURGE,
            badge_url=BadgeImages.PURGE,
            author_name=moderator.display_name,
            author_icon=moderator.display_avatar.url,
        )
        embed.add_field(name="**執行者**", value=f"{moderator.mention} | id: {moderator.id}", inline=False)
        embed.add_field(name="**頻道**", value=f"{channel.mention} | id: {channel.id}", inline=False)
        embed.add_field(name="**刪除數量**", value=f"`{count}` 則訊息", inline=True)
        cls._add_time_field(embed)
        if guild and bot:
            cls._add_server_footer(embed, guild, bot)
        return embed

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 日誌系統 Embed
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @classmethod
    def log_member_join(cls, member: discord.Member, bot: discord.Client = None) -> discord.Embed:
        embed = cls._base_embed(
            title="成員加入",
            color=Colors.LOG_JOIN,
            badge_url=BadgeImages.MEMBER_JOIN,
            author_name=member.display_name,
            author_icon=member.display_avatar.url,
        )
        cls._add_user_field(embed, member, "新成員")
        embed.add_field(name="**帳號建立時間**", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        cls._add_time_field(embed)
        if member.guild and bot:
            cls._add_server_footer(embed, member.guild, bot)
        return embed

    @classmethod
    def log_member_leave(cls, member: discord.Member, bot: discord.Client = None) -> discord.Embed:
        embed = cls._base_embed(
            title="成員離開",
            color=Colors.LOG_LEAVE,
            badge_url=BadgeImages.MEMBER_LEAVE,
            author_name=member.display_name,
            author_icon=member.display_avatar.url,
        )
        cls._add_user_field(embed, member, "離開的成員")
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        if roles:
            embed.add_field(name="**擁有的身分組**", value=" ".join(roles[:10]), inline=False)
        cls._add_time_field(embed)
        if member.guild and bot:
            cls._add_server_footer(embed, member.guild, bot)
        return embed

    @classmethod
    def log_message_delete(cls, message: discord.Message, bot: discord.Client = None) -> discord.Embed:
        embed = cls._base_embed(
            title="刪除訊息：",
            color=Colors.LOG_DELETE,
            badge_url=BadgeImages.MSG_DELETED,
            author_name=message.author.display_name if message.author else "未知",
            author_icon=message.author.display_avatar.url if message.author else "",
        )
        content = message.content or "（無文字內容）"
        if len(content) > 1024:
            content = content[:1021] + "..."
        embed.add_field(name="**刪除訊息：**", value=f"```{content}```", inline=False)
        if message.author:
            embed.add_field(
                name="**誰被刪**",
                value=f"{message.author.mention} | id: {message.author.id} |\n用戶",
                inline=False,
            )
        cls._add_time_field(embed)
        embed.add_field(name="", value=f"原訊息id: {message.id}", inline=False)
        if message.guild and bot:
            cls._add_server_footer(embed, message.guild, bot)
        return embed

    @classmethod
    def log_message_edit(cls, before: discord.Message, after: discord.Message, bot: discord.Client = None) -> discord.Embed:
        embed = cls._base_embed(
            title="訊息編輯",
            color=Colors.LOG_EDIT,
            badge_url=BadgeImages.MSG_EDIT,
            author_name=after.author.display_name if after.author else "未知",
            author_icon=after.author.display_avatar.url if after.author else "",
        )
        old_content = before.content or "（無）"
        new_content = after.content or "（無）"
        if len(old_content) > 512:
            old_content = old_content[:509] + "..."
        if len(new_content) > 512:
            new_content = new_content[:509] + "..."
        embed.add_field(name="**編輯前**", value=f"```{old_content}```", inline=False)
        embed.add_field(name="**編輯後**", value=f"```{new_content}```", inline=False)
        if after.author:
            cls._add_user_field(embed, after.author, "誰編輯")
        embed.add_field(name="**頻道**", value=f"{after.channel.mention} | id: {after.channel.id}", inline=False)
        cls._add_time_field(embed)
        if after.guild and bot:
            cls._add_server_footer(embed, after.guild, bot)
        return embed

    @classmethod
    def log_role_change(cls, member: discord.Member, added: list, removed: list, bot: discord.Client = None) -> discord.Embed:
        embed = cls._base_embed(
            title="身分組變更",
            color=Colors.LOG_ROLE,
            badge_url=BadgeImages.ROLE_CHANGE,
            author_name=member.display_name,
            author_icon=member.display_avatar.url,
        )
        cls._add_user_field(embed, member, "哪位使用者")
        if added:
            embed.add_field(
                name="**新增的身分組**",
                value=" ".join([f"{r.mention} | id: {r.id}" for r in added]),
                inline=False,
            )
        if removed:
            embed.add_field(
                name="**移除的身分組**",
                value=" ".join([f"{r.mention} | id: {r.id}" for r in removed]),
                inline=False,
            )
        cls._add_time_field(embed)
        if member.guild and bot:
            cls._add_server_footer(embed, member.guild, bot)
        return embed

    @classmethod
    def log_voice(cls, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState, bot: discord.Client = None) -> discord.Embed:
        if before.channel is None and after.channel is not None:
            action = "加入語音頻道"
            desc = f"加入了 {after.channel.mention}"
        elif before.channel is not None and after.channel is None:
            action = "離開語音頻道"
            desc = f"離開了 {before.channel.mention}"
        elif before.channel != after.channel:
            action = "切換語音頻道"
            desc = f"{before.channel.mention} ➜ {after.channel.mention}"
        else:
            action = "語音狀態變更"
            desc = "靜音/拒聽狀態變更"

        embed = cls._base_embed(
            title=action,
            description=desc,
            color=Colors.LOG_VOICE,
            badge_url=BadgeImages.VOICE_ACTIVITY,
            author_name=member.display_name,
            author_icon=member.display_avatar.url,
        )
        cls._add_user_field(embed, member, "誰")
        cls._add_time_field(embed)
        if member.guild and bot:
            cls._add_server_footer(embed, member.guild, bot)
        return embed

    @classmethod
    def log_typing(cls, channel: discord.TextChannel, user: discord.Member | discord.User, bot: discord.Client = None) -> discord.Embed:
        embed = cls._base_embed(
            title="正在輸入",
            color=Colors.PRIMARY,
            badge_url=BadgeImages.TYPING,
            author_name=user.display_name,
            author_icon=user.display_avatar.url,
        )
        cls._add_user_field(embed, user, "誰正在輸入")
        embed.add_field(name="**哪個頻道**", value=f"# {channel.name} | id: {channel.id}", inline=False)
        cls._add_time_field(embed)
        guild = getattr(channel, 'guild', None)
        if guild and bot:
            cls._add_server_footer(embed, guild, bot)
        return embed

    @classmethod
    def log_new_message(cls, message: discord.Message, bot: discord.Client = None) -> discord.Embed:
        embed = cls._base_embed(
            title="發送訊息：",
            color=Colors.LOG_JOIN,
            badge_url=BadgeImages.NEW_MESSAGE,
            author_name=message.author.display_name,
            author_icon=message.author.display_avatar.url,
        )
        content = message.content or "（無文字內容）"
        if len(content) > 1024:
            content = content[:1021] + "..."
        embed.add_field(name="**發送訊息：**", value=f"```{content}```", inline=False)
        embed.add_field(
            name="**誰發送**",
            value=f"{message.author.mention} | id: {message.author.id} |\n用戶",
            inline=False,
        )
        cls._add_time_field(embed)
        embed.add_field(name="", value=f"訊息id: {message.id}", inline=False)
        if message.guild and bot:
            cls._add_server_footer(embed, message.guild, bot)
        return embed

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 音樂系統 Embed
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @classmethod
    def now_playing(cls, title: str, url: str = "", duration: str = "", position: str = "", requester: discord.Member = None, thumbnail: str = "", progress: float = 0.0) -> discord.Embed:
        # 建立進度條
        bar_length = 12
        filled = int(bar_length * progress)
        bar = "▰" * filled + "▱" * (bar_length - filled)
        
        embed = cls._base_embed(
            title=f"{Emoji.MUSIC} 正在播放",
            description=f"**[{title}]({url})**" if url else f"**{title}**",
            color=Colors.MUSIC,
            badge_url=BadgeImages.MUSIC,
        )
        embed.add_field(
            name="**進度**",
            value=f"`{position}` {bar} `{duration}`",
            inline=False,
        )
        if requester:
            embed.add_field(name="**點歌者**", value=requester.mention, inline=True)
        if thumbnail:
            embed.set_image(url=thumbnail)
        return embed

    @classmethod
    def queue_page(cls, tracks: list, page: int, total_pages: int, now_playing_title: str = "") -> discord.Embed:
        embed = cls._base_embed(
            title=f"{Emoji.QUEUE} 播放佇列",
            color=Colors.MUSIC,
            badge_url=BadgeImages.MUSIC,
        )
        if now_playing_title:
            embed.add_field(name="🎵 正在播放", value=f"**{now_playing_title}**", inline=False)
        
        if tracks:
            desc_lines = []
            for i, track_info in enumerate(tracks):
                idx = (page - 1) * 10 + i + 1
                desc_lines.append(f"`{idx}.` {track_info}")
            embed.add_field(name="📋 佇列中", value="\n".join(desc_lines), inline=False)
        else:
            embed.add_field(name="📋 佇列中", value="*佇列為空*", inline=False)
        
        embed.set_footer(text=f"第 {page}/{total_pages} 頁")
        return embed

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 娛樂系統 Embed
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @classmethod
    def game(cls, title: str, description: str = "") -> discord.Embed:
        return cls._base_embed(
            title=f"{Emoji.GAME} {title}",
            description=description,
            color=Colors.GAME,
            badge_url=BadgeImages.GAME,
        )

    @classmethod
    def giveaway(cls, prize: str, host: discord.Member, duration: str = "", winners: int = 1, entries: int = 0, role_hint: str = "") -> discord.Embed:
        desc = f"**{Emoji.GIFT} 獎品：{prize}**"
        if role_hint:
            desc += f"\n{role_hint}"
        embed = cls._base_embed(
            title=f"{Emoji.PARTY} 抽獎活動",
            description=desc,
            color=Colors.GIVEAWAY,
            badge_url=BadgeImages.GIVEAWAY,
        )
        embed.add_field(name="**主辦者**", value=host.mention, inline=True)
        embed.add_field(name="**中獎人數**", value=f"`{winners}`", inline=True)
        embed.add_field(name="**參加人數**", value=f"`{entries}`", inline=True)
        if duration:
            embed.add_field(name="**剩餘時間**", value=duration, inline=True)
        embed.add_field(
            name="\u200b",
            value=f"點擊下方 {Emoji.PARTY} 按鈕參加抽獎！",
            inline=False,
        )
        return embed


    @classmethod
    def giveaway_ended(cls, prize: str, winners: list[discord.Member], entries: int = 0) -> discord.Embed:
        embed = cls._base_embed(
            title=f"{Emoji.TROPHY} 抽獎結果",
            description=f"**{Emoji.GIFT} 獎品：{prize}**",
            color=Colors.GIVEAWAY,
            badge_url=BadgeImages.GIVEAWAY,
        )
        if winners:
            winner_text = "\n".join([f"{Emoji.CROWN} {w.mention}" for w in winners])
            embed.add_field(name="**🏆 中獎者**", value=winner_text, inline=False)
        else:
            embed.add_field(name="**結果**", value="沒有人參加抽獎 😢", inline=False)
        embed.add_field(name="**總參加人數**", value=f"`{entries}`", inline=True)
        return embed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 互動按鈕 Views
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class UserProfileButton(discord.ui.View):
    """用戶主頁按鈕"""
    def __init__(self, user_id: int, message_url: str = "", channel_id: int = None):
        super().__init__(timeout=None)
        # 前往變更者主頁
        self.add_item(discord.ui.Button(
            label="前往變更者主頁",
            style=discord.ButtonStyle.link,
            url=f"https://discord.com/users/{user_id}",
            emoji="🔗",
        ))

class MessageLogButtons(discord.ui.View):
    """訊息日誌按鈕組"""
    def __init__(self, user_id: int, message_url: str = "", channel_id: int = None, guild_id: int = None, message_id: int = None):
        super().__init__(timeout=None)
        
        # 前往訊息
        if message_url:
            self.add_item(discord.ui.Button(
                label="前往訊息",
                style=discord.ButtonStyle.link,
                url=message_url,
                emoji="🔗",
            ))
        
        # 對方主頁
        self.add_item(discord.ui.Button(
            label="對方主頁",
            style=discord.ButtonStyle.link,
            url=f"https://discord.com/users/{user_id}",
            emoji="🔗",
        ))
        
        # 頻道連結
        if guild_id and channel_id:
            self.add_item(discord.ui.Button(
                label="頻道連結",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/channels/{guild_id}/{channel_id}",
                emoji="🔗",
            ))


class DeleteMessageButton(discord.ui.View):
    """含刪除訊息按鈕的日誌 View"""
    def __init__(self, user_id: int, message_url: str = "", channel_id: int = None, guild_id: int = None):
        super().__init__(timeout=None)
        
        # 刪除訊息按鈕（紅色）
        delete_btn = discord.ui.Button(
            label="刪除訊息",
            style=discord.ButtonStyle.danger,
            custom_id=f"delete_log_{user_id}",
            emoji="🗑️",
        )
        self.add_item(delete_btn)
        
        # 前往訊息
        if message_url:
            self.add_item(discord.ui.Button(
                label="前往訊息",
                style=discord.ButtonStyle.link,
                url=message_url,
                emoji="🔗",
            ))
        
        # 對方主頁
        self.add_item(discord.ui.Button(
            label="對方主頁",
            style=discord.ButtonStyle.link,
            url=f"https://discord.com/users/{user_id}",
            emoji="🔗",
        ))
        
        # 頻道連結
        if guild_id and channel_id:
            self.add_item(discord.ui.Button(
                label="頻道連結",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/channels/{guild_id}/{channel_id}",
                emoji="🔗",
            ))


class ConfirmView(discord.ui.View):
    """確認/取消操作 View"""
    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.value = None

    @discord.ui.button(label="確認", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("你不能操作這個按鈕！", ephemeral=True)
            return
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="取消", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("你不能操作這個按鈕！", ephemeral=True)
            return
        self.value = False
        self.stop()
        await interaction.response.defer()


class PaginatorView(discord.ui.View):
    """通用分頁 View"""
    def __init__(self, pages: list[discord.Embed], author_id: int):
        super().__init__(timeout=120)
        self.pages = pages
        self.current_page = 0
        self.author_id = author_id

    @discord.ui.button(emoji="⏪", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("你不能操作這個按鈕！", ephemeral=True)
        self.current_page = 0
        await interaction.response.edit_message(embed=self.pages[self.current_page])

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("你不能操作這個按鈕！", ephemeral=True)
        self.current_page = max(0, self.current_page - 1)
        await interaction.response.edit_message(embed=self.pages[self.current_page])

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("你不能操作這個按鈕！", ephemeral=True)
        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        await interaction.response.edit_message(embed=self.pages[self.current_page])

    @discord.ui.button(emoji="⏩", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("你不能操作這個按鈕！", ephemeral=True)
        self.current_page = len(self.pages) - 1
        await interaction.response.edit_message(embed=self.pages[self.current_page])
