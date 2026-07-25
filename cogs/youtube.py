"""
YouTube 訂閱通知 Cog
定時輪詢 YouTube RSS 頻道，發現新上傳影片時發送精美 Embed 通知
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from config import Colors, Emoji
from utils.embeds import EmbedFactory


class YouTubeNotifier(commands.Cog):
    """YouTube 影片更新通知系統"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.check_youtube_channels.start()

    def cog_unload(self):
        self.check_youtube_channels.cancel()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 輔助方法
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _resolve_channel_id(self, input_str: str) -> tuple[str, str] | None:
        """
        將使用者輸入的網址、名稱、或頻道 ID 解析為 (channel_id, channel_name)
        """
        input_str = input_str.strip()

        # 1. 檢查是否為直接的 Channel ID (UC 開頭，24 位字元)
        if re.match(r"^UC[a-zA-Z0-9_-]{22}$", input_str):
            name = await self._fetch_channel_name(input_str)
            if name:
                return input_str, name
            return None

        # 2. 檢查是否為標準 YouTube 頻道網址
        match = re.search(r"youtube\.com/channel/(UC[a-zA-Z0-9_-]{22})", input_str)
        if match:
            cid = match.group(1)
            name = await self._fetch_channel_name(cid)
            if name:
                return cid, name
            return None

        # 3. 處理 @username 使用者名稱或自訂 URL
        username = None
        if input_str.startswith("@"):
            username = input_str
        else:
            m = re.search(r"youtube\.com/(@[a-zA-Z0-9_.-]+)", input_str)
            if m:
                username = m.group(1)

        target_url = f"https://www.youtube.com/{username}" if username else input_str

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(target_url, headers=headers) as response:
                    if response.status != 200:
                        return None
                    html = await response.text()

                    # 從網頁 HTML 提取 channelId
                    patterns = [
                        r'itemprop="channelId"\s+content="(UC[a-zA-Z0-9_-]{22})"',
                        r'href="https://www.youtube.com/channel/(UC[a-zA-Z0-9_-]{22})"',
                        r'"channelId":"(UC[a-zA-Z0-9_-]{22})"'
                    ]
                    for pat in patterns:
                        m = re.search(pat, html)
                        if m:
                            cid = m.group(1)
                            name = await self._fetch_channel_name(cid)
                            if name:
                                return cid, name
        except Exception as e:
            print(f"解析 YouTube 頻道網址時出錯 ({input_str}): {e}")
        return None

    async def _fetch_channel_name(self, channel_id: str) -> str | None:
        """從 RSS 獲取 YouTube 頻道名稱"""
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        xml_data = await resp.text()
                        root = ET.fromstring(xml_data)
                        namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
                        title_el = root.find('atom:title', namespaces)
                        if title_el is not None:
                            return title_el.text
        except Exception as e:
            print(f"獲取頻道名稱時出錯 ({channel_id}): {e}")
        return None

    async def _fetch_latest_videos(self, channel_id: str) -> list[dict]:
        """獲取最新影片列表"""
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return []
                    xml_data = await resp.text()
                    
                    root = ET.fromstring(xml_data)
                    namespaces = {
                        'atom': 'http://www.w3.org/2005/Atom',
                        'yt': 'http://www.youtube.com/xml/schemas/2015'
                    }

                    videos = []
                    for entry in root.findall('atom:entry', namespaces):
                        video_id_el = entry.find('yt:videoId', namespaces)
                        video_id = video_id_el.text if video_id_el is not None else None
                        
                        title_el = entry.find('atom:title', namespaces)
                        title = title_el.text if title_el is not None else None
                        
                        published_el = entry.find('atom:published', namespaces)
                        published = published_el.text if published_el is not None else None
                        
                        author_name_el = entry.find('atom:author/atom:name', namespaces)
                        channel_name = author_name_el.text if author_name_el is not None else None
                        
                        if video_id and title:
                            videos.append({
                                'video_id': video_id,
                                'title': title,
                                'published': published,
                                'channel_name': channel_name,
                                'channel_id': channel_id,
                                'video_url': f"https://www.youtube.com/watch?v={video_id}",
                                'thumbnail_url': f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
                            })
                    # 按發布時間由舊到新排序，便於依次發送通知
                    videos.reverse()
                    return videos
        except Exception as e:
            print(f"獲取最新影片時出錯 ({channel_id}): {e}")
        return []

    async def _check_and_notify(self):
        """檢查所有訂閱並發送新影片通知"""
        all_subs = await self.db.get_all_youtube_subs()
        if not all_subs:
            return

        # 整理出不重複的頻道 ID 以優化網路請求
        channels_to_check = set(sub['channel_id'] for sub in all_subs)

        # 每個頻道拉取一次 RSS
        latest_data = {}
        for cid in channels_to_check:
            videos = await self._fetch_latest_videos(cid)
            if videos:
                latest_data[cid] = videos

        # 遍歷所有訂閱進行比對與通知
        for sub in all_subs:
            cid = sub['channel_id']
            guild_id = sub['guild_id']
            notify_chan_id = sub['notification_channel_id']
            last_vid = sub['last_video_id']

            # 確保伺服器與頻道有效
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            channel = guild.get_channel(notify_chan_id)
            if not channel:
                continue

            videos = latest_data.get(cid, [])
            if not videos:
                continue

            # 如果資料庫尚未記錄 last_video_id，則將最新的影片設為 baseline (不通知舊影片)
            if not last_vid:
                newest = videos[-1]
                await self.db.update_youtube_last_video(
                    channel_id=cid,
                    guild_id=guild_id,
                    video_id=newest['video_id'],
                    published=newest['published']
                )
                continue

            # 尋找比 last_video_id 新的影片
            new_videos = []
            found_last = False
            for v in videos:
                if v['video_id'] == last_vid:
                    found_last = True
                    continue
                if found_last:
                    new_videos.append(v)

            # 如果沒有在 RSS feed 中找到 last_video_id (可能是被刪除或過舊)，
            # 則檢查發布時間
            if not found_last and last_vid:
                last_pub = sub['last_published']
                for v in videos:
                    if last_pub and v['published'] > last_pub:
                        new_videos.append(v)

            # 發送通知
            for v in new_videos:
                embed = discord.Embed(
                    title=f"🎥 YouTube 影片更新通知",
                    description=f"**[{v['title']}]({v['video_url']})**",
                    color=0xFF0000, # YouTube 紅色
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_author(
                    name=v['channel_name'],
                    url=f"https://www.youtube.com/channel/{v['channel_id']}",
                    icon_url="https://files.catbox.moe/60d0si.png" # 影片播放圖標
                )
                embed.set_image(url=v['thumbnail_url'])
                embed.add_field(name="頻道連結", value=f"[點我前往頻道](https://www.youtube.com/channel/{v['channel_id']})", inline=True)
                embed.add_field(name="影片網址", value=f"[觀看影片]({v['video_url']})", inline=True)
                embed.set_footer(text=f"伺服器id: {guild.id}", icon_url=self.bot.user.display_avatar.url)

                try:
                    await channel.send(
                        content=f"🔔 **{v['channel_name']}** 發布了新影片！ @everyone",
                        embed=embed
                    )
                except discord.Forbidden:
                    print(f"❌ 缺少發送權限至頻道 {channel.name} ({guild.name})")

                # 更新最新已通知影片
                await self.db.update_youtube_last_video(
                    channel_id=cid,
                    guild_id=guild_id,
                    video_id=v['video_id'],
                    published=v['published']
                )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 輪詢背景任務
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @tasks.loop(minutes=5.0)
    async def check_youtube_channels(self):
        """定時檢查 YouTube 是否有新影片"""
        try:
            await self._check_and_notify()
        except Exception as e:
            print(f"YouTube 輪詢發生異常: {e}")

    @check_youtube_channels.before_loop
    async def before_check_youtube(self):
        await self.bot.wait_until_ready()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Slash Commands
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="youtube", description="YouTube 影片通知管理")
    @app_commands.choices(action=[
        app_commands.Choice(name="新增訂閱 (add)", value="add"),
        app_commands.Choice(name="移除訂閱 (remove)", value="remove"),
        app_commands.Choice(name="查看訂閱 (list)", value="list"),
        app_commands.Choice(name="手動檢測 (check)", value="check"),
    ])
    @app_commands.describe(
        action="要執行的動作",
        url_or_id="YouTube 頻道網址、@使用者名稱 或 頻道ID（新增/移除時必填）",
        channel="接收通知的文字頻道（若不填則預設為目前頻道）"
    )
    async def youtube_cmd(
        self,
        interaction: discord.Interaction,
        action: str,
        url_or_id: str = None,
        channel: discord.TextChannel = None
    ):
        guild_id = interaction.guild.id
        
        if action == "add":
            if not url_or_id:
                return await interaction.response.send_message(
                    embed=EmbedFactory.error("參數缺失", "新增訂閱時必須填寫 `url_or_id` 參數！"),
                    ephemeral=True
                )
            
            await interaction.response.defer(ephemeral=True)
            
            # 解析頻道資訊
            res = await self._resolve_channel_id(url_or_id)
            if not res:
                return await interaction.followup.send(
                    embed=EmbedFactory.error("無效的 YouTube 頻道", "無法解析此頻道資訊，請檢查網址或 @使用者名稱 是否正確。"),
                    ephemeral=True
                )
            
            channel_id, channel_name = res
            notify_channel = channel or interaction.channel
            
            # 獲取目前的最新影片做為 baseline，避免洗板
            videos = await self._fetch_latest_videos(channel_id)
            last_vid = videos[-1]['video_id'] if videos else None
            last_pub = videos[-1]['published'] if videos else None
            
            # 寫入資料庫
            await self.db.add_youtube_sub(
                channel_id=channel_id,
                channel_name=channel_name,
                guild_id=guild_id,
                notification_channel_id=notify_channel.id
            )
            if last_vid:
                await self.db.update_youtube_last_video(
                    channel_id=channel_id,
                    guild_id=guild_id,
                    video_id=last_vid,
                    published=last_pub
                )
                
            embed = EmbedFactory.success(
                "YouTube 訂閱成功",
                f"機器人已訂閱 **{channel_name}**！\n當該頻道更新影片時，會發送通知至 {notify_channel.mention}"
            )
            embed.add_field(name="YouTube 頻道 ID", value=f"`{channel_id}`", inline=False)
            embed.set_thumbnail(url="https://files.catbox.moe/60d0si.png")
            await interaction.followup.send(embed=embed)

        elif action == "remove":
            if not url_or_id:
                return await interaction.response.send_message(
                    embed=EmbedFactory.error("參數缺失", "移除訂閱時必須填寫 `url_or_id` 參數！"),
                    ephemeral=True
                )
                
            await interaction.response.defer(ephemeral=True)
            
            # 先嘗試解析，若解析不到就當作 channel_id 直接刪除
            res = await self._resolve_channel_id(url_or_id)
            channel_id = res[0] if res else url_or_id
            
            success = await self.db.remove_youtube_sub(channel_id, guild_id)
            if success:
                display_name = res[1] if res else channel_id
                await interaction.followup.send(
                    embed=EmbedFactory.success("訂閱已移除", f"已成功取消訂閱 YouTube 頻道：**{display_name}**"),
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    embed=EmbedFactory.error("移除失敗", f"本伺服器並未訂閱頻道 `{channel_id}`"),
                    ephemeral=True
                )

        elif action == "list":
            await interaction.response.defer(ephemeral=True)
            subs = await self.db.get_youtube_subs(guild_id)
            if not subs:
                return await interaction.followup.send(
                    embed=EmbedFactory.info("訂閱列表為空", "目前此伺服器尚未訂閱任何 YouTube 頻道！\n可以使用 `/youtube action:新增訂閱` 來加入訂閱。"),
                    ephemeral=True
                )
                
            desc_lines = []
            for idx, sub in enumerate(subs, 1):
                chan_mention = f"<#{sub['notification_channel_id']}>"
                desc_lines.append(
                    f"{idx}. **[{sub['channel_name']}](https://www.youtube.com/channel/{sub['channel_id']})**\n"
                    f"   └ 頻道 ID: `{sub['channel_id']}`\n"
                    f"   └ 通知頻道: {chan_mention}"
                )
                
            embed = discord.Embed(
                title=f"📺 {interaction.guild.name} 的 YouTube 訂閱清單",
                description="\n".join(desc_lines),
                color=0xFF0000,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text=f"總共 {len(subs)} 個訂閱項目", icon_url=self.bot.user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)

        elif action == "check":
            await interaction.response.defer(ephemeral=True)
            await self._check_and_notify()
            await interaction.followup.send(
                embed=EmbedFactory.success("檢測完畢", "已手動觸發一次 YouTube 頻道更新檢測！"),
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(YouTubeNotifier(bot))
