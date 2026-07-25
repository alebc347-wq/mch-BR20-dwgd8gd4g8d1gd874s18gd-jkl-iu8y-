"""
自動審核 Cog
髒話/敏感詞過濾、刷屏偵測、連結過濾、大寫過量偵測
"""

import discord
from discord import app_commands
from discord.ext import commands
import re
import hashlib
import json

from config import Colors, Emoji, BadgeImages
from utils.embeds import EmbedFactory


class AutoMod(commands.Cog):
    """自動審核系統"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    async def _is_whitelisted(self, message: discord.Message) -> bool:
        """檢查是否在白名單中"""
        if not message.guild:
            return True
        
        # Bot 和管理員免疫
        if message.author.bot:
            return True
        if message.author.guild_permissions.administrator:
            return True
        if message.author.guild_permissions.manage_messages:
            return True
        
        settings = await self.db.get_guild_settings(message.guild.id)
        
        # 白名單頻道
        whitelist_channels = json.loads(settings.get("automod_whitelist_channels", "[]"))
        if message.channel.id in whitelist_channels:
            return True
        
        # 白名單角色
        whitelist_roles = json.loads(settings.get("automod_whitelist_roles", "[]"))
        user_role_ids = [r.id for r in message.author.roles]
        if any(r in whitelist_roles for r in user_role_ids):
            return True
        
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """監聽訊息進行自動審核"""
        if not message.guild or message.author.bot:
            return
        
        settings = await self.db.get_guild_settings(message.guild.id)
        if not settings.get("automod_enabled"):
            return
        
        if await self._is_whitelisted(message):
            return
        
        # 髒話過濾
        bad_words = json.loads(settings.get("automod_bad_words", "[]"))
        if bad_words:
            content_lower = message.content.lower()
            for word in bad_words:
                if word in content_lower:
                    await self._handle_violation(message, "髒話/敏感詞", f"觸發詞彙：`{word}`")
                    return
        
        # 刷屏偵測
        if settings.get("automod_spam_enabled"):
            msg_hash = hashlib.md5(message.content.encode()).hexdigest()
            count = await self.db.track_message(message.author.id, message.guild.id, msg_hash)
            spam_limit = await self.db.get_spam_limit(message.guild.id, 7)
            if count >= spam_limit:
                await self._handle_violation(message, "刷屏偵測", f"短時間內發送過多重複訊息（重複超過 {spam_limit} 次）")
                await self.db.reset_spam_tracker(message.author.id, message.guild.id)
                return
        
        # 連結過濾
        if settings.get("automod_links_enabled"):
            url_pattern = re.compile(r'https?://\S+', re.IGNORECASE)
            if url_pattern.search(message.content):
                await self._handle_violation(message, "連結過濾", "此頻道不允許發送連結")
                return
        
        # 大寫過量
        if settings.get("automod_caps_enabled"):
            alpha_chars = [c for c in message.content if c.isalpha()]
            if len(alpha_chars) > 10:
                caps_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
                if caps_ratio > 0.7:
                    await self._handle_violation(message, "大寫過量", "訊息中大寫字母比例過高")
                    return
        
        # 大量 Mention
        mentions_max = settings.get("automod_mentions_max", 5)
        if len(message.mentions) > mentions_max:
            await self._handle_violation(message, "大量 Mention", f"一則訊息中提及了超過 {mentions_max} 位用戶")
            return

    async def _handle_violation(self, message: discord.Message, violation_type: str, detail: str):
        """處理違規行為"""
        try:
            await message.delete()
        except discord.Forbidden:
            pass
        
        # 發送警告通知
        embed = discord.Embed(
            title=f"{Emoji.SHIELD} 自動審核",
            description=f"**違規類型：** {violation_type}",
            color=Colors.AUTOMOD,
        )
        if BadgeImages.AUTOMOD:
            embed.set_thumbnail(url=BadgeImages.AUTOMOD)
        embed.add_field(name="**詳情**", value=detail, inline=False)
        embed.add_field(
            name="**用戶**",
            value=f"{message.author.mention} | id: {message.author.id}",
            inline=False,
        )
        embed.add_field(name="**頻道**", value=message.channel.mention, inline=True)
        
        try:
            warn_msg = await message.channel.send(
                embed=embed,
                delete_after=10,  # 10 秒後自動刪除
            )
        except discord.Forbidden:
            pass
        
        # 記錄到日誌頻道
        log_channel_id = await self.db.get_log_channel(message.guild.id)
        if log_channel_id:
            log_channel = message.guild.get_channel(log_channel_id)
            if log_channel:
                try:
                    await log_channel.send(embed=embed)
                except discord.Forbidden:
                    pass

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 設定指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    automod_group = app_commands.Group(name="automod", description="自動審核設定")

    @automod_group.command(name="toggle", description="開關自動審核功能")
    @app_commands.describe(feature="要開關的功能")
    @app_commands.choices(feature=[
        app_commands.Choice(name="自動審核（總開關）", value="automod_enabled"),
        app_commands.Choice(name="刷屏偵測", value="automod_spam_enabled"),
        app_commands.Choice(name="連結過濾", value="automod_links_enabled"),
        app_commands.Choice(name="大寫過量偵測", value="automod_caps_enabled"),
    ])
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_toggle(self, interaction: discord.Interaction, feature: str):
        settings = await self.db.get_guild_settings(interaction.guild.id)
        current = settings.get(feature, 0)
        new_value = 0 if current else 1
        await self.db.update_guild_setting(interaction.guild.id, feature, new_value)
        
        feature_names = {
            "automod_enabled": "自動審核（總開關）",
            "automod_spam_enabled": "刷屏偵測",
            "automod_links_enabled": "連結過濾",
            "automod_caps_enabled": "大寫過量偵測",
        }
        
        status = "✅ 已開啟" if new_value else "❌ 已關閉"
        await interaction.response.send_message(
            embed=EmbedFactory.success(
                "自動審核設定",
                f"**{feature_names.get(feature)}**：{status}",
            )
        )

    @automod_group.command(name="spam_limit", description="設定刷屏偵測重複訊息次數限制（上限 15，下限 3）")
    @app_commands.describe(count="重複訊息次數限制")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_spam_limit(self, interaction: discord.Interaction, count: int):
        if count < 3 or count > 15:
            return await interaction.response.send_message(
                embed=EmbedFactory.error(
                    "設定失敗",
                    "刷屏重複限制次數必須介於 **3 (下限)** 與 **15 (上限)** 之間！"
                ),
                ephemeral=True
            )
        
        await self.db.set_spam_limit(interaction.guild.id, count)
        await interaction.response.send_message(
            embed=EmbedFactory.success(
                "設定已更新",
                f"刷屏重複限制次數已成功設定為：`{count}` 次。"
            )
        )

    @automod_group.command(name="addword", description="新增過濾詞彙")
    @app_commands.describe(word="要過濾的詞彙")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_addword(self, interaction: discord.Interaction, word: str):
        await self.db.add_bad_word(interaction.guild.id, word)
        await interaction.response.send_message(
            embed=EmbedFactory.success("詞彙已新增", f"已將 `{word}` 加入過濾清單。"),
            ephemeral=True,
        )

    @automod_group.command(name="removeword", description="移除過濾詞彙")
    @app_commands.describe(word="要移除的詞彙")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_removeword(self, interaction: discord.Interaction, word: str):
        result = await self.db.remove_bad_word(interaction.guild.id, word)
        if result:
            await interaction.response.send_message(
                embed=EmbedFactory.success("詞彙已移除", f"已將 `{word}` 從過濾清單移除。"),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=EmbedFactory.error("找不到詞彙", f"`{word}` 不在過濾清單中。"),
                ephemeral=True,
            )

    @automod_group.command(name="whitelist", description="設定白名單頻道或角色")
    @app_commands.describe(channel="白名單頻道", role="白名單角色")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_whitelist(self, interaction: discord.Interaction, channel: discord.TextChannel = None, role: discord.Role = None):
        if not channel and not role:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("請指定頻道或角色"),
                ephemeral=True,
            )
        
        settings = await self.db.get_guild_settings(interaction.guild.id)
        results = []
        
        if channel:
            channels = json.loads(settings.get("automod_whitelist_channels", "[]"))
            if channel.id in channels:
                channels.remove(channel.id)
                results.append(f"已從白名單移除 {channel.mention}")
            else:
                channels.append(channel.id)
                results.append(f"已加入白名單 {channel.mention}")
            await self.db.update_guild_setting(interaction.guild.id, "automod_whitelist_channels", json.dumps(channels))
        
        if role:
            roles = json.loads(settings.get("automod_whitelist_roles", "[]"))
            if role.id in roles:
                roles.remove(role.id)
                results.append(f"已從白名單移除 {role.mention}")
            else:
                roles.append(role.id)
                results.append(f"已加入白名單 {role.mention}")
            await self.db.update_guild_setting(interaction.guild.id, "automod_whitelist_roles", json.dumps(roles))
        
        await interaction.response.send_message(
            embed=EmbedFactory.success("白名單已更新", "\n".join(results))
        )

    @automod_group.command(name="settings", description="查看自動審核設定")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_settings(self, interaction: discord.Interaction):
        settings = await self.db.get_guild_settings(interaction.guild.id)
        
        def status(key):
            return "✅" if settings.get(key) else "❌"
        
        bad_words = json.loads(settings.get("automod_bad_words", "[]"))
        whitelist_channels = json.loads(settings.get("automod_whitelist_channels", "[]"))
        whitelist_roles = json.loads(settings.get("automod_whitelist_roles", "[]"))
        
        embed = discord.Embed(
            title=f"{Emoji.SHIELD} 自動審核設定",
            color=Colors.AUTOMOD,
        )
        
        embed.add_field(
            name="功能狀態",
            value=(
                f"{status('automod_enabled')} 自動審核（總開關）\n"
                f"{status('automod_spam_enabled')} 刷屏偵測\n"
                f"{status('automod_links_enabled')} 連結過濾\n"
                f"{status('automod_caps_enabled')} 大寫過量偵測"
            ),
            inline=False,
        )
        
        embed.add_field(
            name="過濾詞彙",
            value=f"`{len(bad_words)}` 個詞彙" if bad_words else "（無）",
            inline=True,
        )
        embed.add_field(
            name="最大 Mention 數",
            value=f"`{settings.get('automod_mentions_max', 5)}`",
            inline=True,
        )
        
        if whitelist_channels:
            ch_mentions = [f"<#{cid}>" for cid in whitelist_channels]
            embed.add_field(name="白名單頻道", value=" ".join(ch_mentions), inline=False)
        
        if whitelist_roles:
            role_mentions = [f"<@&{rid}>" for rid in whitelist_roles]
            embed.add_field(name="白名單角色", value=" ".join(role_mentions), inline=False)
        
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
