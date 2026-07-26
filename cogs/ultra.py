"""
Ultra 系統 Cog
提供 YouTube 訂閱檢測自動解鎖、Ultra 激活碼管理、以及全域 YouTube 頻道設定
"""

import discord
from discord import app_commands
from discord.ext import commands
import uuid
import re
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import Optional

import json
from config import Colors, Emoji
from utils.embeds import EmbedFactory


def extract_sub_count_from_json(data: dict) -> Optional[str]:
    """從 ytInitialData JSON 中提取本頻道的訂閱數字串"""
    header = data.get("header", {})
    
    # 1. 新版 pageHeaderRenderer
    if "pageHeaderRenderer" in header:
        try:
            renderer = header["pageHeaderRenderer"]
            content = renderer.get("content", {})
            vm = content.get("pageHeaderViewModel", {})
            metadata = vm.get("metadata", {})
            rows = metadata.get("contentMetadataViewModel", {}).get("metadataRows", [])
            for row in rows:
                parts = row.get("metadataParts", [])
                for part in parts:
                    text_obj = part.get("text", {})
                    content_str = text_obj.get("content", "")
                    if "subscriber" in content_str.lower():
                        return content_str
        except Exception:
            pass

    # 2. 舊版 c4TabbedHeaderRenderer
    if "c4TabbedHeaderRenderer" in header:
        try:
            renderer = header["c4TabbedHeaderRenderer"]
            sub_count_text = renderer.get("subscriberCountText", {})
            label = sub_count_text.get("accessibility", {}).get("accessibilityData", {}).get("label")
            if label:
                return label
            simple = sub_count_text.get("simpleText")
            if simple:
                return simple
        except Exception:
            pass

    # 3. 其他可能通道渲染器 (遞迴搜尋 "subscriberCountText")
    def find_key(d, target):
        if isinstance(d, dict):
            for k, v in d.items():
                if k == target:
                    return v
                res = find_key(v, target)
                if res:
                    return res
        elif isinstance(d, list):
            for item in d:
                res = find_key(item, target)
                if res:
                    return res
        return None

    sub_text_obj = find_key(header, "subscriberCountText")
    if sub_text_obj:
        if isinstance(sub_text_obj, dict):
            label = sub_text_obj.get("accessibility", {}).get("accessibilityData", {}).get("label")
            if label:
                return label
            simple = sub_text_obj.get("simpleText")
            if simple:
                return simple
        elif isinstance(sub_text_obj, str):
            return sub_text_obj

    return None


