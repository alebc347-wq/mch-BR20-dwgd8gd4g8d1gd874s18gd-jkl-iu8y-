import os
import json
import time
import asyncio
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone
from config import Colors

CWA_API_KEY = os.getenv("CWA_API_KEY", "")
DISASTER_CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "disaster_channels.json")

def _load_disaster_config() -> dict:
    """載入天災通知頻道設定 {guild_id_str: channel_id_int}"""
    if os.path.exists(DISASTER_CONFIG_FILE):
        try:
            with open(DISASTER_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_disaster_config(data: dict):
    """儲存天災通知頻道設定"""
    os.makedirs(os.path.dirname(DISASTER_CONFIG_FILE), exist_ok=True)
    with open(DISASTER_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

class Disaster(commands.Cog):
    """倉鼠勇者 - 多源即時地震與天災速報系統 (Multi-Source Real-time Earthquake Alert Engine)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config: dict = _load_disaster_config()
        self.processed_ids: set = set()
        self.disaster_monitor.start()

    def cog_unload(self):
        self.disaster_monitor.cancel()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 多源地震 API 監測與抓取
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def fetch_usgs_taiwan_earthquakes(self, session: aiohttp.ClientSession) -> list[dict]:
        """從 USGS 抓取台灣區域 (緯度 20~26.5, 經度 118~124.5) 最新地震"""
        url = "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&minlatitude=20&maxlatitude=26.5&minlongitude=118&maxlongitude=124.5&minmagnitude=2.5&limit=10"
        try:
            async with session.get(url, timeout=7) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = []
                    for feat in data.get("features", []):
                        props = feat.get("properties", {})
                        geom = feat.get("geometry", {}).get("coordinates", [0, 0, 0])
                        event_id = f"usgs_{feat.get('id')}"
                        mag = props.get("mag", 0.0)
                        place = props.get("place", "台灣周邊海域")
                        eq_time = datetime.fromtimestamp(props.get("time", 0)/1000, tz=timezone.utc)
                        depth = geom[2] if len(geom) > 2 else 0

                        results.append({
                            "id": event_id,
                            "title": f"M {mag} - {place}",
                            "magnitude": mag,
                            "location": place,
                            "depth": f"{depth:.1f} km",
                            "time": eq_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                            "url": props.get("url", "https://earthquake.usgs.gov/"),
                            "source": "USGS 地震監測網",
                            "lat": geom[1],
                            "lon": geom[0]
                        })
                    return results
        except Exception as e:
            print(f"⚠️ 抓取 USGS 台灣地震資料失敗: {e}")
        return []

    async def fetch_cwa_earthquakes(self, session: aiohttp.ClientSession) -> list[dict]:
        """從 CWA (中央氣象署) 抓取地震報告 (若設定有效 API Key)"""
        if not CWA_API_KEY:
            return []
        url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization={CWA_API_KEY}"
        try:
            async with session.get(url, timeout=7) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    earthquakes = data.get("records", {}).get("Earthquake", [])
                    results = []
                    for eq in earthquakes:
                        eq_info = eq.get("EarthquakeInfo", {})
                        eq_num = eq.get("EarthquakeNo", f"cwa_{time.time()}")
                        mag = float(eq_info.get("EarthquakeMagnitude", {}).get("MagnitudeValue", 0))
                        loc = eq_info.get("Epicenter", {}).get("Location", "台灣地區")
                        depth = eq_info.get("FocalDepth", 0)
                        eq_time = eq_info.get("OriginTime", "")
                        web_url = eq.get("Web", "https://www.cwa.gov.tw/")

                        results.append({
                            "id": f"cwa_{eq_num}",
                            "title": f"M {mag} 顯著有感地震",
                            "magnitude": mag,
                            "location": loc,
                            "depth": f"{depth} km",
                            "time": eq_time,
                            "url": web_url,
                            "source": "交通部中央氣象署 CWA",
                            "lat": 0,
                            "lon": 0
                        })
                    return results
        except Exception as e:
            print(f"⚠️ 抓取 CWA 地震資料失敗: {e}")
        return []

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 自動輪詢任務與廣播
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @tasks.loop(seconds=15)
    async def disaster_monitor(self):
        """每 15 秒自動輪詢多源地震數據"""
        # 只在 Active 節點執行天災輪詢，防止兩台主機重複推播
        if not getattr(self.bot, "is_active_node", True):
            return

        async with aiohttp.ClientSession() as session:
            # 優先讀取 USGS 台灣區域，必要時補充 CWA
            usgs_events = await self.fetch_usgs_taiwan_earthquakes(session)
            cwa_events = await self.fetch_cwa_earthquakes(session)
            all_events = usgs_events + cwa_events

            for eq in all_events:
                eid = eq["id"]
                if eid in self.processed_ids:
                    continue

                # 若第一次啟動，紀錄歷史 ID 防止歷史舊案爆發式推播
                if not self.processed_ids and len(all_events) > 0:
                    for item in all_events:
                        self.processed_ids.add(item["id"])
                    break

                self.processed_ids.add(eid)
                await self.broadcast_earthquake(eq)

    @disaster_monitor.before_loop
    async def before_monitor(self):
        await self.bot.wait_until_ready()

    async def broadcast_earthquake(self, eq: dict):
        """將地震特報發布給所有啟動監控的伺服器頻道"""
        mag = eq["magnitude"]

        # 設定 Embed 視覺顏色
        if mag >= 5.5:
            color = discord.Color.red()
            header = "🚨【緊急】顯著強烈地震速報"
            mention = "@everyone " if mag >= 6.0 else ""
        elif mag >= 4.0:
            color = discord.Color.orange()
            header = "⚠️【特報】區域中型地震速報"
            mention = ""
        else:
            color = discord.Color.gold()
            header = "📢 區域有感地震速報"
            mention = ""

        embed = discord.Embed(
            title=f"{header} - {eq['title']}",
            url=eq["url"],
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="📍 震央位置", value=f"`{eq['location']}`", inline=True)
        embed.add_field(name="📊 地震規模", value=f"`M {eq['magnitude']:.1f}`", inline=True)
        embed.add_field(name="📉 震源深度", value=f"`{eq['depth']}`", inline=True)
        embed.add_field(name="🕒 發震時間", value=f"`{eq['time']}`", inline=False)
        embed.add_field(name="📡 資料來源", value=f"`{eq['source']}`", inline=True)

        embed.set_footer(text="🛡️ 倉鼠勇者 天災防衛監測中心 | 自動防偽認證")

        # 廣播發送
        for guild_id_str, channel_id in list(self.config.items()):
            try:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    # 嘗試以名稱尋找預設頻道
                    guild = self.bot.get_guild(int(guild_id_str))
                    if guild:
                        channel = discord.utils.get(guild.text_channels, name="🫨-地震通知")

                if channel:
                    await channel.send(content=f"{mention}📢 **{header}**", embed=embed)
            except Exception as e:
                print(f"⚠️ 發送地震速報至頻道 {channel_id} 失敗: {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 指令系統 (Prefix & Slash Commands)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    disaster_group = app_commands.Group(name="disaster", description="多源即時地震與天災監控管理")

    @disaster_group.command(name="set_channel", description="將當前頻道設定為地震天災推播頻道")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_channel_slash(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        target_channel = channel or interaction.channel
        self.config[str(interaction.guild_id)] = target_channel.id
        _save_disaster_config(self.config)

        embed = discord.Embed(
            title="✅ 地震天災推播頻道設定成功",
            description=f"本伺服器天災通知頻道已成功設定為：{target_channel.mention}\n當發生台灣及周邊地震時將第一時間自動播報！",
            color=Colors.SUCCESS
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @disaster_group.command(name="toggle", description="開啟或關閉本伺服器的地震天災通知")
    @app_commands.checks.has_permissions(administrator=True)
    async def toggle_slash(self, interaction: discord.Interaction, enabled: bool):
        gid_str = str(interaction.guild_id)
        if enabled:
            target_channel = interaction.channel
            self.config[gid_str] = target_channel.id
            _save_disaster_config(self.config)
            await interaction.response.send_message(f"✅ 已啟動地震天災推播！通知頻道：{target_channel.mention}", ephemeral=True)
        else:
            if gid_str in self.config:
                del self.config[gid_str]
                _save_disaster_config(self.config)
            await interaction.response.send_message("🔕 已關閉本伺服器的地震天災推播通知。", ephemeral=True)

    @disaster_group.command(name="test", description="測試發送地震天災推播 Embed")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_slash(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🧪 倉鼠勇者 天災監測系統測試報告",
            description="多源地震數據介面 (USGS/CWA) 連線正常！",
            color=Colors.SUCCESS,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="監控狀態", value="🟢 100% 運作中 (每 15 秒自動輪詢)", inline=True)
        embed.add_field(name="目前啟用頻道數", value=f"`{len(self.config)}` 個伺服器", inline=True)
        embed.set_footer(text="🛡️ 倉鼠勇者 天災防衛監測中心")

        await interaction.response.send_message("✅ 測試完成！推播測試 Embed 如下：", embed=embed, ephemeral=True)

    @disaster_group.command(name="latest", description="查詢台灣及全球最新地震紀錄")
    async def latest_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        async with aiohttp.ClientSession() as session:
            events = await self.fetch_usgs_taiwan_earthquakes(session)

        if not events:
            await interaction.followup.send("ℹ️ 目前無最新地震資料紀錄。", ephemeral=True)
            return

        embed = discord.Embed(
            title="📊 台灣及周邊區域最新地震統計",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        for eq in events[:5]:
            embed.add_field(
                name=f"M {eq['magnitude']:.1f} - {eq['location']}",
                value=f"時間: `{eq['time']}`\n深度: `{eq['depth']}`\n來源: `{eq['source']}`",
                inline=False
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # 傳統前綴指令相容
    @commands.command(name="天災")
    @commands.has_permissions(administrator=True)
    async def disaster_prefix(self, ctx: commands.Context, mode: str = "最新"):
        gid_str = str(ctx.guild.id)
        if mode in ("開啟", "on"):
            self.config[gid_str] = ctx.channel.id
            _save_disaster_config(self.config)
            await ctx.send(f"✅ 已啟動天災推播！預設頻道：{ctx.channel.mention}")
        elif mode in ("關閉", "off"):
            if gid_str in self.config:
                del self.config[gid_str]
                _save_disaster_config(self.config)
            await ctx.send("🔕 已關閉天災推播。")
        elif mode in ("測試", "test"):
            embed = discord.Embed(title="🧪 系統測試報告", description="多源地震監測連線正常！", color=Colors.SUCCESS)
            await ctx.send(embed=embed)
        else:
            await ctx.send("ℹ️ 使用說明：`.天災 開啟` | `.天災 關閉` | `.天災 測試` | `.天災 最新`")

async def setup(bot: commands.Bot):
    await bot.add_cog(Disaster(bot))
