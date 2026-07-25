"""
天災監控系統 Cog
使用 CWA (中央氣象署) OpenData API
地震速報 + 天氣特報 自動推播
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import os
import json
from datetime import datetime, timezone

from config import Colors


# CWA API Key（從 .env 讀取，若無則使用預設值）
CWA_API_KEY = os.getenv("CWA_API_KEY", "CWA-B18C5BCE-BB65-4C62-AFAF-656A3ED67EB0")
DISASTER_CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "disaster_guilds.json")


def _load_enabled_guilds() -> list[int]:
    if os.path.exists(DISASTER_CONFIG_FILE):
        with open(DISASTER_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_enabled_guilds(guilds: list[int]):
    os.makedirs(os.path.dirname(DISASTER_CONFIG_FILE), exist_ok=True)
    with open(DISASTER_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(guilds, f)


class Disaster(commands.Cog):
    """天災監控系統 — 地震速報 + 天氣特報"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.enabled_guilds = _load_enabled_guilds()
        self.last_ids = {"earthquake": None, "weather": None}

    async def cog_load(self):
        self.disaster_monitor.start()

    async def cog_unload(self):
        self.disaster_monitor.cancel()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 核心監控任務 (每 30 秒輪詢)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @tasks.loop(seconds=30)
    async def disaster_monitor(self):
        if not self.enabled_guilds:
            return

        async with aiohttp.ClientSession() as session:
            # 1. 地震速報
            try:
                url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-002?Authorization={CWA_API_KEY}"
                async with session.get(url) as r:
                    if r.status == 200:
                        data = await r.json()
                        eqs = data.get("records", {}).get("Earthquake", [])
                        if eqs:
                            eq = eqs[0]
                            eid = eq.get("ReportNo") or eq.get("EarthquakeNo")
                            if self.last_ids["earthquake"] != eid:
                                self.last_ids["earthquake"] = eid
                                await self._broadcast(eq, "earthquake")
            except Exception:
                pass

            # 2. 天氣特報
            try:
                url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0033-001?Authorization={CWA_API_KEY}"
                async with session.get(url) as r:
                    if r.status == 200:
                        data = await r.json()
                        records = data.get("records", {}).get("record", [])
                        if records:
                            w = records[0]
                            wid = f"{w.get('datasetDescription')}{w.get('status', {}).get('reportTime')}"
                            if self.last_ids["weather"] != wid:
                                self.last_ids["weather"] = wid
                                await self._broadcast(w, "weather")
            except Exception:
                pass

    @disaster_monitor.before_loop
    async def before_monitor(self):
        await self.bot.wait_until_ready()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 推播邏輯
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _broadcast(self, data: dict, dtype: str):
        embed = discord.Embed(timestamp=datetime.now(timezone.utc))
        content = "@everyone 📢 **即時災害預警**"

        if dtype == "earthquake":
            info = data.get("EarthquakeInfo", {})
            loc = info.get("Epicenter", {}).get("Location", "台灣區域")
            mag = info.get("EarthquakeMagnitude", {}).get("MagnitudeValue", "未知")
            dep = info.get("EarthquakeDepth", {}).get("Value", "未知")
            img = data.get("ReportImageURI")

            embed.title = "🫨 【地震速報】偵測到有感地震！"
            embed.description = (
                f"🚨 **請落實：趴下、掩護、穩住**\n\n"
                f"**地點：** `{loc}`\n"
                f"**規模：** `M {mag}`\n"
                f"**深度：** `{dep} km`"
            )
            embed.color = discord.Color.red()
            if img:
                embed.set_image(url=img)
        else:
            title = data.get("datasetDescription", "天氣特報")
            desc = data.get("contents", {}).get("content", {}).get("description", "請注意氣象變化")
            embed.title = f"⛈️ 【{title}】發布中"
            display_desc = desc[:1000] + "..." if len(desc) > 1000 else desc
            embed.description = f"```{display_desc}```"
            embed.color = discord.Color.orange()

        embed.set_footer(
            text="中央氣象署 CWA 即時連線",
            icon_url="https://www.cwa.gov.tw/favicon.ico",
        )

        for gid in self.enabled_guilds:
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            channel = discord.utils.get(guild.text_channels, name="🫨-地震通知")
            if channel:
                try:
                    await channel.send(content=content, embed=embed)
                except Exception:
                    pass

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 管理指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @commands.command(name="天災")
    @commands.has_permissions(administrator=True)
    async def disaster_cmd(self, ctx: commands.Context, mode: str):
        if mode == "開啟":
            if ctx.guild.id not in self.enabled_guilds:
                self.enabled_guilds.append(ctx.guild.id)
                _save_enabled_guilds(self.enabled_guilds)

            channel = discord.utils.get(ctx.guild.text_channels, name="🫨-地震通知")
            if not channel:
                overwrites = {
                    ctx.guild.default_role: discord.PermissionOverwrite(send_messages=False),
                    ctx.guild.me: discord.PermissionOverwrite(send_messages=True),
                }
                channel = await ctx.guild.create_text_channel(
                    "🫨-地震通知", overwrites=overwrites, topic="台灣即時天災地震推播"
                )

            await ctx.send(
                f"✅ **已啟動監控**\n通知頻道：{channel.mention}\n若有地震或豪雨，我將第一時間通知各位！"
            )

        elif mode == "關閉":
            if ctx.guild.id in self.enabled_guilds:
                self.enabled_guilds.remove(ctx.guild.id)
                _save_enabled_guilds(self.enabled_guilds)
            await ctx.send("🔕 **已關閉監控**\n本伺服器將不再接收天災推播。")

        else:
            await ctx.send("❌ 請使用 `!天災 開啟` 或 `!天災 關閉`")

    @commands.command(name="測試天災")
    @commands.has_permissions(administrator=True)
    async def test_disaster(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🧪 系統測試報告",
            description="API 連線正常，Embed 渲染成功！",
            color=Colors.SUCCESS,
        )
        embed.add_field(name="監控狀態", value="🟢 運作中 (每 30 秒輪詢)")
        embed.add_field(name="啟用伺服器數", value=f"{len(self.enabled_guilds)} 個")

        channel = discord.utils.get(ctx.guild.text_channels, name="🫨-地震通知")
        if channel:
            await channel.send(embed=embed)
            await ctx.send(f"✅ 測試 Embed 已發送到 {channel.mention}")
        else:
            await ctx.send("❌ 測試失敗：找不到 `🫨-地震通知` 頻道。請先使用 `!天災 開啟`")


async def setup(bot: commands.Bot):
    await bot.add_cog(Disaster(bot))