async def get_youtube_sub_count(channel_id_or_username: str) -> Optional[int]:
    """
    獲取 YouTube 頻道訂閱數。
    優先直接請求 YouTube；若伺服器 IP 被 Google 封鎖，自動啟用 Invidious 節點 API 作為備用方案。
    """
    input_str = channel_id_or_username.strip()
    channel_id = None
    
    # 判斷是否直接是 Channel ID
    if re.match(r"^UC[a-zA-Z0-9_-]{22}$", input_str):
        channel_id = input_str

    # 1. 嘗試直接請求 YouTube 并解析 JSON 結構，避免匹配到其他相關頻道的訂閱數
    url = f"https://www.youtube.com/channel/{input_str}" if channel_id else f"https://www.youtube.com/{input_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=6) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    match = re.search(r'var ytInitialData = (\{.*?\});</script>', html)
                    if match:
                        data = json.loads(match.group(1))
                        label = extract_sub_count_from_json(data)
                        if label:
                            label = label.replace(",", "").strip().lower()
                            num_match = re.search(r"([\d.]+)\s*(billion|million|thousand|b|m|k)?", label)
                            if num_match:
                                val = float(num_match.group(1))
                                unit = num_match.group(2)
                                if unit:
                                    if unit in ("billion", "b"):
                                        val *= 1_000_000_000
                                    elif unit in ("million", "m"):
                                        val *= 1_000_000
                                    elif unit in ("thousand", "k"):
                                        val *= 1_000
                                return int(val)
    except Exception as e:
        print(f"[Scraper] Direct YouTube fetch error: {e}")

    # 2. YouTube 連線失敗或被阻擋，啟用 Invidious 備用節點 API
    print("[Scraper] Direct YouTube fetch failed or layout mismatch. Activating Invidious fallback API...")
    invidious_instances = [
        "invidious.flokinet.to",
        "invidious.projectsegfau.lt",
        "yewtu.be",
        "invidious.privacydev.net"
    ]
    
    async with aiohttp.ClientSession() as session:
        # A. 若沒有 channel_id，需要先解析名稱獲取 ID
        if not channel_id:
            for inst in invidious_instances:
                search_url = f"https://{inst}/api/v1/search?q={input_str}&type=channel"
                try:
                    async with session.get(search_url, timeout=5) as s_resp:
                        if s_resp.status == 200:
                            data = await s_resp.json(content_type=None)
                            if isinstance(data, list) and len(data) > 0:
                                channel_id = data[0].get("authorId")
                                break
                except Exception as ex:
                    print(f"[Scraper] Resolve username failed on {inst}: {ex}")

        # B. 根據 channel_id 獲取訂閱數
        if channel_id:
            for inst in invidious_instances:
                api_url = f"https://{inst}/api/v1/channels/{channel_id}"
                try:
                    async with session.get(api_url, timeout=5) as c_resp:
                        if c_resp.status == 200:
                            data = await c_resp.json(content_type=None)
                            sub_count = data.get("subCount")
                            if sub_count is not None:
                                return int(sub_count)
                except Exception as ex:
                    print(f"[Scraper] Fetch subCount failed on {inst}: {ex}")
                    
    return None


