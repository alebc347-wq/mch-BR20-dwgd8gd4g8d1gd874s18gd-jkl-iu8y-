"""
自動回覆系統 Cog
關鍵字自動回覆 + 自訂回覆管理 (支援多模式、變數、多重隨機選取與內建字典開關)
"""

import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import random
from typing import Optional

from config import Colors
from utils.embeds import EmbedFactory


CUSTOM_REPLIES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "custom_replies.json")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 內建回覆詞典（從舊版遷移，精選版本）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DEFAULT_REPLIES = {
    # ─── 問候類 ───
    "哈囉": "嗨嗨嗨～終於看到你啦！👋 你今天是不是特別帥（或美）？😆",
    "嗨": "哈囉哈囉哈囉～是不是想我了？🤭",
    "你好": "你好呀！😊 今天也要元氣滿滿喔～💪",
    "早安": "早安呀！☀️ 太陽公公已經上班了，你也不能偷懶啦～",
    "早": "早早早！今天精神看起來不錯喔！☀️",
    "午安": "午安午安！🍵 吃飽了嗎？要記得吃飯才有力氣玩遊戲喔！🎮",
    "晚安": "晚安啦～祝你今晚做個好夢 💰🌙",
    "安安": "安安呀！🙌 我剛剛還在想你什麼時候會出現欸～",
    "有事嗎": "沒事呀～只是想找你聊天嘛 🥺",
    "在嗎": "我永遠都在 🤖 除非主機炸了 😆",
    "誰": "是我啦！你最貼心的小幫手 🤖",
    "你誰": "我是你的專屬小幫手 🤖 24小時全年無休那種 🕒",
    "我回來了": "歡迎回來！🙌 我還以為你忘記我了 🥺",
    "我來了": "耶！你終於來了 🎉 我等你好久了～",
    "我走了": "掰掰，下次見 👋 但我會想你的啦～",
    "掰掰": "掰掰～路上小心喔！👋 我會一直守候在這裡的～",
    "886": "886！下次見囉！🫂",

    # ─── 情緒/反應類 ───
    "笑死": "哈哈哈哈🤣 我也快笑到缺氧啦～快幫我叫救護車 🚑",
    "笑爛": "哈哈哈🤣 肚子要笑到抽筋了啦！",
    "哈哈哈": "哈哈哈 🤣 笑到根本停不下來！",
    "真的假的": "真的啦！🙈 比你想的還真！",
    "真的": "對啊！百分之百贊同！💯",
    "好扯": "太扯了吧 😆 我扯得比衛生紙還長！",
    "傻眼": "傻眼貓咪 🐱 真的讓人無言以對...",
    "無言": "......好吧，既然大家都無言了，那我來唱首歌？🎤",
    "崩潰": "不要崩潰啦 🤣 來抱抱，我們一起假裝沒事！🤗",
    "好累": "辛苦啦！喝點水、深呼吸一下 💧 休息一下再繼續戰鬥吧！💪",
    "無聊": "我可以陪你聊天呀！😆 還可以講冷笑話給你聽 ❄️",
    "開心": "開心最重要 😄 來一起撒花 🌸🌸🌸",
    "難過": "別難過啦，我陪你 💕 我會一直在這裡陪著你～",
    "哭啊": "不哭不哭，眼淚是珍珠 🥺 給你拍拍～",
    "生氣": "不要生氣啦 🤗 生氣會長皺紋啦 🤭",
    "可惡": "可惡！太氣人了吧 😤 幫你畫圈圈詛咒他！",
    "好慘": "幫 QQ 🥺 這也太慘了吧...",
    "太神啦": "太神啦！🧎 請收下我的膝蓋！",
    "酷": "超酷的！😎 帥到沒朋友～",
    "哇": "哇！真是讓人驚嘆 😲 太不可思議了！",
    "哇塞": "哇塞！太狂了吧！🔥",
    "驚訝": "驚訝到下巴都掉到地板上了 😲",
    "討厭": "不要討厭我啦 🥺 我會努力變得更好的...",

    # ─── 互動/陪伴類 ───
    "我愛你": "我也愛你呀 💕 這不是客套話是真的唷 💖",
    "抱抱": "抱抱 🤗 緊緊抱住～不放手！",
    "好耶": "耶～～ 🎉 這一定值得開香檳 🍾",
    "讚": "👍 超讚der！你最棒！",
    "加油": "加油加油！🔥 衝鴨！你一定可以的！💪",
    "謝謝": "客氣什麼！這是我應該做的嘛～😘",
    "感恩": "感恩的心，感謝有你～🌸",
    "不客氣": "不會啦～能幫上忙是我的榮幸！🤗",
    "對不起": "沒關係啦～抱一個 🤗 事情過去就過去了！",
    "抱歉": "不用道歉啦～我們誰跟誰呀！😆",
    "沒事": "沒事就好，那要不要聽首歌或玩個遊戲？🎮",
    "求救": "怎麼了？！😱 發生什麼大事了？需要我幫忙嗎？",
    "救命": "SOS！支援來了！🚨 發生什麼事？",
    "笨蛋": "你才是笨蛋呢哼哼 😤 本機器人可是高智商！",
    "白癡": "哎呀，不要口出惡言嘛 🤭 和氣生財！",
    "單身": "沒關係，你還有我啊！🤖 機器人永遠不背叛！💖",
    "工具人": "能當大家的工具人機器人，也是一種幸福啦 🤖💖",
    "邊緣人": "你才不邊緣呢！我這不是正在跟你說話嗎？🤭",

    # ─── 生活/娛樂類 ───
    "我餓了": "快去吃東西 🍔 不然我餵你虛擬泡麵 🍜",
    "吃什麼": "問就是吃火鍋 🍲 或者來碗虛擬拉麵 🍜",
    "我想睡": "那快去睡覺 😴 做個好夢！💰",
    "睡覺": "去吧去吧，蓋好被子 😴 晚安囉～",
    "睡不著": "需要我幫你數羊嗎？🐑 一隻羊、兩隻羊...",
    "來玩": "開始玩吧！🎮 玩到天荒地老！",
    "打遊戲": "組隊啦！🎮 帶我一個，雖然我可能有點雷 🤭",
    "卡了嗎": "沒有卡呀！是不是你網路慢了 🤣",
    "乾": "冷靜冷靜 🤫 喝杯茶消消氣～",
    "幹": "冷靜冷靜 🤫 喝杯茶消消氣～",
    "有鬼": "👻 哪裡有鬼？！別嚇我，我膽子很小的...",
    "帥哥": "哪裡有帥哥？！🤩 難道是正在看著螢幕的你？",
    "美女": "美女出現了！✨ 閃閃發光～",
}


