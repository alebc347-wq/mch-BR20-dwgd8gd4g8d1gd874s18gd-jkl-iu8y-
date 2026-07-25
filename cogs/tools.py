"""
工具系統 Cog
翻譯、天氣、QR Code、縮網址
"""

import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import urllib.parse
import io
import zipfile
import datetime
import wavelink
from config import Colors, Emoji
from utils.embeds import EmbedFactory


class YTSearchPlayButton(discord.ui.Button):
    def __init__(self, track: wavelink.Playable, index: int):
        super().__init__(
            label=f"播放 #{index}",
            style=discord.ButtonStyle.success,
            emoji="🎵",
            custom_id=f"yt_search_play_{track.identifier}_{index}"
        )
        self.track = track

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ 你必須先加入一個語音頻道！", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        
        music_cog = interaction.client.get_cog("Music")
        if not music_cog:
            return await interaction.followup.send("❌ 音樂系統目前不可用。", ephemeral=True)
            
        player = await music_cog._ensure_voice(interaction)
        if not player:
            return
            
        # 時長防禦限制
        is_247 = getattr(player, "mode_247", False)
        is_ultra = await music_cog.bot.db.is_guild_ultra(interaction.guild_id)
        is_pro = await music_cog.bot.db.is_guild_pro(interaction.guild_id)
        if is_247 or is_ultra:
            max_duration = 24 * 60 * 60 * 1000
        else:
            max_duration = 30 * 60 * 1000 if is_pro else 15 * 60 * 1000

        if self.track.length > max_duration:
            if is_247 or is_ultra:
                limit_text = "24 小時"
            else:
                limit_text = "30 分鐘 (Pro)" if is_pro else "15 分鐘"
            dur_fmt = music_cog._fmt_duration(self.track.length) if hasattr(music_cog, "_fmt_duration") else f"{self.track.length // 60000}:{(self.track.length % 60000) // 1000:02d}"
            return await interaction.followup.send(
                embed=EmbedFactory.error("時長超出限制", f"此歌曲長度為 `{dur_fmt}`，超出 {limit_text} 限制。"),
                ephemeral=True
            )
            
        self.track.extras = {"requester_id": interaction.user.id}
        await player.queue.put_wait(self.track)
        
        if not player.playing:
            next_t = player.queue.get()
            await player.play(next_t)
            
        await interaction.followup.send(f"✅ 已為您點播：**{self.track.title}**！", ephemeral=True)
        await music_cog.update_controller_message(interaction.guild)


class YTSearchView(discord.ui.View):
    def __init__(self, tracks: list[wavelink.Playable]):
        super().__init__(timeout=60)
        for i, track in enumerate(tracks[:3], 1):
            self.add_item(YTSearchPlayButton(track, i))