class UltraActivationModal(discord.ui.Modal, title="輸入 Ultra 激活碼"):
    key_input = discord.ui.TextInput(
        label="Ultra 激活碼 (Ultra Key)",
        placeholder="請輸入您的 Ultra 激活金鑰...",
        required=True,
        min_length=10,
        max_length=100,
    )

    def __init__(self, cog: "Ultra"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        key = self.key_input.value.strip()
        db = interaction.client.db
        
        success = await db.use_ultra_key(key, interaction.guild_id, interaction.user.id)
        if success:
            embed = discord.Embed(
                title="✨ 恭喜！Ultra 旗艦版已成功啟用！",
                description=(
                    f"🎉 您的伺服器 **{interaction.guild.name}** 已成功激活 Ultra 權限！\n"
                    f"所有的 Ultra 專屬福利（包含 24 小時超長歌曲播放、高級音效濾波器等）現已解鎖。\n\n"
                    f"👥 啟用者: {interaction.user.mention}\n"
                    f"📅 啟用時間: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} (UTC)"
                ),
                color=0xFFD700
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                embed=EmbedFactory.error("無效的金鑰", "您輸入的激活碼不存在或已被使用。"),
                ephemeral=True
            )


class UltraPromotionView(discord.ui.View):
    """當用戶沒有 Ultra 權限時顯示的推廣 UI 按鈕"""
    def __init__(self, cog: "Ultra", chan_url: str):
        super().__init__(timeout=None)
        self.cog = cog
        
        # 連結按鈕放在第一行
        self.add_item(discord.ui.Button(
            label="點我前往 YouTube 頻道",
            url=chan_url,
            emoji="📺",
            style=discord.ButtonStyle.link,
            row=0
        ))

    @discord.ui.button(label="訂閱解鎖 Ultra", emoji="💎", style=discord.ButtonStyle.primary, custom_id="ultra_promo_subscribe", row=1)
    async def subscribe_unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 彈出訂閱檢測流程
        await self.cog.start_subscribe_flow(interaction)

    @discord.ui.button(label="輸入激活碼", emoji="🔑", style=discord.ButtonStyle.success, custom_id="ultra_enter_key", row=1)
    async def enter_key(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(UltraActivationModal(self.cog))


class UltraSubscribeView(discord.ui.View):
    """互動式 YouTube 訂閱檢測 View"""
    def __init__(self, cog: "Ultra", guild_id: int, user_id: int, owner_channel: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.owner_channel = owner_channel
        self.start_subs = None

        chan_url = f"https://www.youtube.com/channel/{owner_channel}" if owner_channel.startswith("UC") else f"https://www.youtube.com/{owner_channel}"
        # 連結按鈕放在第一行，點擊直接打開網頁
        self.add_item(discord.ui.Button(
            label="點我前往 YouTube 頻道",
            url=chan_url,
            emoji="📺",
            style=discord.ButtonStyle.link,
            row=0
        ))

    @discord.ui.button(label="1. 開始驗證訂閱", emoji="⏳", style=discord.ButtonStyle.primary, custom_id="ultra_start_verify", row=1)
    async def start_verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ 只有發起此驗證的用戶可以操作！", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        # 獲取初始訂閱數
        subs = await get_youtube_sub_count(self.owner_channel)
        if subs is None:
            return await interaction.followup.send(
                "❌ 無法獲取頻道訂閱數，請確認網路連線或稍後再試。",
                ephemeral=True
            )

        self.start_subs = subs
        
        # 更新按鈕狀態
        button.disabled = True
        button.label = "已記錄初始訂閱數"
        button.style = discord.ButtonStyle.secondary
        self.confirm_verify.disabled = False
        
        chan_url = f"https://www.youtube.com/channel/{self.owner_channel}" if self.owner_channel.startswith("UC") else f"https://www.youtube.com/{self.owner_channel}"
        
        embed = discord.Embed(
            title="💎 步驟 2：請前往訂閱並確認",
            description=(
                f"1. 請點擊下方連結前往頻道訂閱我：\n"
                f"👉 **[點我前往 YouTube 頻道]({chan_url})**\n\n"
                f"2. 訂閱成功後，請點選下方的 **「2. 確認我已訂閱」** 按鈕進行驗證！\n\n"
                f"💡 **若您已經訂閱過：**\n"
                f"請先點連結 **「取消訂閱」**，重新點擊 **「1. 開始驗證訂閱」** 記錄初始值，再 **「重新訂閱」** 並點擊 **「2. 確認我已訂閱」**！\n\n"
                f"*(初始訂閱數記錄為: `{subs}`)*"
            ),
            color=0xFFD700
        )
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="2. 確認我已訂閱", emoji="✅", style=discord.ButtonStyle.success, custom_id="ultra_confirm_verify", disabled=True)
    async def confirm_verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ 只有發起此驗證的用戶可以操作！", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        # 再次獲取訂閱數
        end_subs = await get_youtube_sub_count(self.owner_channel)
        if end_subs is None:
            return await interaction.followup.send("❌ 無法獲取目前訂閱數，請稍候重試。", ephemeral=True)

        chan_url = f"https://www.youtube.com/channel/{self.owner_channel}" if self.owner_channel.startswith("UC") else f"https://www.youtube.com/{self.owner_channel}"

        if end_subs > self.start_subs:
            # 成功！
            await self.cog.db.activate_ultra_guild_direct(self.guild_id, self.user_id, expires_in_days=30)
            
            embed = discord.Embed(
                title="✨ 恭喜！Ultra 旗艦版已成功啟用！",
                description=(
                    f"🎉 您的伺服器 **{interaction.guild.name}** 已成功升級為 Ultra 旗艦版！\n"
                    f"所有的高級功能（包含 24 小時播放、進階音訊濾波器）現已完全解鎖。\n\n"
                    f"👥 啟用者: {interaction.user.mention}\n"
                    f"📅 當前訂閱數: `{end_subs}` (訂閱前: `{self.start_subs}`)\n"
                    f"📅 啟用時長: 30 天"
                ),
                color=0xFFD700
            )
            self.stop()
            await interaction.edit_original_response(embed=embed, view=None)
        else:
            # 未增加
            embed = discord.Embed(
                title="⚠️ 驗證失敗：訂閱數未增加",
                description=(
                    f"目前的訂閱數仍為 `{end_subs}` (記錄的初始數為 `{self.start_subs}`)。\n\n"
                    f"👉 **[點我前往 YouTube 頻道]({chan_url})**\n\n"
                    f"**可能原因與解法：**\n"
                    f"1. 您可能尚未完成訂閱動作。\n"
                    f"2. **如果您此前已經訂閱過**，訂閱數不會有增長。請先點連結 **「取消訂閱」**，重新進行一次 **「1. 開始驗證」** 後再 **「重新訂閱」**。\n"
                    f"3. YouTube 的訂閱數顯示可能會有 10 ~ 60 秒的系統延遲，請稍等片刻再按一次。\n"
                    f"4. 若頻道訂閱人數大於 1,000，YouTube 會將數字四捨五入（例如顯示為 1.23K），單人訂閱將無法直接在畫面上增加 1。這時請聯繫 Bot 擁有者獲取 Ultra 啟用金鑰。\n\n"
                    f"請確認訂閱成功後再次重試。"
                ),
                color=Colors.WARNING
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


class Ultra(commands.Cog):
    """Ultra 旗艦版管理系統"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    @staticmethod
    async def check_ultra(interaction: discord.Interaction) -> bool:
        """
        檢查 interaction 所在的 Guild 是否已啟用 Ultra 功能。
        如果沒有啟用，自動發送精美的推廣與啟用 UI。
        """
        if not interaction.guild_id:
            if interaction.response.is_done():
                await interaction.followup.send("❌ 此功能只能在伺服器中使用。", ephemeral=True)
            else:
                await interaction.response.send_message("❌ 此功能只能在伺服器中使用。", ephemeral=True)
            return False

        db = interaction.client.db
        is_ultra = await db.is_guild_ultra(interaction.guild_id)
        if is_ultra:
            return True

        # 未啟用 Ultra，顯示漂亮的推廣 UI
        embed = discord.Embed(
            title="💎 這是 Ultra 旗艦版專屬功能！",
            description=(
                f"此功能為高階 Ultra 專屬。為確保更高階的會員有最舒適、順暢的機器人體驗，"
                f"您的伺服器 (**{interaction.guild.name}**) 目前尚未啟用 Ultra 旗艦版。\n\n"
                f"💡 **Ultra 旗艦版專屬福利包含：**\n"
                f"• 🟢 24/7 音樂不斷線模式 (優先串流與解碼)\n"
                f"• 📋 支援大型播放清單解析與 **無限制歌曲長度** 播放\n"
                f"• 🎛️ **進階音效濾波器** (Bassboost, Nightcore, 8D 環繞音效等)\n"
                f"• ⚡ 享受最高階 CPU 與獨立解碼線路，音質更完美\n\n"
                f"您可以點擊下方按鈕免費訂閱我以解鎖，或使用啟用碼進行啟用！"
            ),
            color=0xFFD700
        )
        embed.set_footer(text="勇者 2.0 • Ultra 旗艦版防禦機制")
        
        ultra_cog = interaction.client.cogs.get("Ultra")
        channel_id = await db.get_global_setting("owner_youtube_channel_id", "@CalebYT-t1g")
        chan_url = f"https://www.youtube.com/channel/{channel_id}" if channel_id.startswith("UC") else f"https://www.youtube.com/{channel_id}"
        view = UltraPromotionView(ultra_cog, chan_url)
        
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        return False

    async def start_subscribe_flow(self, interaction: discord.Interaction):
        """啟動訂閱檢測流程"""
        channel_id = await self.db.get_global_setting("owner_youtube_channel_id", "@CalebYT-t1g")
        chan_url = f"https://www.youtube.com/channel/{channel_id}" if channel_id.startswith("UC") else f"https://www.youtube.com/{channel_id}"
        
        embed = discord.Embed(
            title="💎 免費解鎖 Ultra 旗艦版 (30 天)",
            description=(
                f"只需訂閱擁有者的 YouTube 頻道即可免費解鎖！\n"
                f"👉 **[點我前往 YouTube 頻道]({chan_url})**\n\n"
                f"**步驟說明：**\n"
                f"1. 點選下方 **「1. 開始驗證訂閱」** 按鈕，機器人會記錄頻道當前的訂閱數。\n"
                f"2. 前往頻道完成訂閱後，點選 **「2. 確認我已訂閱」** 即可完成解鎖！\n\n"
                f"💡 **若您在此前已經訂閱過：**\n"
                f"請先點連結 **「取消訂閱」**，回到 Discord 點選 **「1. 開始驗證訂閱」**，然後**重新點選連結進行訂閱**並按 **「2. 確認我已訂閱」**，即可成功驗證！\n\n"
                f"*(注意：驗證時間限制為 120 秒)*"
            ),
            color=0xFFD700
        )
        
        view = UltraSubscribeView(self, interaction.guild_id, interaction.user.id, channel_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ─── 使用者指令 ──────────────────────────────────────────

    @app_commands.command(name="ultra", description="查看本伺服器 Ultra 狀態與解鎖 Ultra 福利")
    async def ultra_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        if not guild_id:
            return await interaction.followup.send("❌ 此指令只能在伺服器中使用。", ephemeral=True)

        is_ultra = await self.db.is_guild_ultra(guild_id)
        
        if is_ultra:
            # 獲取過期時間
            async with self.db.db.execute("SELECT expires_at FROM ultra_guilds WHERE guild_id = ?", (guild_id,)) as cursor:
                row = await cursor.fetchone()
                expires_at = row[0] if row else "未知"
            
            embed = discord.Embed(
                title="💎 本伺服器已啟用 Ultra 旗艦版！",
                description=(
                    f"🎉 感謝支持！本伺服器已享有 Ultra 旗艦版福利。\n\n"
                    f"📅 **到期時間：** `{expires_at}`\n\n"
                    f"💡 您可以自由使用包含高階濾波器 `/filter`、24小時無限制長度點歌等多項特權！"
                ),
                color=0xFFD700
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            # 未啟用，彈出推廣 UI
            channel_id = await self.db.get_global_setting("owner_youtube_channel_id", "@CalebYT-t1g")
            chan_url = f"https://www.youtube.com/channel/{channel_id}" if channel_id.startswith("UC") else f"https://www.youtube.com/{channel_id}"
            
            embed = discord.Embed(
                title="💎 解鎖 Ultra 旗艦版",
                description=(
                    f"解鎖 Ultra 功能可以讓本伺服器用戶享有更舒服的機器人與音樂體驗！\n\n"
                    f"🎁 **解鎖方式：**\n"
                    f"1. **訂閱擁有者 YouTube 頻道** (自動檢測解鎖，免費 30 天)\n"
                    f"2. **輸入 Ultra 激活金鑰**\n\n"
                    f"點選下方按鈕開始解鎖："
                ),
                color=0xFFD700
            )
            view = UltraPromotionView(self, chan_url)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # ─── 管理指令 (僅限 Bot Owner) ───────────────────────────

    @app_commands.command(name="ultra_admin", description="管理 Ultra 激活金鑰與設定 (僅限 Bot 擁有者)")
    @app_commands.choices(action=[
        app_commands.Choice(name="產生 Ultra 金鑰", value="generate"),
        app_commands.Choice(name="批量產生 Ultra 金鑰", value="batch_generate"),
        app_commands.Choice(name="列出未使用的金鑰", value="list_unused"),
        app_commands.Choice(name="列出已使用的金鑰", value="list_used"),
        app_commands.Choice(name="設定擁有者 YouTube 頻道", value="set_youtube"),
    ])
    @app_commands.describe(
        action="要執行的動作",
        days="金鑰的有效天數 (預設 30 天)",
        count="批量產生的金鑰個數 (僅批量產生時有效，預設 1)",
        key_or_value="啟用碼或設定值 (設定頻道時填寫 ID/Username/URL)"
    )
    async def ultra_admin(
        self,
        interaction: discord.Interaction,
        action: str,
        days: Optional[int] = 30,
        count: Optional[int] = 1,
        key_or_value: Optional[str] = None
    ):
        # 檢查是否為擁有者
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message(
                embed=EmbedFactory.error("無權限", "只有 Bot 擁有者可以使用此指令。"),
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        if action == "generate":
            new_key = f"HERO-ULTRA-{uuid.uuid4().hex.upper()[:16]}"
            await self.db.add_ultra_key(new_key, days)
            
            embed = discord.Embed(
                title="✨ 成功產生 Ultra 激活碼",
                description=(
                    f"🔑 **激活碼：** `{new_key}`\n"
                    f"📅 **有效天數：** {days} 天\n\n"
                    f"您可以將此金鑰發送給用戶。"
                ),
                color=Colors.SUCCESS
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        elif action == "batch_generate":
            # 批量產生 Ultra 金鑰
            count = max(1, min(count or 1, 50))
            keys = []
            for _ in range(count):
                new_key = f"HERO-ULTRA-{uuid.uuid4().hex.upper()[:16]}"
                await self.db.add_ultra_key(new_key, days)
                keys.append(new_key)
            
            keys_str = "\n".join([f"• `{k}`" for k in keys])
            embed = discord.Embed(
                title=f"✨ 成功批量產生 {count} 組 Ultra 激活碼",
                description=(
                    f"📅 **每組有效天數：** {days} 天\n\n"
                    f"🔑 **激活碼清單：**\n{keys_str}\n\n"
                    f"您現在可以將這些金鑰分發給用戶使用。"
                ),
                color=Colors.SUCCESS
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        elif action == "list_unused":
            unused = await self.db.get_ultra_keys()
            if not unused:
                return await interaction.followup.send("目前沒有未使用的 Ultra 金鑰。", ephemeral=True)
            
            text = "\n".join([f"• `{r[0]}` ({r[1]} 天) - 建立於: {r[2]}" for r in unused])
            embed = discord.Embed(
                title="📋 未使用的 Ultra 金鑰列表",
                description=text,
                color=Colors.PRIMARY
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        elif action == "list_used":
            used = await self.db.get_used_ultra_keys()
            if not used:
                return await interaction.followup.send("目前沒有已被使用的 Ultra 金鑰。", ephemeral=True)
            
            text = "\n".join([
                f"• `{r[0]}` - 伺服器: `{r[1]}` (由 {self.bot.get_user(r[2]) or r[2]} 使用) - 使用於: {r[3]}"
                for r in used
            ])
            embed = discord.Embed(
                title="📋 已使用的 Ultra 金鑰歷史",
                description=text,
                color=Colors.PRIMARY
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        elif action == "set_youtube":
            if not key_or_value:
                return await interaction.followup.send(
                    embed=EmbedFactory.error("參數缺失", "設定頻道時請填寫 `key_or_value` 參數！"),
                    ephemeral=True
                )
            
            # 解析並驗證頻道是否有效
            res = await get_youtube_sub_count(key_or_value)
            if res is None:
                return await interaction.followup.send(
                    embed=EmbedFactory.error("設定失敗", f"無法驗證頻道 `{key_or_value}`。請確認輸入的 ID/@Username/URL 是否正確。"),
                    ephemeral=True
                )
            
            await self.db.set_global_setting("owner_youtube_channel_id", key_or_value)
            embed = EmbedFactory.success(
                "設定成功",
                f"已成功將擁有者的 YouTube 頻道設定為：`{key_or_value}`\n當前訂閱數：`{res}`"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ultra(bot))