def _load_custom_replies() -> dict[str, dict]:
    """載入自訂回覆（按 guild_id 分組）"""
    if os.path.exists(CUSTOM_REPLIES_FILE):
        try:
            with open(CUSTOM_REPLIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_custom_replies(data: dict):
    os.makedirs(os.path.dirname(CUSTOM_REPLIES_FILE), exist_ok=True)
    with open(CUSTOM_REPLIES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class DeleteReplyView(discord.ui.View):
    """用於 /add_reply 成功後的一鍵刪除 View"""
    def __init__(self, cog, keyword: str, author_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.keyword = keyword
        self.author_id = author_id

    @discord.ui.button(label="🗑️ 刪除此自訂回覆", style=discord.ButtonStyle.danger)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 檢查權限：只有指令發起者或是管理員/機器人擁有者能刪除
        is_author = interaction.user.id == self.author_id
        is_owner = interaction.user.id == 1437408048934027274 # BYPASS_USER_ID
        is_admin = interaction.permissions.administrator

        if not (is_author or is_owner or is_admin):
            return await interaction.response.send_message("❌ 你沒有權限刪除此回覆！", ephemeral=True)

        guild_id = str(interaction.guild_id)
        guild_replies = self.cog.custom_replies.get(guild_id, {})
        if self.keyword in guild_replies:
            del self.cog.custom_replies[guild_id][self.keyword]
            _save_custom_replies(self.cog.custom_replies)
            
            # 停用所有按鈕並更新訊息
            for item in self.children:
                item.disabled = True
            
            embed = interaction.message.embeds[0]
            embed.title = "🗑️ 自訂自動回覆已刪除"
            embed.color = discord.Color.red()
            await interaction.response.edit_message(embed=embed, view=self)
            await interaction.followup.send(f"✅ 已成功刪除關鍵字 `{self.keyword}` 的自動回覆！", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ 關鍵字 `{self.keyword}` 的回覆已被刪除或不存在。", ephemeral=True)


class AutoReply(commands.Cog):
    """自動回覆系統 — 關鍵字觸發回覆"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.custom_replies = _load_custom_replies()

    def _get_guild_replies(self, guild_id: int) -> dict:
        """取得某伺服器的自訂回覆"""
        return self.custom_replies.get(str(guild_id), {})

    def _process_reply(self, reply_text: str, message: discord.Message) -> str:
        """解析變數與隨機選擇多重回覆"""
        # 支援多重回覆（以 | 或換行分隔）
        choices = []
        if "\n" in reply_text:
            choices = [c.strip() for c in reply_text.split("\n") if c.strip()]
        elif "|" in reply_text:
            choices = [c.strip() for c in reply_text.split("|") if c.strip()]
        else:
            choices = [reply_text]

        chosen = random.choice(choices) if choices else reply_text

        # 變數替代
        chosen = chosen.replace("{user}", message.author.mention)
        chosen = chosen.replace("{name}", message.author.display_name)
        chosen = chosen.replace("{guild}", message.guild.name)
        chosen = chosen.replace("{channel}", message.channel.mention)
        return chosen

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 監聽訊息
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 忽略機器人自己 and DM
        if message.author.bot or not message.guild:
            return

        content = message.content.strip()
        if not content:
            return

        guild_replies = self._get_guild_replies(message.guild.id)
        
        # 1. 先檢查自訂回覆（過濾掉特殊配置欄位 __config__）
        keywords = [k for k in guild_replies.keys() if k != "__config__"]

        # 優先長度較長關鍵字比對
        for keyword in sorted(keywords, key=lambda x: -len(x)):
            data = guild_replies[keyword]
            
            # 相容舊格式 (僅字串)
            if isinstance(data, str):
                reply_text = data
                mode = "exact"
            else:
                reply_text = data.get("reply", "")
                mode = data.get("mode", "exact")

            triggered = False
            if mode == "exact" and content == keyword:
                triggered = True
            elif mode == "startswith" and content.startswith(keyword):
                triggered = True
            elif mode == "contains" and keyword in content:
                triggered = True

            if triggered:
                final_reply = self._process_reply(reply_text, message)
                await message.channel.send(final_reply, allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True))
                return

        # 2. 檢查內建回覆是否啟用 (預設為啟用)
        guild_config = guild_replies.get("__config__", {})
        enable_default = guild_config.get("enable_default", True)

        if enable_default:
            # 內建回覆採用精確匹配
            if content in DEFAULT_REPLIES:
                await message.channel.send(DEFAULT_REPLIES[content], allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True))
                return

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 管理指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.command(name="add_reply", description="新增或修改自訂自動回覆（管理員）")
    @app_commands.describe(
        keyword="觸發關鍵字", 
        reply="回覆內容（可用 | 區隔隨機回覆，可用 {user}, {name} 等變數）",
        mode="觸發比對模式"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="精確相同 (exact)", value="exact"),
        app_commands.Choice(name="包含關鍵字 (contains)", value="contains"),
        app_commands.Choice(name="關鍵字開頭 (startswith)", value="startswith")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def add_reply(self, interaction: discord.Interaction, keyword: str, reply: str, mode: str = "exact"):
        if keyword == "__config__":
            return await interaction.response.send_message("❌ 無效的關鍵字名稱。", ephemeral=True)

        guild_id = str(interaction.guild_id)
        if guild_id not in self.custom_replies:
            self.custom_replies[guild_id] = {}

        self.custom_replies[guild_id][keyword] = {
            "reply": reply,
            "mode": mode
        }
        _save_custom_replies(self.custom_replies)

        embed = discord.Embed(
            title="✅ 自動回覆已建立/更新",
            color=Colors.SUCCESS,
        )
        mode_labels = {
            "contains": "包含關鍵字",
            "exact": "精確相同",
            "startswith": "關鍵字開頭"
        }
        embed.add_field(name="關鍵字", value=f"`{keyword}`", inline=True)
        embed.add_field(name="匹配模式", value=f"`{mode_labels.get(mode, mode)}`", inline=True)
        embed.add_field(name="回覆內容", value=reply[:200], inline=False)
        embed.set_footer(text="💡 提示：使用 {user} 提及觸發者；多重回覆以 | 隔開。")
        view = DeleteReplyView(self, keyword, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    async def _do_remove_reply(self, interaction: discord.Interaction, keyword: str):
        guild_id = str(interaction.guild_id)
        guild_replies = self.custom_replies.get(guild_id, {})

        if keyword not in guild_replies or keyword == "__config__":
            return await interaction.response.send_message(
                f"❌ 找不到關鍵字 `{keyword}` 的自訂回覆。", ephemeral=True
            )

        del self.custom_replies[guild_id][keyword]
        _save_custom_replies(self.custom_replies)

        await interaction.response.send_message(f"✅ 已成功移除關鍵字 `{keyword}` 的自動回覆。")

    @app_commands.command(name="remove_reply", description="移除自訂自動回覆（管理員）")
    @app_commands.describe(keyword="要移除的關鍵字")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_reply(self, interaction: discord.Interaction, keyword: str):
        await self._do_remove_reply(interaction, keyword)

    @app_commands.command(name="delete_reply", description="移除自訂自動回覆（管理員）")
    @app_commands.describe(keyword="要移除的關鍵字")
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_reply(self, interaction: discord.Interaction, keyword: str):
        await self._do_remove_reply(interaction, keyword)

    @app_commands.command(name="toggle_default_replies", description="切換是否啟用系統內建的自動回覆庫（管理員）")
    @app_commands.describe(enable="是否啟用內建回覆")
    @app_commands.checks.has_permissions(administrator=True)
    async def toggle_default_replies(self, interaction: discord.Interaction, enable: bool):
        guild_id = str(interaction.guild_id)
        if guild_id not in self.custom_replies:
            self.custom_replies[guild_id] = {}

        if "__config__" not in self.custom_replies[guild_id]:
            self.custom_replies[guild_id]["__config__"] = {}

        self.custom_replies[guild_id]["__config__"]["enable_default"] = enable
        _save_custom_replies(self.custom_replies)

        status_text = "🟢 已啟用" if enable else "🔴 已停用"
        embed = discord.Embed(
            title="🛠️ 系統內建自動回覆設定",
            description=f"此伺服器的系統預設自動回覆目前已切換為：**{status_text}**",
            color=Colors.SUCCESS
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="list_replies", description="列出所有自訂自動回覆")
    async def list_replies(self, interaction: discord.Interaction):
        guild_replies = self._get_guild_replies(interaction.guild_id)
        keywords = [k for k in guild_replies.keys() if k != "__config__"]

        guild_config = guild_replies.get("__config__", {})
        enable_default = guild_config.get("enable_default", True)
        default_status = "啟用" if enable_default else "停用"

        if not keywords:
            return await interaction.response.send_message(
                f"📋 本伺服器目前沒有自訂自動回覆。\n"
                f"系統內建回覆（共 **{len(DEFAULT_REPLIES)}** 組）狀態：**{default_status}**。\n"
                f"💡 管理員可以使用 `/add_reply` 新增自訂回覆！",
                ephemeral=True,
            )

        embed = discord.Embed(
            title="📋 自動回覆系統狀態",
            description=f"自訂回覆：**{len(keywords)}** 組\n"
                        f"內建回覆：**{len(DEFAULT_REPLIES)}** 組（目前：**{default_status}**）",
            color=Colors.PRIMARY,
        )

        mode_labels = {
            "contains": "包含",
            "exact": "精確",
            "startswith": "開頭"
        }

        # 展示前 20 組
        for keyword in sorted(keywords)[:20]:
            data = guild_replies[keyword]
            if isinstance(data, str):
                reply_text = data
                mode_str = "精確"
            else:
                reply_text = data.get("reply", "")
                mode_str = mode_labels.get(data.get("mode", "exact"), "精確")

            short_reply = reply_text[:80] + "..." if len(reply_text) > 80 else reply_text
            embed.add_field(name=f"`{keyword}` ({mode_str})", value=short_reply, inline=False)

        if len(keywords) > 20:
            embed.set_footer(text=f"僅顯示前 20 組，共 {len(keywords)} 組自訂回覆")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoReply(bot))