class Tools(commands.GroupCog, name="tool", description="實用生活工具箱"):
    """工具系統 — 實用生活工具"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.waiting_for_code = {}
        self.font_maps = _generate_font_maps()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 翻譯指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="translate", description="跨語言翻譯文字（自動偵測來源語言）")
    @app_commands.describe(text="要翻譯的文字", target="目標語言代碼（例如：zh-tw, en, ja, ko），預設 zh-tw")
    async def translate(self, interaction: discord.Interaction, text: str, target: str = "zh-tw"):
        await interaction.response.defer()
        
        target = target.strip().lower()
        # Google Translate API 免金鑰端點
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target}&dt=t&q={urllib.parse.quote(text)}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return await interaction.followup.send(
                            embed=EmbedFactory.error("翻譯失敗", f"API 回傳錯誤代碼: {response.status}")
                        )
                    data = await response.json()
            
            # 解析翻譯結果
            translated_text = "".join(part[0] for part in data[0] if part and part[0])
            detected_lang = data[2] if len(data) > 2 else "未知"
            
            embed = EmbedFactory.info(f"🌐 翻譯結果 ({detected_lang} ➜ {target})")
            embed.color = Colors.PRIMARY
            embed.add_field(name="**原文**", value=f"```{text}```", inline=False)
            embed.add_field(name="**譯文**", value=f"```{translated_text}```", inline=False)
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(
                embed=EmbedFactory.error("翻譯出錯", f"發生非預期的錯誤：`{str(e)}`")
            )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 天氣指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="weather", description="查詢指定城市的天氣狀況")
    @app_commands.describe(city="城市名稱（支援中文與英文，如：台北, Tokyo, London）")
    async def weather(self, interaction: discord.Interaction, city: str):
        await interaction.response.defer()
        
        # 使用 wttr.in JSON j1 格式
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1"
        
        try:
            async with aiohttp.ClientSession(headers={"Accept-Language": "zh-tw"}) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return await interaction.followup.send(
                            embed=EmbedFactory.error("查詢失敗", "找不到此城市的天氣資訊，請檢查拼字。")
                        )
                    data = await response.json()
            
            current = data["current_condition"][0]
            temp = current["temp_C"]
            feels = current["FeelsLikeC"]
            humidity = current["humidity"]
            wind_speed = current["windspeedKmph"]
            
            # 天氣描述與對應表情符號
            weather_desc = current.get("lang_zh-tw", current["weatherDesc"])[0]["value"]
            
            embed = discord.Embed(
                title=f"🌤️ {city} 的即時天氣狀況",
                color=Colors.GAME,
            )
            embed.add_field(name="**目前溫度**", value=f"`{temp}°C` (體感 `{feels}°C`)", inline=True)
            embed.add_field(name="**天氣狀態**", value=f"`{weather_desc}`", inline=True)
            embed.add_field(name="**空氣濕度**", value=f"`{humidity}%`", inline=True)
            embed.add_field(name="**風速**", value=f"`{wind_speed} km/h`", inline=True)
            
            # 使用 wttr.in 提供的氣象圖作為縮圖
            embed.set_thumbnail(url=f"https://wttr.in/{urllib.parse.quote(city)}_3hx.png")
            embed.set_footer(text="數據來源: wttr.in")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(
                embed=EmbedFactory.error("查詢出錯", f"發生非預期的錯誤：`{str(e)}`")
            )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # QR Code 產生指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="qr", description="將輸入的文字或網址轉換為 QR Code")
    @app_commands.describe(text="要轉換的文字或網址")
    async def qr(self, interaction: discord.Interaction, text: str):
        # 使用 qrserver.com 免費產生端點
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(text)}"
        
        embed = discord.Embed(
            title="📱 QR Code 產生器",
            description=f"已成功為以下內容產生 QR Code：\n```{text}```",
            color=Colors.PRIMARY,
        )
        embed.set_image(url=qr_url)
        embed.set_footer(text="請使用手機相機或掃描器進行掃描")
        
        await interaction.response.send_message(embed=embed)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 縮網址指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="shorten", description="將長網址縮短為 TinyURL 短網址")
    @app_commands.describe(url="要縮短的長網址 (必須以 http:// 或 https:// 開頭)")
    async def shorten(self, interaction: discord.Interaction, url: str):
        url_clean = url.strip()
        if not (url_clean.startswith("http://") or url_clean.startswith("https://")):
            return await interaction.response.send_message(
                embed=EmbedFactory.error("格式錯誤", "請提供完整的網址，並以 `http://` 或 `https://` 開頭。"),
                ephemeral=True
            )
            
        await interaction.response.defer()
        # TinyURL 免金鑰端點
        api_url = f"http://tinyurl.com/api-create.php?url={urllib.parse.quote(url_clean)}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as response:
                    if response.status != 200:
                        return await interaction.followup.send(
                            embed=EmbedFactory.error("縮短失敗", f"API 回傳錯誤: {response.status}")
                        )
                    short_url = await response.text()
                    short_url = short_url.strip()
                    
            embed = EmbedFactory.success("網址縮短成功")
            embed.color = Colors.SUCCESS
            embed.add_field(name="**原網址**", value=url_clean, inline=False)
            embed.add_field(name="**短網址**", value=f"🔗 [點我前往]({short_url}) \n`{short_url}`", inline=False)
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(
                embed=EmbedFactory.error("縮短出錯", f"發生非預期的錯誤：`{str(e)}`")
            )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 訊息搜尋指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="msg_where", description="🔍 搜尋頻道中包含關鍵字的訊息")
    @app_commands.describe(keyword="搜尋關鍵字", limit="搜尋的訊息數量上限（預設 200）")
    async def msg_where(self, interaction: discord.Interaction, keyword: str, limit: int = 200):
        await interaction.response.defer(thinking=True)
        limit = min(limit, 500)

        results = []
        async for msg in interaction.channel.history(limit=limit):
            if keyword.lower() in msg.content.lower():
                results.append(msg)

        if not results:
            return await interaction.followup.send(
                embed=EmbedFactory.error("找不到結果", f"在最近 {limit} 則訊息中找不到包含 **{keyword}** 的訊息。")
            )

        # 分頁顯示
        per_page = 5
        pages = []
        for i in range(0, len(results), per_page):
            page_msgs = results[i:i + per_page]
            embed = discord.Embed(
                title=f"🔍 搜尋結果：「{keyword}」",
                description=f"找到 **{len(results)}** 則相關訊息",
                color=Colors.PRIMARY,
            )
            for msg in page_msgs:
                content = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
                embed.add_field(
                    name=f"{msg.author.display_name} — {msg.created_at.strftime('%m/%d %H:%M')}",
                    value=f"```{content}```[🔗 跳轉](https://discord.com/channels/{msg.guild.id}/{msg.channel.id}/{msg.id})",
                    inline=False,
                )
            embed.set_footer(text=f"第 {i // per_page + 1}/{(len(results) + per_page - 1) // per_page} 頁")
            pages.append(embed)

        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0])
        else:
            from utils.embeds import PaginatorView
            view = PaginatorView(pages, interaction.user.id)
            await interaction.followup.send(embed=pages[0], view=view)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # YouTube 搜尋指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="yt", description="🎬 YouTube 影片搜尋與快速點歌")
    @app_commands.describe(query="搜尋關鍵字")
    async def yt(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        
        music_cog = self.bot.get_cog("Music")
        tracks = None
        
        # 1. 嘗試使用 Wavelink (Lavalink) 進行高品質搜尋
        if music_cog:
            try:
                tracks = await music_cog._search_with_failover(query)
            except Exception:
                pass
                
        if not tracks:
            # 2. 備用 HTML 爬蟲
            search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {"User-Agent": "Mozilla/5.0"}
                    async with session.get(search_url, headers=headers) as response:
                        html = await response.text()
                
                import re
                video_ids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", html)
                unique_ids = list(dict.fromkeys(video_ids))[:5]
                
                if not unique_ids:
                    return await interaction.followup.send(
                        embed=EmbedFactory.error("找不到結果", f"在 YouTube 上找不到 **{query}** 的搜尋結果。")
                    )
                
                embed = discord.Embed(
                    title=f"🎬 YouTube 搜尋結果：「{query}」",
                    description="透過備用爬蟲找到以下影片：",
                    color=0xFF0000,
                )
                for i, vid_id in enumerate(unique_ids, 1):
                    embed.add_field(
                        name=f"影片 {i}",
                        value=f"🔗 [點我觀看影片](https://www.youtube.com/watch?v={vid_id})",
                        inline=False
                    )
                return await interaction.followup.send(embed=embed)
            except Exception as e:
                return await interaction.followup.send(
                    embed=EmbedFactory.error("搜尋出錯", f"發生非預期的錯誤：`{str(e)}`")
                )
                
        # 3. 使用 Wavelink 的結果，建構精美 Embed
        results = tracks[:5] if not isinstance(tracks, wavelink.Playlist) else tracks.tracks[:5]
        
        embed = discord.Embed(
            title=f"🎬 YouTube 搜尋結果：「{query}」",
            description="🔍 找到以下最相關的影片，可點擊下方按鈕直接在語音頻道中播放：",
            color=0xFF0000,
        )
        
        for i, track in enumerate(results, 1):
            dur_str = music_cog._fmt_duration(track.length) if hasattr(music_cog, "_fmt_duration") else f"{track.length // 60000}:{(track.length % 60000) // 1000:02d}"
            embed.add_field(
                name=f"#{i} {track.title}",
                value=f"👤 頻道：`{track.author}` | ⏱️ 時長：`{dur_str}`\n🔗 [點我觀看影片]({track.uri})",
                inline=False
            )
            
        first_artwork = results[0].artwork if results[0].artwork else None
        if first_artwork:
            embed.set_thumbnail(url=first_artwork)
            
        view = YTSearchView(results)
        await interaction.followup.send(embed=embed, view=view)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 錯誤回報指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="bugreport", description="🐛 回報 Bug 給機器人管理員")
    @app_commands.describe(description="描述你遇到的問題")
    async def bugreport(self, interaction: discord.Interaction, description: str):
        import os
        owner_id = int(os.getenv("OWNER_ID", "0"))
        
        embed = discord.Embed(
            title="🐛 Bug 回報",
            description=description,
            color=Colors.WARNING,
        )
        embed.add_field(name="回報者", value=f"{interaction.user} (`{interaction.user.id}`)", inline=True)
        embed.add_field(name="伺服器", value=f"{interaction.guild.name} (`{interaction.guild_id}`)", inline=True)
        embed.add_field(name="頻道", value=f"{interaction.channel.mention}", inline=True)
        embed.timestamp = discord.utils.utcnow()
        
        if owner_id:
            try:
                owner = await self.bot.fetch_user(owner_id)
                await owner.send(embed=embed)
            except Exception:
                pass
        
        await interaction.response.send_message(
            embed=EmbedFactory.success("已收到回報", "感謝你的回報！管理員會盡快處理。🙏"),
            ephemeral=True,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SERVER_INFORMATION — 匯出伺服器完整資訊 (ZIP)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="server_information", description="匯出伺服器完整資訊 (頻道、身分組、使用者) 成ZIP檔")
    async def server_information(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("❌ 此指令只能在伺服器中使用。", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        guild_info = (
            f"伺服器名稱: {guild.name}\n"
            f"伺服器ID: {guild.id}\n"
            f"擁有者: {guild.owner}\n"
            f"成員數: {guild.member_count}\n"
            f"建立時間: {guild.created_at}\n"
            f"Boost等級: {guild.premium_tier}\n"
            f"Boost數量: {guild.premium_subscription_count}\n\n"
        )

        channels_info = [guild_info + "=== 📂 頻道資訊 ===\n"]
        for channel in guild.channels:
            category = channel.category.name if channel.category else "無分類"
            visible_members = len(channel.members) if hasattr(channel, "members") else 0
            channels_info.append(
                f"[分類] {category} ({channel.category_id if channel.category else '無'})\n"
                f"→ 頻道: {channel.name} ({channel.id})\n"
                f"  類型: {channel.type} | 建立: {channel.created_at}\n"
                f"  可見人數: {visible_members} | 位置: {channel.position}\n"
            )

        roles_info = ["=== 🏷️ 身分組資訊 ===\n"]
        for role in guild.roles:
            perms = [p for p, v in role.permissions if v]
            member_count = len([m for m in guild.members if role in m.roles])
            roles_info.append(
                f"{role.name} ({role.id}) | 建立: {role.created_at} | 顏色: {role.color}\n"
                f"可提及: {role.mentionable} | 位置: {role.position} | 成員數: {member_count}\n"
                f"權限 ({len(perms)}): {', '.join(perms)}\n"
            )

        users_info = ["=== 👥 使用者資訊 ===\n"]
        for member in guild.members:
            roles_names = [r.name for r in member.roles if r.name != "@everyone"]
            users_info.append(
                f"名稱: {member} ({member.id})\n"
                f"加入時間: {member.joined_at} | 最高身分組: {member.top_role.name}\n"
                f"是否機器人: {member.bot} | 狀態: {member.status}\n"
                f"身分組: {', '.join(roles_names) if roles_names else '無'}\n"
            )

        channels_txt = "\n".join(channels_info)
        roles_txt = "\n".join(roles_info)
        users_txt = "\n".join(users_info)

        zip_buffer = io.BytesIO()
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr("channels.txt", channels_txt)
            zipf.writestr("roles.txt", roles_txt)
            zipf.writestr("users.txt", users_txt)

        zip_buffer.seek(0)
        await interaction.followup.send(
            "✅ 伺服器資訊已完整匯出！",
            file=discord.File(zip_buffer, filename=f"server_information_{date_str}.zip"),
            ephemeral=True
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # GOOGLE_SEARCH — 搜尋
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="google_search", description="直接在聊天欄顯示搜尋結果")
    @app_commands.describe(query="搜尋關鍵字")
    async def google_search(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()

        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&pretty=1"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return await interaction.followup.send(f"❌ 搜尋服務目前無法使用 (HTTP {resp.status})。")
                    data = await resp.json(content_type=None)

            related = data.get("RelatedTopics", [])
            results = []
            for item in related:
                if "Text" in item and "FirstURL" in item:
                    results.append((item["Text"], item["FirstURL"]))
                elif "Topics" in item:
                    for sub in item["Topics"]:
                        if "Text" in sub and "FirstURL" in sub:
                            results.append((sub["Text"], sub["FirstURL"]))

            if not results:
                return await interaction.followup.send(f"❌ 找不到 **{query}** 的搜尋結果。")

            per_page = 3
            page_results = results[:per_page]

            embed = discord.Embed(
                title=f"🔍 {query} 的搜尋結果（第 1 頁）",
                color=Colors.PRIMARY
            )

            for idx, (title, link) in enumerate(page_results, start=1):
                embed.add_field(name=f"{idx}. {title}", value=link, inline=False)

            view = SearchView(query, results, page=0, per_page=per_page)
            await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            await interaction.followup.send(f"❌ 搜尋過程發生錯誤：{e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # GOOGLE_AI & GOOGLE_IMAGE — 外部 AI 連結
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="google_ai", description="與 AI 聊天（跳到 Phind）")
    @app_commands.describe(query="問題內容")
    async def google_ai(self, interaction: discord.Interaction, query: str):
        url = f"https://phind.com/search?q={urllib.parse.quote(query)}"
        button = discord.ui.Button(label="點此聊天", url=url, style=discord.ButtonStyle.link)
        view = discord.ui.View()
        view.add_item(button)
        await interaction.response.send_message(content=f"這是您要的 AI 聊天連結：", view=view)

    @app_commands.command(name="google_image", description="生成 AI 圖片（跳到 Lexica.art）")
    @app_commands.describe(query="圖片關鍵字")
    async def google_image(self, interaction: discord.Interaction, query: str):
        url = f"https://lexica.art/?q={urllib.parse.quote(query)}"
        button = discord.ui.Button(label="點此生成圖片", url=url, style=discord.ButtonStyle.link)
        view = discord.ui.View()
        view.add_item(button)
        await interaction.response.send_message(content=f"已為您建立圖片生成連結：", view=view)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ANALYZE_CODE — 程式語言偵測
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="analyze_code", description="分析程式碼是用什麼語言寫的")
    async def analyze_code(self, interaction: discord.Interaction):
        self.waiting_for_code[interaction.user.id] = interaction.channel.id
        await interaction.response.send_message("📝 請在此頻道貼上你的程式碼，我會幫你分析。", ephemeral=False)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        user_id = message.author.id
        if user_id in self.waiting_for_code and self.waiting_for_code[user_id] == message.channel.id:
            code_lower = message.content.lower()
            detected = "未知語言"

            language_keywords = {
                "Python 🐍": ["def ", "import ", "async def", "self", "print("],
                "JavaScript 🟨": ["function ", "console.log", "=>", "let ", "const "],
                "TypeScript 🟦": ["interface ", "implements ", "type ", "enum "],
                "Lua 🌙": ["local ", "game:getservice", "end", "then"],
                "C ⚙️": ["#include", "int main(", "printf("],
                "C++ ⚙️": ["#include", "std::", "cout <<", "cin >>", "namespace "],
                "C# 🎯": ["using system", "public class", "console.writeline"],
                "Java ☕": ["public class", "system.out.println", "static void main"],
                "Kotlin 🔷": ["fun main(", "val ", "var ", "println("],
                "Swift 🍏": ["import swift", "let ", "var ", "func "],
                "Go 🐹": ["package main", "func main()", "fmt."],
                "Rust 🦀": ["fn main()", "let mut", "cargo", "::"],
                "PHP 🐘": ["<?php", "echo ", "$_post", "$_get"],
                "HTML 🌐": ["<html>", "<body>", "<head>", "<div"],
                "CSS 🎨": ["color:", "margin:", "padding:", "font-size:"],
                "SCSS 🎨": ["$primary-color", "@mixin", "@include"],
                "SASS 🎨": ["$primary-color", "=", "@mixin"],
                "SQL 💾": ["select ", "insert into", "update ", "delete from"],
                "MySQL 💾": ["auto_increment", "engine=innodb"],
                "PostgreSQL 🐘": ["serial primary key", "returning *"],
                "SQLite 💾": ["pragma", "sqlite_master"],
                "NoSQL 📦": ["db.collection", "find(", "insert("],
                "MongoDB 🍃": ["db.", "aggregate", "bson"],
                "Redis 🚀": ["redis.call", "hset", "lpush", "get"],
                "GraphQL 📊": ["query {", "mutation {", "fragment "],
                "YAML 📜": [":", "- ", "true", "false"],
                "JSON 🔧": ['{', '}', ':', '"'],
                "XML 📰": ["<?xml", "<tag>", "<root>"],
                "Markdown 📝": ["#", "```", "* ", "- "],
                "LaTeX 📐": ["\\begin", "\\documentclass", "\\section"],
                "MATLAB 📊": ["end;", "plot(", "disp("],
                "R 📈": ["<-", "print(", "ggplot"],
                "Ruby 💎": ["def ", "puts ", "end"],
                "Perl 🐪": ["use strict", "print ", "$var"],
                "Shell Script 🐚": ["#!/bin/bash", "echo ", "fi", "done"],
                "PowerShell 💻": ["Write-Host", "Get-Item", "$PSVersionTable"],
                "Batch File 🪟": ["@echo off", "set ", "goto ", "pause"],
                "Assembly ⚙️": ["mov ", "jmp ", "int 0x80"],
                "Haskell λ": ["::", "->", "where", "do"],
                "OCaml 🦊": ["let ", "in ", "match ", "fun "],
                "Erlang 🔴": ["-module", "->", "receive", "end."],
                "Elixir 💧": ["defmodule", "def ", "end", "IO.puts"],
                "Scala 🔷": ["object ", "def ", "val ", "println("],
                "Groovy 🎵": ["println ", "def ", "class ", "import "],
                "Dart 🎯": ["void main()", "import ", "print("],
                "Flutter 🐦": ["MaterialApp(", "Scaffold(", "Widget"],
                "Objective-C 🍏": ["@interface", "@implementation", "NSLog"],
                "VB.NET 🟣": ["Sub Main", "Dim ", "Console.WriteLine"],
                "F# 📐": ["let ", "match ", "->"],
                "COBOL 🏢": ["IDENTIFICATION DIVISION", "PERFORM UNTIL"],
                "Fortran 📊": ["program ", "end program", "real :: "],
                "Ada 🔵": ["procedure ", "begin", "end;"],
                "Pascal 📘": ["program ", "begin", "end."],
                "Delphi 🟠": ["unit ", "uses ", "procedure ", "begin"],
                "Crystal 💎": ["def ", "puts ", "end", "require "],
                "Nim 🐿️": ["proc ", "echo ", "let ", "var "],
                "Julia 🔬": ["function ", "end", "println("],
                "Clojure 🌿": ["(defn ", "(println ", "(let "],
                "Lisp 🧠": ["(defun ", "(setq ", "(print "],
                "Scheme 📘": ["(define ", "(lambda ", "(display "],
                "Prolog 🤔": [":-", "consult(", "assert("],
                "Smalltalk 🎩": ["Transcript show", "Object subclass:"],
                "Hack 🧑‍💻": ["<?hh", "async function"],
                "VHDL 🔌": ["entity ", "architecture ", "signal "],
                "Verilog 🔌": ["module ", "endmodule", "wire "],
                "Racket 📘": ["#lang racket", "(define ", "(require "],
                "Elm 🌳": ["module ", "import ", "->"],
                "Pug 🐶": ["doctype html", "mixin ", "block content"],
                "Handlebars 🔧": ["{{", "}}", "{{#each"],
                "Mustache 🧔": ["{{", "}}", "{{#if"],
                "Smarty 🎯": ["{if}", "{foreach}", "{$var}"],
                "ColdFusion ❄️": ["<cfset", "<cfoutput", "<cfquery"],
                "Tcl 🐢": ["proc ", "puts ", "set "],
                "Awk 📑": ["BEGIN {", "print ", "END {"],
                "Sed 📑": ["s/", "g/", "d"],
                "Q# ⚛️": ["operation ", "qubit", "measure"],
                "Solidity ⛓️": ["pragma solidity", "contract ", "msg.sender"],
                "Move ⛓️": ["module ", "public fun", "script "],
                "Vyper 🐍": ["@external", "def ", "selfdestruct"],
                "TeX 📚": ["\\begin{document}", "\\end{document}"],
                "SML 📘": ["fun ", "val ", "datatype "],
                "ABAP 🟦": ["REPORT ", "WRITE ", "DATA "],
                "QBasic 🎮": ["PRINT ", "INPUT ", "GOTO "],
                "FoxPro 🦊": ["PROCEDURE ", "DO WHILE", "ENDFOR"],
                "ActionScript 🎬": ["package ", "public class", "trace("],
                "Haxe 🦎": ["class ", "function ", "trace("],
                "Powershell DSC ⚡": ["Configuration ", "Node ", "Resource "],
                "OpenCL ⚡": ["__kernel", "get_global_id"],
                "CUDA ⚡": ["__global__", "<<<", ">>>"],
                "Zig 🦎": ["pub fn ", "var ", "const "],
                "Pony 🐴": ["actor ", "be ", "new create"],
                "Chapel ⛪": ["proc ", "var ", "forall "],
                "Red 🔴": ["Red []", "print ", "func "],
                "Rebol 🟠": ["rebol []", "print ", "foreach "],
                "Io 🌀": ["Object clone", "method(", "writeln("],
                "Forth ⛓️": [": ", ";", "dup", "swap"],
                "APL 🔲": ["⍴", "⍳", "⌈"],
                "J 🔲": ["=: ", "+/ ", "*/"],
                "RPG 💾": ["dcl-s ", "exec sql"],
                "Eiffel 🗼": ["class ", "feature ", "do end"],
                "Mercury 🌐": [":- module", ":- pred", "det"],
            }

            for lang, keywords in language_keywords.items():
                if any(kw in code_lower for kw in keywords):
                    detected = lang
                    break

            await message.channel.send(f"📝 偵測結果：看起來這段程式碼是 **{detected}**")
            del self.waiting_for_code[user_id]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 趣味字體轉換指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="font", description="🔤 英文趣味字體轉換（提供 24 種字體樣式）")
    @app_commands.describe(text="要轉換的英文/數字文字")
    async def font(self, interaction: discord.Interaction, text: str):
        if not text.strip():
            return await interaction.response.send_message("❌ 請輸入要轉換的文字！", ephemeral=True)
            
        if len(text) > 100:
            return await interaction.response.send_message("❌ 文字長度不能超過 100 個字元！", ephemeral=True)
            
        embed = discord.Embed(
            title="🔤 英文趣味字體轉換",
            description="請在下方選單選擇您喜歡的字體樣式。點擊按鈕可將選中樣式發送至頻道！",
            color=Colors.PRIMARY
        )
        
        # 預覽幾種常見樣式
        preview_styles = ["fraktur", "double_struck", "script_bold", "bold_italic", "circled_black"]
        for style_id in preview_styles:
            if style_id in self.font_maps:
                preview_text = convert_font(text, style_id, self.font_maps)
                embed.add_field(
                    name=self.font_maps[style_id]["name"],
                    value=f"`{preview_text}`",
                    inline=False
                )
                
        view = FontConverterView(text, self.font_maps)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 廢文生產器指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="nonsense", description="✍️ 廢文產生器 — 輸入主題與字數自動產生廢文")
    @app_commands.describe(topic="廢文的主題（例如：吃晚餐、寫作業）", length="字數限制 (預設 200，介於 50 至 1000 之間)")
    async def nonsense(self, interaction: discord.Interaction, topic: str, length: int = 200):
        if not topic.strip():
            return await interaction.response.send_message("❌ 請輸入廢文主題！", ephemeral=True)
            
        if length < 50 or length > 1000:
            return await interaction.response.send_message("❌ 字數必須在 50 到 1000 之間！", ephemeral=True)
            
        await interaction.response.defer()
        
        # 呼叫廢文生成方法
        nonsense_text = generate_nonsense(topic, length)
        
        embed = discord.Embed(
            title=f"✍️ 廢文產生器：{topic}",
            description=nonsense_text,
            color=Colors.PRIMARY
        )
        embed.set_footer(text=f"估計字數：{len(nonsense_text)} 字 ｜ 主題：{topic}")
        
        await interaction.followup.send(embed=embed)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 偽造超連結產生器指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @app_commands.command(name="fake_url", description="🔗 偽造超連結產生器（顯示與實際導向不同）")
    @app_commands.describe(
        hide_url="偽造的 URL (顯示用)",
        real_url="實際的 URL (導向)"
    )
    async def fake_url(self, interaction: discord.Interaction, hide_url: str, real_url: str):
        hide_url_clean = hide_url.strip()
        real_url_clean = real_url.strip()

        # 實際導向的 URL 必須是 http:// 或 https:// 開頭，否則 Discord 無法解析為超連結
        if not (real_url_clean.startswith("http://") or real_url_clean.startswith("https://")):
            return await interaction.response.send_message(
                embed=EmbedFactory.error("格式錯誤", "實際的 URL (導向) 必須以 `http://` 或 `https://` 開頭。"),
                ephemeral=True
            )

        embed = discord.Embed(
            title="🔗 偽造超連結產生器",
            color=Colors.PRIMARY
        )
        embed.add_field(name="偽造的 URL ( 顯示用 )", value=hide_url_clean, inline=False)
        embed.add_field(name="實際的 URL ( 導向 )", value=real_url_clean, inline=False)
        embed.add_field(name="效果預覽", value=f"[{hide_url_clean}]({real_url_clean})", inline=False)
        embed.add_field(name="複製 Markdown", value=f"```\n[{hide_url_clean}](<{real_url_clean}>)\n```", inline=False)

        view = FakeURLView(hide_url_clean, real_url_clean)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FakeURLView UI 元件 (發送偽造超連結到頻道)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class FakeURLView(discord.ui.View):
    def __init__(self, hide_url: str, real_url: str):
        super().__init__(timeout=180)
        self.hide_url = hide_url
        self.real_url = real_url

    @discord.ui.button(label="發送到頻道", style=discord.ButtonStyle.success, emoji="📤", custom_id="fake_url_send")
    async def send_to_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        # interaction and button are passed by discord.py
        embed = discord.Embed(
            description=f"🔗 [{self.hide_url}]({self.real_url})",
            color=Colors.PRIMARY
        )
        avatar_url = interaction.user.display_avatar.url if interaction.user.display_avatar else None
        embed.set_author(name=f"{interaction.user.display_name} 分享了一個連結", icon_url=avatar_url)
        
        await interaction.channel.send(embed=embed)
        
        # 停用按鈕並編輯原訊息以防重複發送
        self.clear_items()
        await interaction.response.edit_message(view=self)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━





# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SearchView UI 元件 (Google Search 分頁)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SearchView(discord.ui.View):
    def __init__(self, query: str, results: list, page: int = 0, per_page: int = 3):
        super().__init__(timeout=60)
        self.query = query
        self.results = results
        self.page = page
        self.per_page = per_page

        self.add_item(discord.ui.Button(
            label="查看更多",
            url=f"https://www.google.com/search?q={urllib.parse.quote(query)}",
            style=discord.ButtonStyle.link
        ))
        self.add_item(PrevPageButton(query, results, page, per_page))
        self.add_item(NextPageButton(query, results, page, per_page))


class PrevPageButton(discord.ui.Button):
    def __init__(self, query: str, results: list, page: int, per_page: int):
        super().__init__(label="⬅️ 上一頁", style=discord.ButtonStyle.secondary)
        self.query = query
        self.results = results
        self.page = page
        self.per_page = per_page
        if page <= 0:
            self.disabled = True

    async def callback(self, interaction: discord.Interaction):
        start = (self.page - 1) * self.per_page
        end = start + self.per_page
        prev_results = self.results[start:end]

        embed = discord.Embed(
            title=f"🔍 {self.query} 的搜尋結果（第 {self.page} 頁）",
            color=Colors.PRIMARY
        )

        for idx, (title, link) in enumerate(prev_results, start=start+1):
            embed.add_field(name=f"{idx}. {title}", value=link, inline=False)

        view = SearchView(self.query, self.results, self.page - 1, self.per_page)
        await interaction.response.edit_message(embed=embed, view=view)


class NextPageButton(discord.ui.Button):
    def __init__(self, query: str, results: list, page: int, per_page: int):
        super().__init__(label="下一頁 ➡️", style=discord.ButtonStyle.primary)
        self.query = query
        self.results = results
        self.page = page
        self.per_page = per_page
        if (page + 1) * per_page >= len(results):
            self.disabled = True

    async def callback(self, interaction: discord.Interaction):
        start = (self.page + 1) * self.per_page
        end = start + self.per_page
        next_results = self.results[start:end]

        embed = discord.Embed(
            title=f"🔍 {self.query} 的搜尋結果（第 {self.page+2} 頁）",
            color=Colors.PRIMARY
        )

        for idx, (title, link) in enumerate(next_results, start=start+1):
            embed.add_field(name=f"{idx}. {title}", value=link, inline=False)

        view = SearchView(self.query, self.results, self.page + 1, self.per_page)
        await interaction.response.edit_message(embed=embed, view=view)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FontConverter UI 元件 & 轉換對照表
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class FontSelect(discord.ui.Select):
    def __init__(self, original_text: str, font_maps: dict):
        options = []
        for style_id, style_data in font_maps.items():
            preview = convert_font(original_text, style_id, font_maps)[:80]
            options.append(discord.SelectOption(
                label=style_data["name"],
                value=style_id,
                description=preview
            ))
            
        super().__init__(
            placeholder="選擇要複製/發送的字體樣式...",
            min_values=1,
            max_values=1,
            options=options
        )
        self.original_text = original_text
        self.font_maps = font_maps

    async def callback(self, interaction: discord.Interaction):
        style_id = self.values[0]
        styled_text = convert_font(self.original_text, style_id, self.font_maps)
        style_name = self.font_maps[style_id]["name"]
        
        if hasattr(self.view, "selected_style"):
            self.view.selected_style = style_id
            
        embed = discord.Embed(
            title=f"🔤 字體轉換結果 — {style_name}",
            description=f"請長按或點選以下內容進行複製：\n\n```\n{styled_text}\n```\n\n**手機直接複製欄位**：\n{styled_text}",
            color=Colors.PRIMARY
        )
        embed.set_footer(text=f"原始輸入：{self.original_text}")
        
        await interaction.response.edit_message(embed=embed, view=self.view)


class FontConverterView(discord.ui.View):
    def __init__(self, original_text: str, font_maps: dict):
        super().__init__(timeout=180)
        self.original_text = original_text
        self.font_maps = font_maps
        self.selected_style = list(font_maps.keys())[0]
        
        self.select_menu = FontSelect(original_text, font_maps)
        self.add_item(self.select_menu)
        
    @discord.ui.button(label="發送到頻道", style=discord.ButtonStyle.success, emoji="📤", custom_id="font_send_to_channel")
    async def send_to_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        styled_text = convert_font(self.original_text, self.selected_style, self.font_maps)
        await interaction.response.send_message(f"✨ {interaction.user.mention} 使用趣味字體說：\n{styled_text}")


def _generate_font_maps():
    def get_math_chars(start_up, start_lo, exceptions=None):
        if exceptions is None:
            exceptions = {}
        up = "".join(chr(exceptions.get(start_up + i, start_up + i)) for i in range(26))
        lo = "".join(chr(exceptions.get(start_lo + i, start_lo + i)) for i in range(26))
        return up, lo

    script_exceptions = {
        0x1D49D: 0x212C, 0x1D4A0: 0x2130, 0x1D4A1: 0x2131, 0x1D4A3: 0x210B,
        0x1D4A4: 0x2110, 0x1D4A7: 0x2112, 0x1D4A8: 0x2133, 0x1D4AD: 0x211B,
        0x1D4BB: 0x212F, 0x1D4BD: 0x210A, 0x1D4C5: 0x2134,
    }
    frak_exceptions = {
        0x1D506: 0x212D, 0x1D50B: 0x210C, 0x1D50C: 0x2111, 0x1D515: 0x211C, 0x1D51D: 0x2128,
    }
    double_exceptions = {
        0x1D53A: 0x2102, 0x1D53F: 0x210D, 0x1D545: 0x2115, 0x1D547: 0x2119,
        0x1D548: 0x211A, 0x1D549: 0x211D, 0x1D551: 0x2124,
    }

    bold_up, bold_lo = get_math_chars(0x1D400, 0x1D41A)
    italic_up, italic_lo = get_math_chars(0x1D434, 0x1D44E, {0x1D455: 0x210E})
    bold_italic_up, bold_italic_lo = get_math_chars(0x1D468, 0x1D482)
    script_up, script_lo = get_math_chars(0x1D49C, 0x1D4B6, script_exceptions)
    script_bold_up, script_bold_lo = get_math_chars(0x1D4D0, 0x1D4EA)
    frak_up, frak_lo = get_math_chars(0x1D504, 0x1D51E, frak_exceptions)
    frak_bold_up, frak_bold_lo = get_math_chars(0x1D56C, 0x1D586)
    double_up, double_lo = get_math_chars(0x1D538, 0x1D552, double_exceptions)
    mono_up, mono_lo = get_math_chars(0x1D670, 0x1D68A)
    
    sans_up, sans_lo = get_math_chars(0x1D5A0, 0x1D5BA)
    sans_bold_up, sans_bold_lo = get_math_chars(0x1D5D4, 0x1D5EE)
    sans_italic_up, sans_italic_lo = get_math_chars(0x1D608, 0x1D622)
    sans_bold_italic_up, sans_bold_italic_lo = get_math_chars(0x1D63C, 0x1D656)

    # Standard sets
    circled_up = "".join(chr(0x24B6 + i) for i in range(26))
    circled_lo = "".join(chr(0x24D0 + i) for i in range(26))
    circled_num = "⓪" + "".join(chr(0x2460 + i) for i in range(9))

    circled_black = "".join(chr(0x1F150 + i) for i in range(26))
    circled_black_num = "⓿" + "".join(chr(0x2776 + i) for i in range(9))

    squared = "".join(chr(0x1F130 + i) for i in range(26))
    squared_black = "".join(chr(0x1F170 + i) for i in range(26))
    parenthesized_lo = "".join(chr(0x249C + i) for i in range(26))

    double_num = "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"
    bold_num = "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"
    mono_num = "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"

    flip_map = {
        'a': 'ɐ', 'b': 'q', 'c': 'ɔ', 'd': 'p', 'e': 'ǝ', 'f': 'ɟ', 'g': 'ƃ', 'h': 'ɥ', 'i': 'ı', 'j': 'ɾ',
        'k': 'ʞ', 'l': 'l', 'm': 'ɯ', 'n': 'u', 'o': 'o', 'p': 'd', 'q': 'q', 'r': 'ɹ', 's': 's', 't': 'ʇ',
        'u': 'n', 'v': 'ʌ', 'w': 'ʍ', 'x': 'x', 'y': 'ʎ', 'z': 'z',
        'A': '∀', 'B': '𐐒', 'C': 'Ɔ', 'D': '◖', 'E': 'Ǝ', 'F': 'Ⅎ', 'G': '⅁', 'H': 'H', 'I': 'I', 'J': 'ſ',
        'K': 'ʞ', 'L': '˥', 'M': 'W', 'N': 'N', 'O': 'O', 'P': 'Ԁ', 'Q': '◌', 'R': 'ᵱ', 'S': 'S', 'T': '⊥',
        'U': '∩', 'V': 'Ʌ', 'W': 'M', 'X': 'X', 'Y': '⅄', 'Z': 'Z',
        '1': '⇂', '2': 'ᄅ', '3': 'Ɛ', '4': 'ㄣ', '5': 'ϛ', '6': '9', '7': 'ㄥ', '8': '8', '9': '6', '0': '0',
    }

    zalgo_up = ['\u030d', '\u030e', '\u0304', '\u0305', '\u030f', '\u0311', '\u0306']
    zalgo_mid = ['\u0315', '\u031b', '\u0340', '\u0341', '\u0358', '\u0321']
    zalgo_down = ['\u0316', '\u0317', '\u0318', '\u0319', '\u031c', '\u031d', '\u031e']

    return {
        "fraktur": {"up": frak_up, "lo": frak_lo, "name": "哥德體 (Fraktur)"},
        "fraktur_bold": {"up": frak_bold_up, "lo": frak_bold_lo, "name": "粗哥德體 (Fraktur Bold)"},
        "double_struck": {"up": double_up, "lo": double_lo, "num": double_num, "name": "空心體 (Double Struck)"},
        "script": {"up": script_up, "lo": script_lo, "name": "手寫體 (Script)"},
        "script_bold": {"up": script_bold_up, "lo": script_bold_lo, "name": "粗手寫體 (Script Bold)"},
        "bold": {"up": bold_up, "lo": bold_lo, "num": bold_num, "name": "粗體 (Bold)"},
        "italic": {"up": italic_up, "lo": italic_lo, "name": "斜體 (Italic)"},
        "bold_italic": {"up": bold_italic_up, "lo": bold_italic_lo, "name": "粗斜體 (Bold Italic)"},
        "monospace": {"up": mono_up, "lo": mono_lo, "num": mono_num, "name": "等寬體 (Monospace)"},
        "circled": {"up": circled_up, "lo": circled_lo, "num": circled_num, "name": "圓圈體 (Circled)"},
        "circled_black": {"up": circled_black, "lo": circled_black, "num": circled_black_num, "name": "黑圓圈體 (Circled Black)"},
        "squared": {"up": squared, "lo": squared, "name": "方框體 (Squared)"},
        "squared_black": {"up": squared_black, "lo": squared_black, "name": "黑方框體 (Squared Black)"},
        "parenthesized": {"lo": parenthesized_lo, "name": "括號體 (Parenthesized)"},
        "sans": {"up": sans_up, "lo": sans_lo, "name": "無襯線體 (Sans-Serif)"},
        "sans_bold": {"up": sans_bold_up, "lo": sans_bold_lo, "name": "無襯線粗體 (Sans Bold)"},
        "sans_italic": {"up": sans_italic_up, "lo": sans_italic_lo, "name": "無襯線斜體 (Sans Italic)"},
        "sans_bold_italic": {"up": sans_bold_italic_up, "lo": sans_bold_italic_lo, "name": "無襯線粗斜體 (Sans Bold Italic)"},
        "upside_down": {"flip": flip_map, "name": "翻轉體 (Upside Down)"},
        "strikeout": {"name": "刪除線體 (Strikeout)", "comb": "\u0336"},
        "underline": {"name": "底線體 (Underline)", "comb": "\u0332"},
        "double_underline": {"name": "雙底線體 (Double Underline)", "comb": "\u0333"},
        "wavy_underline": {"name": "波浪底線體 (Wavy Underline)", "comb": "\u0330"},
        "zalgo": {"name": "惡魔體 (Zalgo)", "up_list": zalgo_up, "mid_list": zalgo_mid, "down_list": zalgo_down}
    }


def convert_font(text: str, style_id: str, font_maps: dict) -> str:
    import random
    if style_id not in font_maps:
        return text
        
    style = font_maps[style_id]
    
    if style_id == "upside_down":
        flip_map = style["flip"]
        res = []
        for char in text:
            res.append(flip_map.get(char, char))
        return "".join(reversed(res))
        
    if "comb" in style:
        comb = style["comb"]
        return "".join((char + comb) if char != " " else char for char in text)
        
    if style_id == "zalgo":
        res = []
        for char in text:
            if char == " ":
                res.append(char)
                continue
            res.append(char)
            for _ in range(random.randint(1, 2)):
                res.append(random.choice(style["up_list"]))
            for _ in range(random.randint(1, 2)):
                res.append(random.choice(style["mid_list"]))
            for _ in range(random.randint(1, 2)):
                res.append(random.choice(style["down_list"]))
        return "".join(res)
        
    up_map = style.get("up", "")
    lo_map = style.get("lo", "")
    num_map = style.get("num", "")
    
    res = []
    for char in text:
        if 'A' <= char <= 'Z':
            idx = ord(char) - ord('A')
            if up_map and idx < len(up_map):
                res.append(up_map[idx])
            else:
                res.append(char)
        elif 'a' <= char <= 'z':
            idx = ord(char) - ord('a')
            if lo_map and idx < len(lo_map):
                res.append(lo_map[idx])
            else:
                res.append(char)
        elif '0' <= char <= '9':
            idx = ord(char) - ord('0')
            if num_map and idx < len(num_map):
                res.append(num_map[idx])
            else:
                res.append(char)
        else:
            res.append(char)
            
    return "".join(res)


def generate_nonsense(topic: str, min_len: int) -> str:
    import random
    famous = [
        "愛迪生曾經說過，天才是百分之一的靈感加上百分之九十九的汗水。這似乎解答了我的疑惑。",
        "查爾斯·史考伯在不經意間這樣說過，一個人幾乎可以在任何他懷抱無限熱忱的事情上成功。這啟發了我。",
        "培根曾經提到過，深思熟慮的考慮往往能避免不可挽回的錯誤。這不禁令我深思。",
        "歌德在不經意間這樣說過，決定一個人的一生，以及整個命運的，只是一瞬之間。這句話看似簡單，但其中的意義不可忽視。",
        "富蘭克林曾經說過，你熱愛生命嗎？那麼別浪費時間，因為時間是組成生命的材料。帶著這句話，我們還要更加慎重的審視這個問題。",
        "拉羅什福科曾經提到過，我們唯一不會改正的缺點是軟弱。這似乎解答了我的疑惑。",
        "達·芬奇在不經意間這樣說過，勤勞一日，可得一日安眠；勤勞一生，可得幸福長眠。這不禁令我深思。",
        "康德曾經說過，既然我已經踏上這條道路，那麼，任何東西都不應妨礙我沿著這條路走下去。這啟發了我。",
        "莎士比亞在不經意間這樣說過，意志命運往往背道而馳，決心終會全部推倒。這句話把我們帶到了新的維度去思考這個問題。",
        "叔本華曾經提到過，普通人只想到如何度過時間，有才能的人設法利用時間。帶著這句話，我們還要更加慎重的審視這個問題。",
        "伏爾泰曾經提到過，不經巨大的困難，就不有偉大的事業。這似乎解答了我的疑惑。"
    ]
    
    bother = [
        "我們不得不面對一個非常尷尬的事實，那就是，",
        "就我個人來說，{topic}對我的意義，不能不說是非常重大。",
        "一般來說，我們一般認為，抓住了問題的關鍵，其他一切則會迎刃而解。",
        "而這些並不是完全重要，更加重要的新概念是，",
        "帶著這些問題，我們來審視一下{topic}。",
        "在這種困難的抉擇下，本人思來想去，寢食難安。",
        "本人也是經過了深思熟慮，在每個日日夜夜思考這個問題。",
        "{topic}，發生了會如何，不發生又會如何。",
        "我們都知道，只要有意義，那麼就必須慎重考慮。",
        "要生存就得滿足需要，這是一條鐵律。",
        "所謂{topic}，關鍵是{topic}需要如何寫。",
        "這種事實對本人來說意義重大，相信對這個世界也是有一定意義的。",
        "那麼，既然如此，既然如何，要想清楚，{topic}，到底是一種怎麼樣的存在。",
        "解決{topic}的問題，是非常非常重要的。所以，",
        "每個人都不得不面對這些問題。在面對這種問題時，",
        "在這種不可避免的衝突下，我們必須解決這個問題。",
        "這啟發了我，對我而言，這不僅僅是一個簡單的抉擇，更是我人生中的一個重要轉折點。",
        "這不僅僅是為了解決當前的困境，更是為了長遠的未來鋪路。",
        "那麼，我們該如何看待這件事情？我們應該從多角度、多層次去剖析它。",
        "我們需要明白的是，這件事情的本質並不在於它本身，而是在於它所帶來的深遠影響。"
    ]
    
    result = ""
    while len(result) < min_len:
        choice = random.randint(0, 100)
        if choice < 30:
            result += random.choice(famous)
        else:
            result += random.choice(bother).format(topic=topic)
            
    if len(result) > min_len:
        result = result[:min_len]
    return result


async def setup(bot: commands.Bot):
    await bot.add_cog(Tools(bot))

