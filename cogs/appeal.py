"""
申訴系統 Cog
/申訴 — 全伺服器可用的申訴指令
/申訴設定 — 僅限伺服器 1480115281715265590 的管理指令
申訴按鈕附在禁言/封禁/踢出/警告的 DM 通知中
申訴接單頻道 → 開票人員接單 → 私人討論串 → 回覆申訴人 DM
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Select
from datetime import datetime, timezone
import asyncio

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 常數設定
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

APPEAL_GUILD_ID = 1480115281715265590          # 申訴管理伺服器 ID
APPEAL_SERVER_INVITE = "https://discord.gg/cuSxhwCvb6"
STAFF_ROLE_NAME = "開票人員"

# 申訴類型定義
APPEAL_TYPES = [
    discord.SelectOption(label="📢 投訴", value="投訴", description="投訴人員或事件"),
    discord.SelectOption(label="🔇 禁言問題", value="禁言問題", description="對禁言處分提出申訴"),
    discord.SelectOption(label="🚨 檢舉", value="檢舉", description="檢舉違規行為"),
    discord.SelectOption(label="🤖 機器人 Bug", value="機器人Bug", description="Bot 功能錯誤回報"),
    discord.SelectOption(label="📜 違反伺服器規則", value="違反伺服器規則", description="違反規則但 Bot 沒有禁言"),
    discord.SelectOption(label="⛔ Bot 黑名單申訴", value="Bot黑名單", description="被機器人黑名單申訴"),
    discord.SelectOption(label="❓ 其他問題", value="其他問題", description="其他未分類問題"),
]

# 記憶體儲存：appeal_id → appeal_data
_active_appeals: dict[str, dict] = {}


def _generate_appeal_id() -> str:
    import random, string
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 申訴表單 Modal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AppealFormModal(Modal, title="📢 提出申訴"):
    content = TextInput(
        label="詳細說明",
        style=discord.TextStyle.paragraph,
        placeholder="請詳細描述你的申訴內容、事發經過或遇到的問題...",
        required=True,
        max_length=1000,
    )
    related_user = TextInput(
        label="相關人員（可選）",
        style=discord.TextStyle.short,
        placeholder="例：@Username 或 用戶 ID（若無請留空）",
        required=False,
        max_length=100,
    )

    def __init__(self, appeal_type: str, source_guild_id: int = None, source_guild_name: str = None, bot: commands.Bot = None):
        super().__init__()
        self.appeal_type = appeal_type
        self.source_guild_id = source_guild_id
        self.source_guild_name = source_guild_name
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        appeal_id = _generate_appeal_id()
        now = datetime.now(timezone.utc)

        # 取得申訴人在來源伺服器的身分組
        roles_str = "（無法取得）"
        guild_name_display = self.source_guild_name or "（未知伺服器）"
        guild_id_display = str(self.source_guild_id) if self.source_guild_id else "未知"

        if interaction.guild:
            # 在伺服器內申訴
            guild_name_display = interaction.guild.name
            guild_id_display = str(interaction.guild.id)
            member_roles = [r.name for r in interaction.user.roles if r.name != "@everyone"]
            roles_str = "、".join(member_roles) if member_roles else "（無特殊身分組）"
        elif self.source_guild_id and self.bot:
            # 在 DM 中申訴（從按鈕帶入 guild_id）
            src_guild = self.bot.get_guild(self.source_guild_id)
            if src_guild:
                guild_name_display = src_guild.name
                src_member = src_guild.get_member(interaction.user.id)
                if src_member:
                    member_roles = [r.name for r in src_member.roles if r.name != "@everyone"]
                    roles_str = "、".join(member_roles) if member_roles else "（無特殊身分組）"

        # 儲存申訴資料
        _active_appeals[appeal_id] = {
            "id": appeal_id,
            "user_id": interaction.user.id,
            "user_name": str(interaction.user),
            "user_avatar": interaction.user.display_avatar.url,
            "appeal_type": self.appeal_type,
            "content": self.content.value,
            "related_user": self.related_user.value or "（無）",
            "source_guild_id": guild_id_display,
            "source_guild_name": guild_name_display,
            "roles": roles_str,
            "created_at": now.isoformat(),
            "status": "待處理",
            "claimed_by": None,
            "thread_id": None,
        }

        # 1. DM 確認給申訴人
        try:
            dm_embed = discord.Embed(
                title="✅ 申訴已送出",
                description=(
                    f"你的申訴已成功提交，我們會盡快處理。\n\n"
                    f"**申訴編號：** `{appeal_id}`\n"
                    f"**申訴類型：** {self.appeal_type}\n"
                    f"**送出時間：** <t:{int(now.timestamp())}:F>\n\n"
                    f"如需進一步溝通，請加入我們的申訴伺服器：\n{APPEAL_SERVER_INVITE}"
                ),
                color=0x57F287,
            )
            dm_embed.set_footer(text="倉鼠勇者 | 申訴系統")
            await interaction.user.send(embed=dm_embed)
        except discord.Forbidden:
            pass  # 用戶關閉 DM，忽略

        # 2. 發送到申訴伺服器接單頻道
        sent = await _send_to_appeal_channel(interaction.client, appeal_id, _active_appeals[appeal_id])

        if sent:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="✅ 申訴已成功送出！",
                    description=(
                        f"**申訴編號：** `{appeal_id}`\n"
                        f"已傳送至申訴處理中心，我們會盡快審核並透過私訊回覆你。\n\n"
                        f"如需進一步協助，也可以加入：{APPEAL_SERVER_INVITE}"
                    ),
                    color=0x57F287,
                ),
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="⚠️ 申訴已記錄，但接單頻道尚未設定",
                    description=(
                        f"**申訴編號：** `{appeal_id}`\n"
                        "申訴資料已記錄，請加入我們的申訴伺服器以獲得協助：\n"
                        f"{APPEAL_SERVER_INVITE}"
                    ),
                    color=0xFEE75C,
                ),
                ephemeral=True,
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 申訴類型選單 View
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AppealTypeSelect(discord.ui.Select):
    def __init__(self, source_guild_id: int = None, source_guild_name: str = None):
        self.source_guild_id = source_guild_id
        self.source_guild_name = source_guild_name
        super().__init__(
            placeholder="請選擇你的申訴類型",
            options=APPEAL_TYPES,
            custom_id="appeal_type_select",
        )

    async def callback(self, interaction: discord.Interaction):
        appeal_type = self.values[0]
        modal = AppealFormModal(
            appeal_type=appeal_type,
            source_guild_id=self.source_guild_id,
            source_guild_name=self.source_guild_name,
            bot=interaction.client,
        )
        await interaction.response.send_modal(modal)


class AppealSelectView(View):
    def __init__(self, source_guild_id: int = None, source_guild_name: str = None):
        super().__init__(timeout=120)
        self.add_item(AppealTypeSelect(source_guild_id=source_guild_id, source_guild_name=source_guild_name))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 申訴按鈕（附在懲處 DM 中）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AppealButton(discord.ui.View):
    """附在禁言/封禁/踢出/警告 DM 中的申訴按鈕"""

    def __init__(self, source_guild_id: int, source_guild_name: str):
        super().__init__(timeout=None)
        self.source_guild_id = source_guild_id
        self.source_guild_name = source_guild_name
        # 申訴按鈕
        appeal_btn = discord.ui.Button(
            label="📢 提出申訴",
            style=discord.ButtonStyle.danger,
            custom_id=f"appeal_start_{source_guild_id}",
        )
        appeal_btn.callback = self.appeal_callback
        self.add_item(appeal_btn)
        # 申訴伺服器連結
        self.add_item(discord.ui.Button(
            label="前往申訴伺服器",
            style=discord.ButtonStyle.link,
            url=APPEAL_SERVER_INVITE,
            emoji="🔗",
        ))

    async def appeal_callback(self, interaction: discord.Interaction):
        view = AppealSelectView(
            source_guild_id=self.source_guild_id,
            source_guild_name=self.source_guild_name,
        )
        embed = discord.Embed(
            title="📢 申訴系統",
            description="請從下方選單選擇你的申訴類型，然後填寫詳細說明。",
            color=0x5865F2,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 申訴錯誤回報按鈕（附在系統錯誤回應中，取代原本發 DM 給擁有者）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AppealErrorView(discord.ui.View):
    """錯誤發生時顯示的申訴/回報按鈕（取代原 ErrorReportView）"""

    def __init__(self, bot: commands.Bot, error_name: str, error_msg: str, command_name: str, occurrence_time: str):
        super().__init__(timeout=180)
        self.bot = bot
        self.error_name = error_name
        self.error_msg = error_msg
        self.command_name = command_name
        self.occurrence_time = occurrence_time
        self.add_item(discord.ui.Button(label="前往申訴伺服器", style=discord.ButtonStyle.link, url=APPEAL_SERVER_INVITE, emoji="🔗"))

    @discord.ui.button(label="📢 申訴 / 回報此錯誤", style=discord.ButtonStyle.danger, emoji="⚠️", custom_id="appeal_error_btn")
    async def appeal_error(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 預填申訴類型為「機器人Bug」，直接打開 Modal
        modal = AppealFormModal(
            appeal_type="機器人Bug",
            source_guild_id=interaction.guild_id if interaction.guild else None,
            source_guild_name=interaction.guild.name if interaction.guild else None,
            bot=self.bot,
        )
        # 預設填入錯誤訊息到 content
        modal.content.default = (
            f"指令：{self.command_name}\n"
            f"錯誤類型：{self.error_name}\n"
            f"錯誤訊息：{self.error_msg}\n"
            f"發生時間：{self.occurrence_time}"
        )
        await interaction.response.send_modal(modal)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 接單後的討論串控制 View
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AppealReplyModal(Modal, title="💬 回覆申訴人"):
    reply_content = TextInput(
        label="回覆內容",
        style=discord.TextStyle.paragraph,
        placeholder="輸入要傳送給申訴人的訊息...",
        required=True,
        max_length=1000,
    )

    def __init__(self, appeal_id: str, bot: commands.Bot):
        super().__init__()
        self.appeal_id = appeal_id
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        data = _active_appeals.get(self.appeal_id)
        if not data:
            return await interaction.response.send_message("❌ 找不到此申訴紀錄。", ephemeral=True)

        try:
            user = await self.bot.fetch_user(data["user_id"])
            reply_embed = discord.Embed(
                title="📬 收到申訴回覆",
                description=(
                    f"**申訴編號：** `{self.appeal_id}`\n"
                    f"**申訴類型：** {data['appeal_type']}\n\n"
                    f"**工作人員回覆：**\n{self.reply_content.value}\n\n"
                    f"若想進一步溝通，請加入我們的申訴伺服器：\n{APPEAL_SERVER_INVITE}"
                ),
                color=0x5865F2,
            )
            reply_embed.set_footer(text="倉鼠勇者 | 申訴系統")
            await user.send(embed=reply_embed)

            await interaction.response.send_message(
                f"✅ 已成功傳送回覆給 {user.mention}（{user}）", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ 無法傳送私訊給申訴人，對方可能已關閉私訊。", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ 回覆失敗：{e}", ephemeral=True)


class AppealThreadView(discord.ui.View):
    """在接單討論串中的控制按鈕"""

    def __init__(self, appeal_id: str, bot: commands.Bot):
        super().__init__(timeout=None)
        self.appeal_id = appeal_id
        self.bot = bot

    @discord.ui.button(label="💬 回覆申訴人", style=discord.ButtonStyle.primary, custom_id="appeal_reply_btn")
    async def reply_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AppealReplyModal(appeal_id=self.appeal_id, bot=self.bot)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="✅ 標記已處理（關閉討論串）", style=discord.ButtonStyle.success, custom_id="appeal_resolve_btn")
    async def resolve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = _active_appeals.get(self.appeal_id)

        # 通知申訴人已處理
        if data:
            try:
                user = await self.bot.fetch_user(data["user_id"])
                notify_embed = discord.Embed(
                    title="✅ 申訴已處理",
                    description=(
                        f"**申訴編號：** `{self.appeal_id}`\n"
                        f"你的申訴已被標記為已處理。\n\n"
                        f"如有其他問題，歡迎再次申訴或加入申訴伺服器：\n{APPEAL_SERVER_INVITE}"
                    ),
                    color=0x57F287,
                )
                notify_embed.set_footer(text="倉鼠勇者 | 申訴系統")
                await user.send(embed=notify_embed)
            except Exception:
                pass

            _active_appeals.pop(self.appeal_id, None)

        # 封存討論串
        thread = interaction.channel
        if isinstance(thread, discord.Thread):
            try:
                await thread.edit(archived=True, locked=True, reason=f"申訴 {self.appeal_id} 已處理")
            except Exception:
                pass

        await interaction.response.send_message(f"✅ 申訴 `{self.appeal_id}` 已標記為處理完畢，討論串已關閉。", ephemeral=True)

    @discord.ui.button(label="🔗 邀請申訴人加入伺服器", style=discord.ButtonStyle.secondary, custom_id="appeal_invite_btn")
    async def invite_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = _active_appeals.get(self.appeal_id)
        if not data:
            return await interaction.response.send_message("❌ 找不到申訴紀錄。", ephemeral=True)

        try:
            user = await self.bot.fetch_user(data["user_id"])
            invite_embed = discord.Embed(
                title="📩 申訴伺服器邀請",
                description=(
                    f"**申訴編號：** `{self.appeal_id}`\n\n"
                    f"工作人員邀請你加入申訴伺服器以進行進一步溝通：\n"
                    f"{APPEAL_SERVER_INVITE}"
                ),
                color=0x5865F2,
            )
            invite_embed.set_footer(text="倉鼠勇者 | 申訴系統")
            await user.send(embed=invite_embed)
            await interaction.response.send_message(f"✅ 已傳送邀請給 {user.mention}", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 無法傳送私訊給申訴人。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 傳送失敗：{e}", ephemeral=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 接單頻道的工單 View
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AppealClaimView(discord.ui.View):
    """接單頻道中的「接單」按鈕"""

    def __init__(self, appeal_id: str, bot: commands.Bot):
        super().__init__(timeout=None)
        self.appeal_id = appeal_id
        self.bot = bot

    @discord.ui.button(label="✋ 接受此申訴", style=discord.ButtonStyle.primary, custom_id="appeal_claim_btn")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 檢查是否有「開票人員」身分組
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE_NAME)
        is_staff = (
            staff_role and staff_role in interaction.user.roles
        ) or interaction.user.guild_permissions.administrator

        if not is_staff:
            return await interaction.response.send_message(
                f"❌ 只有擁有「{STAFF_ROLE_NAME}」身分組的成員才能接受申訴。", ephemeral=True
            )

        data = _active_appeals.get(self.appeal_id)
        if not data:
            return await interaction.response.send_message("❌ 此申訴已不存在或已被處理。", ephemeral=True)

        if data.get("claimed_by"):
            return await interaction.response.send_message(
                f"❌ 此申訴已由 <@{data['claimed_by']}> 接單，請勿重複接單。", ephemeral=True
            )

        data["claimed_by"] = interaction.user.id
        data["status"] = "處理中"

        # 鎖定接單按鈕
        button.disabled = True
        button.label = f"✅ 已由 {interaction.user.display_name} 接單"
        button.style = discord.ButtonStyle.success
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        # 建立私人討論串（僅接單人員與伺服器擁有者可見）
        try:
            thread_name = f"申訴 {self.appeal_id} — {data['appeal_type']}"
            thread = await interaction.channel.create_thread(
                name=thread_name[:100],
                type=discord.ChannelType.private_thread,
                invitable=False,
                reason=f"申訴接單：{self.appeal_id}",
            )
            data["thread_id"] = thread.id

            # 將接單人員加入討論串
            await thread.add_user(interaction.user)

            # 嘗試加入伺服器擁有者
            try:
                owner = interaction.guild.owner
                if owner:
                    await thread.add_user(owner)
            except Exception:
                pass

            # 在討論串內發送詳細申訴資訊
            detail_embed = discord.Embed(
                title=f"📋 申訴詳情 — `{self.appeal_id}`",
                color=0xED4245,
            )
            detail_embed.add_field(name="🏷️ 申訴類型", value=data["appeal_type"], inline=True)
            detail_embed.add_field(name="📅 送出時間", value=f"<t:{int(datetime.fromisoformat(data['created_at']).timestamp())}:F>", inline=True)
            detail_embed.add_field(name="👤 申訴人", value=f"<@{data['user_id']}>\n`{data['user_name']}`\nID: `{data['user_id']}`", inline=False)
            detail_embed.add_field(name="🏠 來源伺服器", value=f"{data['source_guild_name']}\nID: `{data['source_guild_id']}`", inline=False)
            detail_embed.add_field(name="🎭 申訴人身分組", value=data["roles"] or "（無）", inline=False)
            detail_embed.add_field(name="📝 申訴內容", value=f"```{data['content'][:1000]}```", inline=False)
            if data.get("related_user") and data["related_user"] != "（無）":
                detail_embed.add_field(name="🔗 相關人員", value=data["related_user"], inline=False)
            detail_embed.set_footer(text=f"接單人員：{interaction.user.display_name}")
            detail_embed.set_thumbnail(url=data.get("user_avatar", ""))

            thread_view = AppealThreadView(appeal_id=self.appeal_id, bot=self.bot)
            await thread.send(
                content=f"{interaction.user.mention}，以下是申訴詳情：",
                embed=detail_embed,
                view=thread_view,
            )

            await interaction.response.send_message(
                f"✅ 已接單！請前往討論串 {thread.mention} 進行後續處理。",
                ephemeral=True,
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ 無法建立私人討論串，請確認 Bot 有「建立私人討論串」的權限。", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ 建立討論串時發生錯誤：{e}", ephemeral=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 永久申訴面板按鈕（放在特定頻道）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AppealPanelView(discord.ui.View):
    """永久性申訴面板按鈕"""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📢 提出申訴",
        style=discord.ButtonStyle.danger,
        custom_id="appeal_panel_btn",
        emoji="📢",
    )
    async def open_appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild_id if interaction.guild else None
        guild_name = interaction.guild.name if interaction.guild else None
        view = AppealSelectView(source_guild_id=guild_id, source_guild_name=guild_name)
        embed = discord.Embed(
            title="📢 申訴系統",
            description="請從下方選單選擇你的申訴類型，填寫詳細說明後，系統會自動通知工作人員。",
            color=0x5865F2,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 發送到申訴接單頻道（工具函數）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _send_to_appeal_channel(bot: commands.Bot, appeal_id: str, data: dict) -> bool:
    """把申訴工單發送到申訴管理伺服器的接單頻道"""
    try:
        appeal_guild = bot.get_guild(APPEAL_GUILD_ID)
        if not appeal_guild:
            return False

        # 從資料庫取得設定的接單頻道
        settings = await bot.db.get_appeal_settings(APPEAL_GUILD_ID)
        if not settings or not settings.get("receive_channel_id"):
            return False

        channel = appeal_guild.get_channel(settings["receive_channel_id"])
        if not channel:
            return False

        # 建立申訴工單 Embed
        ticket_embed = discord.Embed(
            title=f"📬 新申訴工單 #{appeal_id}",
            color=0xED4245,
            timestamp=datetime.fromisoformat(data["created_at"]),
        )
        ticket_embed.add_field(name="🏷️ 申訴類型", value=data["appeal_type"], inline=True)
        ticket_embed.add_field(name="📊 狀態", value="⏳ 待處理", inline=True)
        ticket_embed.add_field(
            name="👤 申訴人",
            value=f"<@{data['user_id']}>\n`{data['user_name']}`\nID: `{data['user_id']}`",
            inline=False,
        )
        ticket_embed.add_field(
            name="🏠 來源伺服器",
            value=f"**{data['source_guild_name']}**\nID: `{data['source_guild_id']}`",
            inline=False,
        )
        ticket_embed.add_field(name="🎭 申訴人身分組", value=data["roles"] or "（無）", inline=False)
        ticket_embed.add_field(name="📝 申訴摘要", value=f"```{data['content'][:500]}```", inline=False)
        ticket_embed.set_thumbnail(url=data.get("user_avatar", ""))
        ticket_embed.set_footer(text=f"申訴編號：{appeal_id}")

        claim_view = AppealClaimView(appeal_id=appeal_id, bot=bot)
        await channel.send(embed=ticket_embed, view=claim_view)
        return True

    except Exception as e:
        print(f"[Appeal] 傳送申訴工單失敗: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cog 主體
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Appeal(commands.Cog):
    """申訴系統"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /申訴 指令（全伺服器可用）──
    @app_commands.command(name="申訴", description="📢 提出申訴或錯誤回報")
    async def appeal_command(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id if interaction.guild else None
        guild_name = interaction.guild.name if interaction.guild else None
        view = AppealSelectView(source_guild_id=guild_id, source_guild_name=guild_name)
        embed = discord.Embed(
            title="📢 申訴系統",
            description=(
                "請從下方選單選擇你的**申訴類型**，填寫詳細說明後，系統會自動通知工作人員審核。\n\n"
                "申訴送出後，我們會盡快透過**私訊**回覆你。"
            ),
            color=0x5865F2,
        )
        embed.set_footer(text="倉鼠勇者 | 申訴系統")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── /申訴設定（僅限特定伺服器）──
    appeal_setup_group = app_commands.Group(name="申訴設定", description="申訴系統設定（限申訴管理伺服器）")

    @appeal_setup_group.command(name="接單頻道", description="設定接收申訴工單的頻道（限申訴管理伺服器）")
    @app_commands.describe(channel="要設定的接單頻道")
    @app_commands.default_permissions(administrator=True)
    async def setup_receive_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if interaction.guild_id != APPEAL_GUILD_ID:
            return await interaction.response.send_message(
                "❌ 此指令僅限申訴管理伺服器使用。", ephemeral=True
            )
        await self.bot.db.set_appeal_setting(APPEAL_GUILD_ID, "receive_channel_id", channel.id)
        embed = discord.Embed(
            title="✅ 接單頻道已設定",
            description=f"申訴工單將發送至 {channel.mention}",
            color=0x57F287,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @appeal_setup_group.command(name="按鈕頻道", description="在指定頻道發送永久申訴面板按鈕（限申訴管理伺服器）")
    @app_commands.describe(channel="要放置申訴按鈕面板的頻道")
    @app_commands.default_permissions(administrator=True)
    async def setup_panel_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if interaction.guild_id != APPEAL_GUILD_ID:
            return await interaction.response.send_message(
                "❌ 此指令僅限申訴管理伺服器使用。", ephemeral=True
            )

        await self.bot.db.set_appeal_setting(APPEAL_GUILD_ID, "panel_channel_id", channel.id)

        # 在目標頻道發送永久申訴面板
        panel_embed = discord.Embed(
            title="📢 申訴中心",
            description=(
                "有任何問題、申訴或錯誤回報，請點擊下方按鈕開始申訴流程。\n\n"
                "**支援的申訴類型：**\n"
                "📢 投訴 ／ 🔇 禁言問題 ／ 🚨 檢舉\n"
                "🤖 機器人 Bug ／ 📜 違反伺服器規則 ／ ⛔ Bot 黑名單申訴 ／ ❓ 其他問題\n\n"
                "申訴送出後，工作人員將盡快透過**私訊**回覆你。"
            ),
            color=0x5865F2,
        )
        panel_embed.set_footer(text="倉鼠勇者 | 申訴系統 • 24hr 服務")

        panel_view = AppealPanelView()
        panel_msg = await channel.send(embed=panel_embed, view=panel_view)

        await self.bot.db.set_appeal_setting(APPEAL_GUILD_ID, "panel_message_id", panel_msg.id)

        await interaction.response.send_message(
            embed=discord.Embed(
                title="✅ 申訴面板已建立",
                description=f"已在 {channel.mention} 發送永久申訴按鈕面板。",
                color=0x57F287,
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Appeal(bot))
