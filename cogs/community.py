"""
社群互動 Cog
投票、倒數計時、提醒、工單系統
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Select, Modal, TextInput
import asyncio
import random
import json

from config import Colors
from utils.embeds import EmbedFactory


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 投票系統
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class VoteData:
    """投票資料儲存（記憶體中）"""
    _votes: dict = {}

    @classmethod
    def create(cls, vote_id: str, author_id: int, topic: str, options: list[str]):
        cls._votes[vote_id] = {
            "author": author_id,
            "topic": topic,
            "results": {opt: [] for opt in options},
        }

    @classmethod
    def get(cls, vote_id: str) -> dict | None:
        return cls._votes.get(vote_id)

    @classmethod
    def delete(cls, vote_id: str):
        cls._votes.pop(vote_id, None)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 倒數計時 Modal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CountdownModal(Modal, title="⏳ 倒數計時"):
    time_input = TextInput(label="倒數時間（秒）", placeholder="例如：10", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            seconds = int(self.time_input.value)
            if seconds <= 0 or seconds > 3600:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ 請輸入 1-3600 之間的正整數秒數！", ephemeral=True)
            return

        await interaction.response.send_message(f"⏳ 倒數開始：**{seconds}** 秒")
        message = await interaction.original_response()

        # 更新間隔（避免 API 限流）
        update_interval = max(1, seconds // 20)
        remaining = seconds
        while remaining > 0:
            await asyncio.sleep(min(update_interval, remaining))
            remaining -= min(update_interval, remaining)
            if remaining > 0:
                await message.edit(content=f"⏳ 剩餘時間：**{remaining}** 秒")

        await message.edit(content="✅ 倒數結束！🎉")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 提醒 Modal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ReminderModal(Modal, title="🔔 設定提醒"):
    time_input = TextInput(label="提醒時間（秒後）", placeholder="例如：30", required=True)
    message_input = TextInput(label="提醒訊息", placeholder="要提醒的內容", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            seconds = int(self.time_input.value)
            if seconds <= 0 or seconds > 86400:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ 請輸入 1-86400 之間的正整數秒數！", ephemeral=True)
            return

        await interaction.response.send_message(
            f"✅ 已設定提醒，將於 **{seconds}** 秒後通知您！", ephemeral=True
        )
        await asyncio.sleep(seconds)
        try:
            await interaction.user.send(f"🔔 **提醒：** {self.message_input.value}")
        except discord.Forbidden:
            # 無法私訊的話就在頻道提醒
            await interaction.followup.send(
                f"🔔 {interaction.user.mention} **提醒：** {self.message_input.value}"
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工單系統
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TICKET_CATEGORY_NAME = "Tickets"
TICKET_STAFF_ROLE = "開票人員"
_ticket_counter = 0


class TicketForm(Modal, title="📩 建立新的工單"):
    reason = TextInput(label="問題描述", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, category: str):
        super().__init__()
        self.category = category

    async def on_submit(self, interaction: discord.Interaction):
        global _ticket_counter
        guild = interaction.guild

        # 確保身分組存在
        staff_role = discord.utils.get(guild.roles, name=TICKET_STAFF_ROLE)
        if not staff_role:
            staff_role = await guild.create_role(name=TICKET_STAFF_ROLE)

        # 確保分類存在
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if not category:
            category = await guild.create_category(TICKET_CATEGORY_NAME)

        # 建立頻道
        _ticket_counter += 1
        channel_name = f"ticket-{_ticket_counter}"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            staff_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        channel = await category.create_text_channel(channel_name, overwrites=overwrites)

        # 美化開票 Embed
        embed = discord.Embed(
            title="🎟️ 新的工單已建立",
            description=(
                f"**分類：** {self.category}\n"
                f"**建立人：** {interaction.user.mention}\n\n"
                f"📄 **問題內容：**\n{self.reason.value}"
            ),
            color=0xFCD005,
        )
        
        # 關閉工單按鈕
        close_view = View(timeout=None)
        close_btn = discord.ui.Button(label="關閉工單", style=discord.ButtonStyle.danger, emoji="🔒")
        
        async def close_callback(inter: discord.Interaction):
            await inter.response.send_message("🔒 工單已關閉，此頻道將在 5 秒後刪除。")
            await asyncio.sleep(5)
            try:
                await channel.delete(reason=f"工單由 {inter.user} 關閉")
            except Exception:
                pass
        
        close_btn.callback = close_callback
        close_view.add_item(close_btn)
        
        await channel.send(embed=embed, view=close_view)
        await interaction.response.send_message(f"✅ 您的工單已建立：{channel.mention}", ephemeral=True)


class TicketSelectView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        placeholder="請選擇工單類型",
        options=[
            discord.SelectOption(label="投訴", description="我要投訴人員/事件", emoji="😡"),
            discord.SelectOption(label="法律問題", description="與法律相關的疑問", emoji="⚖️"),
            discord.SelectOption(label="檢舉", description="檢舉違規行為", emoji="🚨"),
            discord.SelectOption(label="📢 申訴 / 機器人問題", description="申訴、Bug 回報（透過申訴系統）", emoji="📢"),
        ],
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        category = select.values[0]
        if "申訴" in category:
            # 導向新的申訴系統
            try:
                from cogs.appeal import AppealSelectView
                guild_id = interaction.guild_id if interaction.guild else None
                guild_name = interaction.guild.name if interaction.guild else None
                view = AppealSelectView(source_guild_id=guild_id, source_guild_name=guild_name)
                embed = discord.Embed(
                    title="📢 申訴系統",
                    description="請從下方選單選擇你的申訴類型，填寫詳細說明後，系統會自動通知工作人員。",
                    color=0x5865F2,
                )
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            except Exception:
                await interaction.response.send_message("❌ 申訴系統暫時無法使用，請稍後再試。", ephemeral=True)
        else:
            modal = TicketForm(category)
            await interaction.response.send_modal(modal)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cog 主體
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Community(commands.Cog):
    """社群互動 — 投票、倒數計時、提醒、工單"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── 投票 ──
    @app_commands.command(name="vote", description="建立投票")
    @app_commands.describe(
        topic="投票主題",
        options="以 ; 分隔的選項，例如 A;B;C",
        duration="投票時間（分鐘）",
    )
    async def vote(self, interaction: discord.Interaction, topic: str, options: str, duration: int):
        option_list = [opt.strip() for opt in options.split(";") if opt.strip()]
        if len(option_list) < 2:
            return await interaction.response.send_message("❌ 請至少提供 2 個選項！", ephemeral=True)
        if len(option_list) > 25:
            return await interaction.response.send_message("❌ 最多只能有 25 個選項！", ephemeral=True)

        vote_id = str(random.randint(10000, 99999))
        VoteData.create(vote_id, interaction.user.id, topic, option_list)

        embed = discord.Embed(
            title=f"📊 {topic}",
            description=f"⏳ 投票將於 **{duration} 分鐘後結束**。\n📋 投票 ID: `{vote_id}`",
            color=Colors.SUCCESS,
        )
        embed.set_footer(text=f"由 {interaction.user.display_name} 發起")

        # 動態建立 Select Menu
        select = Select(
            placeholder="請選擇您的選項",
            options=[
                discord.SelectOption(label=opt, value=f"option_{i}")
                for i, opt in enumerate(option_list)
            ],
        )

        async def select_callback(select_interaction: discord.Interaction):
            vote = VoteData.get(vote_id)
            if not vote:
                return await select_interaction.response.send_message("❌ 投票已結束！", ephemeral=True)
            user_id = str(select_interaction.user.id)
            selected_label = option_list[int(select.values[0].split("_")[1])]
            # 移除舊投票
            for opt in vote["results"]:
                if user_id in vote["results"][opt]:
                    vote["results"][opt].remove(user_id)
            vote["results"][selected_label].append(user_id)
            await select_interaction.response.send_message(
                f"✅ 您已投票給 **{selected_label}**", ephemeral=True
            )

        select.callback = select_callback

        view = View(timeout=None)
        view.add_item(select)

        # 查看結果按鈕
        view_btn = discord.ui.Button(label="🔍 查看目前投票", style=discord.ButtonStyle.secondary)

        async def view_callback(btn_interaction: discord.Interaction):
            vote = VoteData.get(vote_id)
            if not vote:
                return await btn_interaction.response.send_message("❌ 投票不存在！", ephemeral=True)
            result_msg = "\n".join(
                [f"**{opt}**：{len(vote['results'][opt])} 票" for opt in vote["results"]]
            )
            await btn_interaction.response.send_message(f"📊 **投票結果：**\n{result_msg}", ephemeral=True)

        view_btn.callback = view_callback
        view.add_item(view_btn)

        # 提前結束按鈕
        end_btn = discord.ui.Button(label="❌ 提前結束", style=discord.ButtonStyle.danger)

        async def end_callback(btn_interaction: discord.Interaction):
            if btn_interaction.user.id != interaction.user.id:
                return await btn_interaction.response.send_message("❌ 只有投票建立者可結束投票！", ephemeral=True)
            vote = VoteData.get(vote_id)
            if vote:
                result_msg = "\n".join(
                    [f"**{opt}**：{len(vote['results'][opt])} 票" for opt in vote["results"]]
                )
                VoteData.delete(vote_id)
                await btn_interaction.response.send_message(
                    f"📊 **投票「{topic}」已結束！**\n\n{result_msg}"
                )
            await btn_interaction.message.edit(view=None)

        end_btn.callback = end_callback
        view.add_item(end_btn)

        await interaction.response.send_message(embed=embed, view=view)

        # 自動結束
        async def end_after_delay():
            await asyncio.sleep(duration * 60)
            vote = VoteData.get(vote_id)
            if vote:
                result_msg = "\n".join(
                    [f"**{opt}**：{len(vote['results'][opt])} 票" for opt in vote["results"]]
                )
                VoteData.delete(vote_id)
                await interaction.followup.send(
                    f"⏳ **投票「{topic}」已自動結束！**\n\n{result_msg}"
                )

        asyncio.create_task(end_after_delay())

    # ── 倒數計時 ──
    @app_commands.command(name="countdown", description="⏳ 倒數計時")
    async def countdown(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CountdownModal())

    # ── 提醒 ──
    @app_commands.command(name="reminder", description="🔔 設定提醒訊息")
    async def reminder(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ReminderModal())

    # ── 工單 ──
    @app_commands.command(name="ticket", description="📩 開啟工單面板")
    async def ticket(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎟️ 開票系統",
            description="請從下方選單中選擇您要開的工單類型：",
            color=0x00AAFF,
        )
        await interaction.response.send_message(embed=embed, view=TicketSelectView(), ephemeral=True)

    # ── 海賊團頻道建立 ──
    @app_commands.command(name="create_pirate_channel", description="建立一個專屬的海賊王頻道")
    @app_commands.describe(
        name="輸入你的海賊團名稱",
        private="是否為私人頻道",
        role="允許加入的身分組 (可選)"
    )
    async def create_pirate_channel(
        self,
        interaction: discord.Interaction,
        name: str,
        private: bool = False,
        role: discord.Role = None
    ):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("❌ 此指令只能在伺服器中使用。", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        category_name = "🏴‍☠️-海賊王-Blox Fruits"
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            category = await guild.create_category(category_name)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=not private)
        }
        if role:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True)

        channel_name = f"🏴‍☠️-{name}"
        channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)

        announce_category_name = "📢-海賊團公告"
        announce_category = discord.utils.get(guild.categories, name=announce_category_name)
        if not announce_category:
            announce_category = await guild.create_category(announce_category_name)

        announce_channel = discord.utils.get(announce_category.text_channels, name="💩-海賊團公告")
        if not announce_channel:
            announce_channel = await guild.create_text_channel("💩-海賊團公告", category=announce_category)

        view = JoinView(channel)
        await announce_channel.send(
            f"🚢 海賊團 **{name}** 已經成立！想加入的夥伴們，點擊下方按鈕即可進入！",
            view=view
        )

        await interaction.followup.send(f"✅ 頻道 {channel.mention} 已成功建立！", ephemeral=True)

    # ── 認真退出伺服器偵測 ──
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if "我要認真退出伺服器" in message.content:
            view = ConfirmExitView(message.author)
            await message.channel.send(f"{message.author.mention} 你是否要認真的退出伺服器？", view=view)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ConfirmExitView & JoinView UI 元件
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class JoinView(discord.ui.View):
    def __init__(self, channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="⚓ 加入海賊團", style=discord.ButtonStyle.primary, custom_id="pirate_join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.channel.set_permissions(interaction.user, view_channel=True, send_messages=True)
        await interaction.response.send_message(f"✅ 你已成功加入 {self.channel.mention}！", ephemeral=True)


class ConfirmExitView(discord.ui.View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=30)
        self.member = member

    @discord.ui.button(label="✅ 取消", style=discord.ButtonStyle.green, custom_id="exit_cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="好啦不逼你退出啦 😆", view=None)

    @discord.ui.button(label="❌ 認真退出伺服器", style=discord.ButtonStyle.red, custom_id="exit_confirm")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await self.member.kick(reason="使用了認真退出伺服器功能")
            await interaction.response.edit_message(content=f"{self.member.mention} 已被認真踢出伺服器 🚪", view=None)
        except discord.Forbidden:
            await interaction.response.edit_message(content="我沒有權限踢你啦 😅", view=None)


async def setup(bot: commands.Bot):
    await bot.add_cog(Community(bot))
