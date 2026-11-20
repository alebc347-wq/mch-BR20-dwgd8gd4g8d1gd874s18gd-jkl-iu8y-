"""
一般指令 Cog
/help, /ping, /serverinfo, /userinfo, /avatar, /botinfo
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
import platform
import os
import json
import time
import asyncio
import io
from PIL import Image, ImageDraw, ImageFont

from config import Colors, Emoji, BadgeImages, BOT_VERSION
from utils.embeds import EmbedFactory, PaginatorView
from utils.speed_tier import speed_tier
from utils.visual_cards import (
    render_help_banner,
    render_ping_card,
    render_health_card,
    render_profile_card,
    render_server_card,
    render_version_card,
)


class HelpSelectMenu(discord.ui.Select):
    """互動式幫助選單 Select Menu"""
    
    def __init__(self):
        options = [
            discord.SelectOption(
                label="一般指令",
                description="ping、資訊查詢、幫助",
                emoji="ℹ️",
                value="general",
            ),
            discord.SelectOption(
                label="管理系統",
                description="踢出、封禁、禁言、警告",
                emoji="🛡️",
                value="moderation",
            ),
            discord.SelectOption(
                label="自動審核",
                description="髒話過濾、刷屏偵測",
                emoji="🤖",
                value="automod",
            ),
            discord.SelectOption(
                label="日誌系統",
                description="事件記錄、操作追蹤",
                emoji="📋",
                value="logging",
            ),
            discord.SelectOption(
                label="音樂系統",
                description="播放、佇列、音量控制",
                emoji="🎵",
                value="music",
            ),
            discord.SelectOption(
                label="娛樂系統",
                description="迷你遊戲、骰子、21點",
                emoji="🎮",
                value="entertainment",
            ),
            discord.SelectOption(
                label="抽獎系統",
                description="建立抽獎、參加抽獎",
                emoji="🎉",
                value="giveaway",
            ),
            discord.SelectOption(
                label="工具系統",
                description="翻譯、天氣、QR Code、搜尋",
                emoji="🛠️",
                value="tools",
            ),
            discord.SelectOption(
                label="編碼/解碼",
                description="Base64, Hex, Morse, 智能解碼",
                emoji="🔐",
                value="crypto",
            ),
            discord.SelectOption(
                label="計算機",
                description="互動計算機（基本+科學）",
                emoji="🧮",
                value="calculator",
            ),
            discord.SelectOption(
                label="社群互動",
                description="投票、倒數、提醒、工單",
                emoji="📊",
                value="community",
            ),
            discord.SelectOption(
                label="趣味文字",
                description="say, owo, mock, reverse...",
                emoji="✨",
                value="fun_text",
            ),
            discord.SelectOption(
                label="經濟系統",
                description="金幣、簽到、轉帳、排行榜",
                emoji="💰",
                value="economy",
            ),
            discord.SelectOption(
                label="天災監控",
                description="台灣地震+天氣警報推播",
                emoji="🫨",
                value="disaster",
            ),
            discord.SelectOption(
                label="自動回覆",
                description="關鍵字觸發自動回覆",
                emoji="💬",
                value="auto_reply",
            ),
        ]
        super().__init__(placeholder="選擇要查看的指令分類...", options=options)

    async def callback(self, interaction: discord.Interaction):
        help_pages = {
            "general": discord.Embed(
                title=f"{Emoji.INFO} 一般指令",
                description=(
                    "`/help` — 顯示此幫助選單\n"
                    "`/ping` — 查看 Bot 延遲\n"
                    "`/botinfo` — Bot 資訊統計\n"
                    "`/serverinfo` — 伺服器資訊\n"
                    "`/userinfo [@用戶]` — 用戶資訊\n"
                    "`/avatar [@用戶]` — 顯示頭像\n"
                    "`/about` — 關於機器人\n"
                    "`/invite` — 邀請連結\n"
                    "`/uptime` — 運行時間\n"
                    "`/health` — 🩺 系統健康儀表板圖卡\n"
                    "`/plan` `/pro` — ⚡ 3.0 雙方案對比圖卡\n"
                    "`.rest [時間/起訖/off]` `/rest` — 🌙 低耗電休息模式"
                ),
                color=Colors.PRIMARY,
            ),
            "moderation": discord.Embed(
                title=f"{Emoji.SHIELD} 管理系統",
                description=(
                    "**Slash 指令 & 前綴快捷：**\n"
                    "`/kick` `.k` — 踢出用戶\n"
                    "`/ban` `.b` — 封禁（天數 0 = 解封）\n"
                    "`/timeout` `.t` — 禁言\n"
                    "`/warn` — 警告用戶\n"
                    "`/purge` — 批量刪除訊息\n"
                    "`/lock_channel` — 鎖定頻道\n"
                    "`/unlock_channel` — 解除鎖定\n"
                    "`/rename_user` — 更改暱稱\n"
                    "`/dm` — 私訊成員\n"
                    "`/autorole set/remove` — 自動角色"
                ),
                color=Colors.KICK,
            ),
            "automod": discord.Embed(
                title=f"{Emoji.SHIELD} 自動審核",
                description=(
                    "`/automod toggle` — 開關自動審核\n"
                    "`/automod addword` — 新增過濾詞彙\n"
                    "`/automod removeword` — 移除過濾詞彙\n"
                    "`/automod whitelist` — 白名單設定\n"
                    "`/automod settings` — 查看設定"
                ),
                color=Colors.AUTOMOD,
            ),
            "logging": discord.Embed(
                title="📋 日誌系統",
                description=(
                    "`/setlog #頻道` — 設定日誌頻道\n"
                    "`/logconfig` — 配置記錄事件\n\n"
                    "**自動記錄事件：**\n"
                    "• 成員加入/離開\n"
                    "• 訊息編輯/刪除\n"
                    "• 角色變更\n"
                    "• 語音頻道進出\n"
                    "• 正在輸入\n"
                    "• 管理操作"
                ),
                color=Colors.LOG_EDIT,
            ),
            "music": discord.Embed(
                title=f"{Emoji.MUSIC} 音樂系統",
                description=(
                    "`/play <歌曲>` — 播放音樂\n"
                    "`/pause` — 暫停/繼續\n"
                    "`/skip` — 跳過\n"
                    "`/stop` — 停止\n"
                    "`/queue` — 佇列\n"
                    "`/nowplaying` — 正在播放\n"
                    "`/volume <0-100>` — 音量\n"
                    "`/shuffle` — 隨機排列\n"
                    "`/loop` — 循環模式\n"
                    "`/seek <時間>` — 跳轉"
                ),
                color=Colors.MUSIC,
            ),
            "entertainment": discord.Embed(
                title=f"{Emoji.GAME} 娛樂系統",
                description=(
                    "`/guess` — 猜數字\n"
                    "`/dice` — 擲骰子\n"
                    "`/blackjack` — 21 點\n"
                    "`/rps` — 剪刀石頭布\n"
                    "`/coinflip` — 硬幣翻轉\n"
                    "`/8ball` — 神奇 8 號球\n"
                    "`/trivia` — 益智問答\n"
                    "`/slots` — 拉霸老虎機\n"
                    "`/roll` — 擲骰子公式\n"
                    "`/joke` — 隨機笑話\n"
                    "`/quote` — 勵志語錄\n"
                    "`/choose` — 隨機選擇\n"
                    "`/emoji_rain` — 表情雨"
                ),
                color=Colors.GAME,
            ),
            "giveaway": discord.Embed(
                title=f"{Emoji.PARTY} 抽獎系統",
                description=(
                    "`/giveaway start <獎品> <時間> [人數]` — 開始抽獎\n"
                    "`/giveaway end <ID>` — 結束抽獎\n"
                    "`/giveaway reroll <ID>` — 重新抽\n"
                    "`/giveaway list` — 進行中的抽獎"
                ),
                color=Colors.GIVEAWAY,
            ),
            "tools": discord.Embed(
                title="🛠️ 工具系統",
                description=(
                    "`/translate <文字>` — 跨語言翻譯\n"
                    "`/weather <城市>` — 即時天氣\n"
                    "`/qr <文字>` — QR Code 產生器\n"
                    "`/shorten <網址>` — 縮短網址\n"
                    "`/msg_where <關鍵字>` — 搜尋訊息\n"
                    "`/yt <關鍵字>` — YouTube 搜尋\n"
                    "`/bugreport <描述>` — 回報 Bug"
                ),
                color=Colors.PRIMARY,
            ),
            "crypto": discord.Embed(
                title="🔐 編碼/解碼系統",
                description=(
                    "`/encode [text] [steps]` — 編碼\n"
                    "`/decode [text] [steps]` — 解碼\n"
                    "`/smart_decode <text>` — 智能解碼\n\n"
                    "支援 12+ 格式：Base64, Base32, Hex, URL,\n"
                    "ROT13, Morse, Caesar, Binary, HTML 等\n"
                    "多層編碼：`base32>base64>unicode`"
                ),
                color=0x55CCFF,
            ),
            "calculator": discord.Embed(
                title="🧮 互動計算機",
                description=(
                    "`/calculator` — 開啟互動計算機\n\n"
                    "**基本模式：** +, -, *, /, //, %, ^\n"
                    "**進階模式：** sqrt, log, sin, cos, tan\n"
                    "常數：pi, e\n"
                    "使用 Modal 輸入算式，按鈕切換模式"
                ),
                color=Colors.PRIMARY,
            ),
            "community": discord.Embed(
                title="📊 社群互動",
                description=(
                    "`/vote <主題> <選項;選項> <分鐘>` — 投票\n"
                    "`/countdown` — 倒數計時\n"
                    "`/reminder` — 設定提醒\n"
                    "`/ticket` — 開啟工單系統"
                ),
                color=Colors.SUCCESS,
            ),
            "fun_text": discord.Embed(
                title="✨ 趣味文字",
                description=(
                    "`/say` — 讓 Bot 代發言\n"
                    "`/echo` — 重複你的話\n"
                    "`/reverse` — 反轉文字\n"
                    "`/tinytext` — 小字型\n"
                    "`/owo` — OwO 語風格\n"
                    "`/mock` — 嘲諷大小寫\n"
                    "`/spoiler` — 爆雷隱藏\n"
                    "`/repeat` — 重複句子\n"
                    "`/shout` — 大聲說"
                ),
                color=Colors.GAME,
            ),
            "economy": discord.Embed(
                title="💰 經濟系統",
                description=(
                    "`/balance [@成員]` — 查看金幣餘額\n"
                    "`/daily` — 每日簽到\n"
                    "`/pay <成員> <金額>` — 轉帳\n"
                    "`/leaderboard` — 排行榜\n"
                    "`/work` — 打工賺金幣（30 分鐘冷卻）"
                ),
                color=Colors.GAME,
            ),
            "disaster": discord.Embed(
                title="🫨 天災監控系統",
                description=(
                    "`!天災 開啟` — 啟動天災推播\n"
                    "`!天災 關閉` — 關閉天災推播\n"
                    "`!測試天災` — 發送測試推播\n\n"
                    "自動監控 CWA (中央氣象署)：\n"
                    "🫨 地震速報 • ⛈️ 天氣特報\n"
                    "自動建立通知頻道"
                ),
                color=0xFF4444,
            ),
            "auto_reply": discord.Embed(
                title="💬 自動回覆系統",
                description=(
                    "**內建 30+ 組預設回覆**\n\n"
                    "`/add_reply <關鍵字> <回覆>` — 新增回覆\n"
                    "`/remove_reply <關鍵字>` — 移除回覆\n"
                    "`/list_replies` — 列出所有回覆"
                ),
                color=Colors.PRIMARY,
            ),
        }
        
        embed = help_pages.get(self.values[0])
        if embed:
            embed.set_footer(text="使用選單切換不同分類")
            await interaction.response.edit_message(embed=embed)


class HelpView(discord.ui.View):
    """倉鼠勇者 3.0 幫助中樞互動介面（分類選單 + 極速快捷按鈕）"""
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=180)
        self.bot = bot
        self.add_item(HelpSelectMenu())

    @discord.ui.button(label="⚡ 3.0 雙方案", style=discord.ButtonStyle.primary, row=1)
    async def btn_plan(self, interaction: discord.Interaction, button: discord.ui.Button):
        pro_cog = self.bot.get_cog("Pro")
        if pro_cog and hasattr(pro_cog, "_send_plan_panel"):
            await pro_cog._send_plan_panel(interaction)
        else:
            await interaction.response.send_message("請輸入 `/plan` 查看 3.0 Free / Pro 雙方案。", ephemeral=True)

    @discord.ui.button(label="🏓 極速測速", style=discord.ButtonStyle.secondary, row=1)
    async def btn_ping(self, interaction: discord.Interaction, button: discord.ui.Button):
        gen_cog = self.bot.get_cog("General")
        if gen_cog:
            await gen_cog._send_ping_card(interaction)
        else:
            await interaction.response.send_message(f"🏓 `{round(self.bot.latency * 1000)} ms`", ephemeral=True)

    @discord.ui.button(label="🩺 健康儀表板", style=discord.ButtonStyle.secondary, row=1)
    async def btn_health(self, interaction: discord.Interaction, button: discord.ui.Button):
        gen_cog = self.bot.get_cog("General")
        if gen_cog:
            await gen_cog._send_health_card(interaction)
        else:
            await interaction.response.send_message("請輸入 `/health` 查看系統健康度。", ephemeral=True)


class General(commands.Cog):
    """一般指令 (倉鼠勇者 3.0 極速視覺版)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _probe_db_ms(self) -> tuple[bool, float]:
        if not getattr(self.bot, "db", None) or not self.bot.db.db:
            return False, -1.0
        t0 = time.perf_counter()
        try:
            async with self.bot.db.db.execute("SELECT 1") as cur:
                await cur.fetchone()
            return True, round((time.perf_counter() - t0) * 1000, 2)
        except Exception:
            return False, -1.0

    async def _send_ping_card(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ws_ms = round(self.bot.latency * 1000, 1) if self.bot.latency == self.bot.latency else 0.0
        _, db_ms = await self._probe_db_ms()
        is_pro = await speed_tier.is_guild_pro_fast(self.bot.db, interaction.guild_id)

        img_buf = await render_ping_card(ws_ms, max(db_ms, 0.0), is_pro)
        file = discord.File(img_buf, filename="ping_3_0.png")
        embed = discord.Embed(
            color=Colors.PRO if is_pro else Colors.PRIMARY,
        )
        embed.set_image(url="attachment://ping_3_0.png")
        await interaction.followup.send(embed=embed, file=file, ephemeral=True)

    async def _send_health_card(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ws_ms = round(self.bot.latency * 1000, 1) if self.bot.latency == self.bot.latency else 0.0
        db_ok, db_ms = await self._probe_db_ms()

        server_id = os.getenv("SERVER_ID", "單機模式")
        is_active = getattr(self.bot, "is_active_node", True)
        is_resting = getattr(self.bot, "is_resting", False)
        node_label = f"ACTIVE ({server_id})" if is_active else f"IDLE ({server_id})"

        lavalink_label = "未初始化"
        try:
            import wavelink
            nodes = list(wavelink.Pool.nodes.values())
            if nodes:
                connected = sum(1 for n in nodes if n.status == wavelink.NodeStatus.CONNECTED)
                lavalink_label = f"{connected}/{len(nodes)} 節點在線"
            else:
                lavalink_label = "無連線節點"
        except Exception:
            lavalink_label = "無法偵測"

        uptime_secs = int(time.time() - getattr(self.bot, "_start_time", time.time()))
        days, rem = divmod(uptime_secs, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{days}天 {hours}時 {minutes}分" if days else f"{hours}時 {minutes}分 {seconds}秒"

        img_buf = await render_health_card(
            ws_ms=ws_ms,
            db_ms=max(db_ms, 0.0),
            db_ok=db_ok,
            node_label=node_label,
            is_active=is_active,
            is_resting=is_resting,
            lavalink_label=lavalink_label,
            cog_count=len(self.bot.cogs),
            uptime_str=uptime_str,
            guild_count=len(self.bot.guilds),
        )
        file = discord.File(img_buf, filename="health_3_0.png")
        embed = discord.Embed(
            color=Colors.SUCCESS if (is_active and db_ok and not is_resting) else Colors.WARNING,
        )
        embed.set_image(url="attachment://health_3_0.png")
        await interaction.followup.send(embed=embed, file=file, ephemeral=True)

    @app_commands.command(name="help", description="顯示倉鼠勇者 3.0 互動式指令中樞")
    async def help_command(self, interaction: discord.Interaction):
        await interaction.response.defer()
        is_pro = await speed_tier.is_guild_pro_fast(self.bot.db, interaction.guild_id)
        ws_ms = round(self.bot.latency * 1000, 1) if self.bot.latency == self.bot.latency else 0.0
        img_buf = await render_help_banner(is_pro, len(self.bot.guilds), len(self.bot.cogs), ws_ms)
        file = discord.File(img_buf, filename="help_banner_3_0.png")

        embed = discord.Embed(
            color=Colors.PRO if is_pro else Colors.PRIMARY,
        )
        embed.set_image(url="attachment://help_banner_3_0.png")
        embed.set_footer(text=f"倉鼠勇者 {BOT_VERSION} • 請由下方選單切換功能分類或使用快捷按鈕")

        view = HelpView(self.bot)
        await interaction.followup.send(embed=embed, file=file, view=view)

    @app_commands.command(name="ping", description="查看倉鼠勇者 3.0 極速測速圖卡")
    async def ping(self, interaction: discord.Interaction):
        await self._send_ping_card(interaction)

    @app_commands.command(name="botinfo", description="顯示 Bot 資訊與統計")
    async def botinfo(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"{Emoji.INFO} Bot 資訊",
            color=Colors.PRIMARY,
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        
        # 統計
        total_members = sum(g.member_count or 0 for g in self.bot.guilds)
        total_channels = sum(len(g.channels) for g in self.bot.guilds)
        
        embed.add_field(name="**伺服器數**", value=f"`{len(self.bot.guilds)}`", inline=True)
        embed.add_field(name="**總用戶數**", value=f"`{total_members}`", inline=True)
        embed.add_field(name="**頻道數**", value=f"`{total_channels}`", inline=True)
        embed.add_field(name="**延遲**", value=f"`{round(self.bot.latency * 1000)}ms`", inline=True)
        embed.add_field(name="**Python**", value=f"`{platform.python_version()}`", inline=True)
        embed.add_field(name="**discord.py**", value=f"`{discord.__version__}`", inline=True)
        embed.add_field(name="**系統**", value=f"`{platform.system()} {platform.release()}`", inline=True)
        
        embed.set_footer(
            text=f"Bot ID: {self.bot.user.id}",
            icon_url=self.bot.user.display_avatar.url,
        )
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="顯示伺服器 3.0 視覺總覽卡片")
    async def serverinfo(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("❌ 此指令僅限在伺服器中使用。", ephemeral=True)
        await interaction.response.defer()
        guild = interaction.guild
        is_pro = await speed_tier.is_guild_pro_fast(self.bot.db, guild.id)

        icon_bytes = None
        if guild.icon:
            try:
                icon_bytes = await guild.icon.replace(format="png", size=256).read()
            except Exception:
                pass

        online_count = sum(1 for m in guild.members if m.status != discord.Status.offline)
        img_buf = await render_server_card(
            guild_name=guild.name,
            guild_id=guild.id,
            is_pro=is_pro,
            member_count=guild.member_count or len(guild.members),
            online_count=online_count,
            text_count=len(guild.text_channels),
            voice_count=len(guild.voice_channels),
            role_count=len(guild.roles),
            boost_tier=guild.premium_tier,
            icon_bytes=icon_bytes,
        )
        file = discord.File(img_buf, filename="server_card_3_0.png")
        embed = discord.Embed(color=Colors.PRO if is_pro else Colors.PRIMARY)
        embed.set_image(url="attachment://server_card_3_0.png")
        embed.set_footer(text=f"建立於 {guild.created_at.strftime('%Y-%m-%d')} • 倉鼠勇者 {BOT_VERSION}")
        await interaction.followup.send(embed=embed, file=file)

    @app_commands.command(name="userinfo", description="顯示成員 3.0 視覺檔案卡片")
    @app_commands.describe(user="要查詢的用戶（不填則查詢自己）")
    async def userinfo(self, interaction: discord.Interaction, user: discord.Member = None):
        await interaction.response.defer()
        target = user or interaction.user
        is_pro = await speed_tier.is_guild_pro_fast(self.bot.db, interaction.guild_id)

        avatar_bytes = None
        try:
            avatar_bytes = await target.display_avatar.replace(format="png", size=256).read()
        except Exception:
            pass

        roles = [r.name for r in reversed(getattr(target, "roles", [])) if r.name != "@everyone"]
        created_str = target.created_at.strftime("%Y-%m-%d")
        joined_str = target.joined_at.strftime("%Y-%m-%d") if getattr(target, "joined_at", None) else "未知"

        img_buf = await render_profile_card(
            display_name=target.display_name,
            username=target.name,
            user_id=target.id,
            is_pro=is_pro,
            roles=roles,
            joined_str=joined_str,
            created_str=created_str,
            avatar_bytes=avatar_bytes,
        )
        file = discord.File(img_buf, filename="profile_card_3_0.png")
        embed = discord.Embed(color=Colors.PRO if is_pro else Colors.PRIMARY)
        embed.set_image(url="attachment://profile_card_3_0.png")
        await interaction.followup.send(embed=embed, file=file)

    @app_commands.command(name="avatar", description="顯示用戶頭像")
    @app_commands.describe(user="要查看頭像的用戶")
    async def avatar(self, interaction: discord.Interaction, user: discord.Member = None):
        user = user or interaction.user
        
        embed = discord.Embed(
            title=f"🖼️ {user.display_name} 的頭像",
            color=user.color if user.color != discord.Color.default() else Colors.PRIMARY,
        )
        embed.set_image(url=user.display_avatar.url)
        
        # 不同格式的下載連結
        avatar_url = user.display_avatar
        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label="PNG",
            style=discord.ButtonStyle.link,
            url=str(avatar_url.replace(format="png", size=1024)),
        ))
        view.add_item(discord.ui.Button(
            label="JPG",
            style=discord.ButtonStyle.link,
            url=str(avatar_url.replace(format="jpg", size=1024)),
        ))
        view.add_item(discord.ui.Button(
            label="WEBP",
            style=discord.ButtonStyle.link,
            url=str(avatar_url.replace(format="webp", size=1024)),
        ))
        if avatar_url.is_animated():
            view.add_item(discord.ui.Button(
                label="GIF",
                style=discord.ButtonStyle.link,
                url=str(avatar_url.replace(format="gif", size=1024)),
            ))
        
        await interaction.response.send_message(embed=embed, view=view)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ABOUT / INVITE / UPTIME
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.command(name="about", description="📖 關於這個機器人")
    async def about(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 關於機器人",
            description=(
                "這是一個功能豐富的 Discord 機器人，擁有管理、娛樂、音樂、經濟、工具等多種系統。\n\n"
                "**主要功能：**\n"
                "🛡️ 管理系統 — 踢出、封禁、禁言、警告\n"
                "🎵 音樂系統 — YouTube/SoundCloud 播放、佇列管理\n"
                "🎮 娛樂系統 — 21點、猜數字、骰子\n"
                "💰 經濟系統 — 金幣、簽到、排行榜\n"
                "🔐 編碼系統 — 12+ 編解碼格式\n"
                "🧮 計算機 — 基本/科學模式\n"
                "📩 工單系統 — 自動建立私人工單\n"
                "🫨 天災監控 — 台灣地震+天氣警報\n"
                "🤖 自動回覆 — 關鍵字觸發回覆\n"
            ),
            color=Colors.PRIMARY,
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="invite", description="🔗 取得機器人的邀請連結")
    async def invite(self, interaction: discord.Interaction):
        invite_url = discord.utils.oauth_url(
            self.bot.user.id,
            permissions=discord.Permissions(administrator=True),
        )
        embed = discord.Embed(
            title="🔗 邀請機器人",
            description=f"[點我邀請機器人到你的伺服器！]({invite_url})",
            color=Colors.PRIMARY,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="uptime", description="⏱ 查看機器人運行時間")
    async def uptime(self, interaction: discord.Interaction):
        import time
        uptime_seconds = time.time() - self.bot._start_time
        hours, remainder = divmod(int(uptime_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        parts = []
        if days:
            parts.append(f"{days} 天")
        if hours:
            parts.append(f"{hours} 小時")
        if minutes:
            parts.append(f"{minutes} 分鐘")
        parts.append(f"{seconds} 秒")

        embed = discord.Embed(
            title="⏱ 運行時間",
            description=f"機器人已持續運行 **{' '.join(parts)}**",
            color=Colors.SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # VERSION — 倉鼠勇者 3.0 即時程式圖片版本卡（零等待）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="version", description="即時查看倉鼠勇者 3.0 版本資訊視覺卡")
    async def version(self, interaction: discord.Interaction):
        await interaction.response.defer()
        is_pro = await speed_tier.is_guild_pro_fast(self.bot.db, interaction.guild_id)
        img_buf = await render_version_card(BOT_VERSION, is_pro)
        file = discord.File(img_buf, filename="version_3_0.png")

        embed = discord.Embed(
            color=Colors.PRO if is_pro else Colors.PRIMARY,
        )
        embed.set_image(url="attachment://version_3_0.png")
        embed.set_footer(text=f"倉鼠勇者 {BOT_VERSION} • 即時渲染（已移除假載入動畫）")
        await interaction.followup.send(embed=embed, file=file)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # JOIN — 宣傳與 Email 聯絡
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="join", description="📩 加入我們，接收最新功能資訊")
    async def join_info(self, interaction: discord.Interaction):
        FEATURE_IMG = "https://cf71d14b5d.cbaul-cdnwnd.com/e0dba41b4ac2639df429cc67c9dae4d4/200000013-686aa686ac/450/pngtree-sophisticated-violet-gradient-linear-texture-background-image_13768869.webp?ph=cf71d14b5d"
        embed = discord.Embed(
            title="💌 歡迎加入我們！",
            description=(
                "想要第一時間收到最新的功能與活動資訊嗎？\n\n"
                "📩 聯絡 Email：**alebc347@gmail.com**\n"
                "🔗 最新功能連結與圖片將會固定貼在這裡！"
            ),
            color=0x8e44ad
        )
        embed.set_image(url=FEATURE_IMG)
        await interaction.response.send_message(embed=embed, view=JoinInfoView(), ephemeral=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HEALTH — 3.0 系統健康儀表板視覺卡
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="health", description="🩺 檢查倉鼠勇者 3.0 系統健康儀表板視覺卡")
    async def health(self, interaction: discord.Interaction):
        await self._send_health_card(interaction)



    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DM 指令 — 群發/指定發送私訊
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @commands.command(name="dm")
    async def dm_command(self, ctx: commands.Context, *, args: str = None):
        """
        私訊發送指令 (僅限機器人擁有者)
        用法：
        .dm all <訊息> — 發送訊息給所有伺服器的擁有者
        .dm @使用者1 [@使用者2 ...] <訊息> — 發送訊息給指定使用者
        .dm <使用者ID1> [<使用者ID2> ...] <訊息> — 發送訊息給指定 ID 的使用者
        """
        # 權限檢查：僅限機器人擁有者
        is_owner = (ctx.author.id == 1437408048934027274) or await self.bot.is_owner(ctx.author)
        if not is_owner:
            return await ctx.reply("❌ 此指令僅限機器人擁有者使用！", mention_author=False)

        if not args or not args.strip():
            embed = EmbedFactory.info(
                "📬 私訊指令使用說明",
                "**發送給所有伺服器擁有者：**\n"
                "`.dm all <訊息內容>`\n\n"
                "**發送給所有伺服器的所有人 (全成員廣播)：**\n"
                "`.dm everyone <訊息內容>`\n\n"
                "**發送給指定使用者 (支援 1 位或多位)：**\n"
                "`.dm @使用者1 [@使用者2 ...] <訊息內容>`\n"
                "`.dm <使用者ID1> [<使用者ID2> ...] <訊息內容>`"
            )
            return await ctx.reply(embed=embed, mention_author=False)

        args_clean = args.strip()
        tokens = args_clean.split()

        # 讀取附件數據 (若有)
        attachment_files_data = []
        if ctx.message.attachments:
            for att in ctx.message.attachments:
                try:
                    data = await att.read()
                    attachment_files_data.append((att.filename, data))
                except Exception as ex:
                    print(f"[DM Command] 讀取附件 {att.filename} 失敗: {ex}")

        # 1. 判斷廣播選項：.dm all <訊息> (所有伺服器擁有者) 或 .dm everyone <訊息> (所有伺服器的所有人)
        first_token = tokens[0].lower()
        if first_token in ("everyone", "all_members", "allmembers", "members"):
            message_text = args_clean[len(tokens[0]):].strip()
            if not message_text and not attachment_files_data:
                return await ctx.reply("❌ 請提供要發送給所有伺服器成員的訊息內容！\n範例：`.dm everyone 系統廣播通知訊息`", mention_author=False)

            target_members: dict[int, discord.User | discord.Member] = {}
            for guild in self.bot.guilds:
                for member in guild.members:
                    if not member.bot and member.id not in target_members:
                        target_members[member.id] = member

            if not target_members:
                return await ctx.reply("❌ 未能獲取任何伺服器成員。", mention_author=False)

            total_count = len(target_members)
            status_msg = await ctx.reply(f"⏳ 正在開始向所有伺服器的 {total_count} 位成員發送廣播私訊...", mention_author=False)

            success_count = 0
            fail_count = 0
            last_update_time = time.time()

            for idx, member_user in enumerate(target_members.values(), 1):
                try:
                    embed = self._create_styled_dm_embed(
                        sender=ctx.author,
                        guild=ctx.guild,
                        message_text=message_text,
                        is_broadcast=True
                    )

                    files = [
                        discord.File(io.BytesIO(data), filename=filename)
                        for filename, data in attachment_files_data
                    ]

                    await member_user.send(embed=embed, files=files if files else None)
                    success_count += 1
                except Exception as e:
                    print(f"[DM Command] 發送至成員 {member_user} (ID: {member_user.id}) 失敗: {e}")
                    fail_count += 1

                # 每 5 秒更新一次進度狀態
                now = time.time()
                if now - last_update_time >= 5.0 or idx == total_count:
                    last_update_time = now
                    try:
                        await status_msg.edit(
                            content=f"⏳ **全服所有人廣播發送中... ({idx}/{total_count})**\n"
                                    f"• 成功：`{success_count}` 人\n"
                                    f"• 失敗/關閉私訊：`{fail_count}` 人"
                        )
                    except Exception:
                        pass
                
                await asyncio.sleep(0.6)  # 避免觸發 API 頻率限制

            return await status_msg.edit(
                content=f"✅ **全服所有人廣播完畢！**\n"
                        f"• 總成員數：`{total_count}` 人\n"
                        f"• 成功發送：`{success_count}` 人\n"
                        f"• 失敗/關閉私訊：`{fail_count}` 人"
            )

        if first_token == "all":
            message_text = args_clean[3:].strip()
            if not message_text and not attachment_files_data:
                return await ctx.reply("❌ 請提供要發送給伺服器擁有者的訊息內容！\n範例：`.dm all 系統通知訊息`", mention_author=False)

            target_owners: dict[int, discord.User | discord.Member] = {}
            for guild in self.bot.guilds:
                owner = guild.owner
                if not owner and guild.owner_id:
                    try:
                        owner = await self.bot.fetch_user(guild.owner_id)
                    except Exception:
                        owner = None
                if owner and owner.id not in target_owners:
                    target_owners[owner.id] = owner

            if not target_owners:
                return await ctx.reply("❌ 未能獲取任何伺服器擁有者。", mention_author=False)

            status_msg = await ctx.reply(f"⏳ 正在開始為 {len(target_owners)} 位伺服器擁有者發送私訊...", mention_author=False)

            success_count = 0
            fail_count = 0

            for owner_user in target_owners.values():
                try:
                    embed = self._create_styled_dm_embed(
                        sender=ctx.author,
                        guild=ctx.guild,
                        message_text=message_text,
                        is_broadcast=True
                    )

                    files = [
                        discord.File(io.BytesIO(data), filename=filename)
                        for filename, data in attachment_files_data
                    ]

                    await owner_user.send(embed=embed, files=files if files else None)
                    success_count += 1
                except Exception as e:
                    print(f"[DM Command] 發送至伺服器擁有者 {owner_user} (ID: {owner_user.id}) 失敗: {e}")
                    fail_count += 1
                
                await asyncio.sleep(0.5)

            return await status_msg.edit(
                content=f"✅ **廣播完畢！**\n"
                        f"• 成功發送：`{success_count}` 人\n"
                        f"• 失敗/關閉私訊：`{fail_count}` 人"
            )

        # 2. 針對指定使用者：.dm @使用者1 [@使用者2 ...] <訊息>
        targets: list[discord.User | discord.Member] = []
        seen_ids = set()

        used_tokens_count = 0
        for token in tokens:
            cleaned_id_str = token.strip("<@!>")
            if cleaned_id_str.isdigit():
                uid = int(cleaned_id_str)
                found_user = None
                for m in ctx.message.mentions:
                    if m.id == uid:
                        found_user = m
                        break
                if not found_user:
                    found_user = ctx.guild.get_member(uid) if ctx.guild else None
                if not found_user:
                    try:
                        found_user = await self.bot.fetch_user(uid)
                    except Exception:
                        found_user = None

                if found_user:
                    if found_user.id not in seen_ids:
                        targets.append(found_user)
                        seen_ids.add(found_user.id)
                    used_tokens_count += 1
                else:
                    break
            else:
                break

        if used_tokens_count > 0:
            remaining_tokens = tokens[used_tokens_count:]
            message_text = " ".join(remaining_tokens).strip()
        else:
            if ctx.message.mentions:
                targets = list(ctx.message.mentions)
                message_text = args_clean
                for m in ctx.message.mentions:
                    message_text = message_text.replace(f"<@{m.id}>", "").replace(f"<@!{m.id}>", "").strip()
            else:
                message_text = ""

        if not targets:
            return await ctx.reply(
                "❌ 無法解析目標使用者！\n"
                "格式：\n"
                "• 廣播給所有伺服器擁有者：`.dm all <訊息>`\n"
                "• 發送給指定使用者：`.dm @使用者1 [@使用者2 ...] <訊息>`",
                mention_author=False
            )

        if not message_text and not attachment_files_data:
            return await ctx.reply("❌ 請提供要發送的訊息內容！", mention_author=False)

        success_count = 0
        fail_count = 0
        failed_names = []

        for target_user in targets:
            try:
                embed = self._create_styled_dm_embed(
                    sender=ctx.author,
                    guild=ctx.guild,
                    message_text=message_text,
                    is_broadcast=False
                )

                files = [
                    discord.File(io.BytesIO(data), filename=filename)
                    for filename, data in attachment_files_data
                ]

                await target_user.send(embed=embed, files=files if files else None)
                success_count += 1
            except Exception as e:
                print(f"[DM Command] 發送至 {target_user} (ID: {target_user.id}) 失敗: {e}")
                fail_count += 1
                failed_names.append(target_user.mention)

            await asyncio.sleep(0.3)

        target_mentions = ", ".join([t.mention for t in targets])
        if fail_count == 0:
            return await ctx.reply(f"✅ 已成功發送私訊給 {target_mentions}！", mention_author=False)
        else:
            fail_str = ", ".join(failed_names)
            return await ctx.reply(
                f"⚠️ 發送結果：成功 `{success_count}` 人，失敗 `{fail_count}` 人 ({fail_str} 可能已關閉私訊)。",
                mention_author=False
            )

    def _create_styled_dm_embed(
        self,
        sender: discord.User | discord.Member,
        guild: discord.Guild | None,
        message_text: str,
        is_broadcast: bool = False
    ) -> discord.Embed:
        """建立極簡且美觀的私訊通知 Embed"""
        embed = discord.Embed(
            title="📢 系統廣播" if is_broadcast else "📬 系統通知",
            description=message_text if message_text else "*(請查看隨附的檔案/圖片附件)*",
            color=Colors.PRIMARY,
            timestamp=datetime.now(timezone.utc)
        )
        
        bot_name = self.bot.user.name if self.bot.user else "勇者 Bot"
        bot_avatar = self.bot.user.display_avatar.url if self.bot.user else None
        embed.set_footer(
            text=f"{bot_name} • 請勿直接回覆此訊息",
            icon_url=bot_avatar
        )
        return embed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# JoinInfoView UI 元件
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class JoinInfoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        select = discord.ui.Select(
            placeholder="選擇一個方式來加入我們",
            custom_id="join_select",
            options=[
                discord.SelectOption(label="📩 透過 Email 接收資訊", description="Email: alebc347@gmail.com"),
                discord.SelectOption(label="🔗 查看最新功能連結", description="立刻查看最新的更新資訊"),
                discord.SelectOption(label="📷 查看宣傳圖片", description="點擊後會顯示新功能圖片"),
            ]
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        choice = interaction.data["values"][0]
        FEATURE_IMG = "https://cf71d14b5d.cbaul-cdnwnd.com/e0dba41b4ac2639df429cc67c9dae4d4/200000013-686aa686ac/450/pngtree-sophisticated-violet-gradient-linear-texture-background-image_13768869.webp?ph=cf71d14b5d"

        if "Email" in choice:
            await interaction.response.send_message("📩 您可以透過 **alebc347@gmail.com** 聯絡我們，並接收最新資訊。", ephemeral=True)
        elif "最新功能" in choice:
            await interaction.response.send_message("🔗 最新功能更新將會在這裡貼出！歡迎常來看看喔～✨", ephemeral=True)
        elif "圖片" in choice:
            embed = discord.Embed(
                title="✨ 新功能圖片",
                description="這是我們最新的功能宣傳圖！",
                color=0x9b59b6
            )
            embed.set_image(url=FEATURE_IMG)
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))

