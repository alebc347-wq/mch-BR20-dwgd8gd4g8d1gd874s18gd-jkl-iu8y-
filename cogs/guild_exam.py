"""
限定伺服器 (1472826730300309629) 專屬完整考試系統 Cog
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from config import Colors, Emoji
from utils.embeds import EmbedFactory

TARGET_GUILD_ID = 1472826730300309629
ROLE_APPLICANT = 1478335180069671044   # 一般考試通過後新增的角色組 (核心成員)
ROLE_COACH = 1489513038699827270       # 考考官通過後獲得的角色組
ROLE_YOUTUBE = 1477119651182805005     # 考考官需擁有的 YouTube 角色組
BYPASS_USER_ID = 1437408048934027274   # 團長 ID

# 預設考官名單 (在資料表為空時初始化)
DEFAULT_EXAMINERS = [
    # user_id, knife, rifle, sniper
    (1252446151475466241, 1, 0, 0),  # 小刀考官
    (1438132914712744009, 1, 0, 0),  # 小刀考官
    (1414070624795758732, 1, 0, 1),  # 小刀、狙擊考官
    (1476866853795004527, 1, 1, 1),  # 小刀、步槍、狙擊考官
    (1421430913652494518, 1, 0, 0),  # 小刀考官
    (1426607669283913738, 0, 0, 1),  # 狙擊考官
    (1444634939541815347, 0, 1, 1),  # 步槍、狙擊考官
    (1458091320764661922, 0, 1, 0),  # 步槍考官
    (1437408048934027274, 1, 1, 1),  # 團長 (全能)
]

# 預設戰隊核心成員名單
DEFAULT_CORE_MEMBERS = [
    (1492390033213358261, ""),
    (1121812848532799648, ""),
    (1444634939541815347, ""),
    (1472830305634091101, ""),
    (1371788772936646716, ""),
    (1421430913652494518, ""),
    (1491779590362759338, ""),
    (1452295135642783856, ""),
    (1438482564384817194, ""),
    (1442071283830620221, ""),
    (1391986586446594088, ""),
    (1161313819520405626, "  950連勝!!  🔥 "),
    (1446673715973722112, ""),
    (1454822286484832307, ""),
    (1401099920345399347, ""),
    (1386692651406987306, ""),
]


def is_guild_limited():
    """檢查是否為指定伺服器的裝飾器"""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild_id != TARGET_GUILD_ID:
            await interaction.response.send_message("❌ 此功能為限定伺服器的完整考試系統，其他伺服器無法使用！", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)


class ExamRegisterModal(discord.ui.Modal):
    """報名輸入資料 Modal"""

    def __init__(self, bot, category_id: int):
        super().__init__(title="輸入您的考試報名資料")
        self.bot = bot
        self.category_id = category_id

        self.level = discord.ui.TextInput(
            label="遊戲等級 (Level)",
            placeholder="請輸入您的等級，例如: 120",
            required=True,
            max_length=10
        )
        self.win_rate = discord.ui.TextInput(
            label="勝率 (Win Rate)",
            placeholder="請輸入您的勝率，例如: 58% 或 0.58",
            required=True,
            max_length=15
        )
        self.rank = discord.ui.TextInput(
            label="遊戲牌位 (Rank)",
            placeholder="請輸入您的牌位，例如: 金牌、傳奇",
            required=True,
            max_length=20
        )

        self.add_item(self.level)
        self.add_item(self.win_rate)
        self.add_item(self.rank)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db.db
        guild = interaction.guild

        # 檢查等級是否達到 200 等以上 (免試直過政策)
        import re
        level_str = self.level.value
        nums = re.findall(r'\d+', level_str)
        level_val = int(nums[0]) if nums else 0

        if level_val >= 200:
            # 200等以上改為審核制：發送審核按鈕給最高權限者 (BYPASS_USER_ID 1437408048934027274)
            audit_embed = discord.Embed(
                title="🎯 收到 200 等以上免試審核申請",
                description="有考生提交了 200 等以上的報名資料，請最高管理員點擊下方按鈕進行審核：",
                color=discord.Color.gold()
            )
            audit_embed.add_field(name="考生", value=interaction.user.mention, inline=True)
            audit_embed.add_field(name="遊戲等級", value=f"`{self.level.value}`", inline=True)
            audit_embed.add_field(name="勝率", value=f"`{self.win_rate.value}`", inline=True)
            audit_embed.add_field(name="牌位", value=f"`{self.rank.value}`", inline=True)
            audit_embed.set_footer(text=f"考生 ID: {interaction.user.id}")

            view = Exam200AuditView(self.bot, interaction.user.id)

            bypass_member = guild.get_member(BYPASS_USER_ID)
            ping_str = bypass_member.mention if bypass_member else f"<@{BYPASS_USER_ID}>"

            target_chan = interaction.channel
            async with db.execute("SELECT panel_channel_id FROM guild_exam_settings WHERE guild_id = ?", (guild.id,)) as cursor:
                r = await cursor.fetchone()
                if r and r[0]:
                    c = guild.get_channel(r[0])
                    if c:
                        target_chan = c

            try:
                await target_chan.send(content=f"🔔 {ping_str} 收到新的 200 等免試審核申請！", embed=audit_embed, view=view)
            except Exception:
                await interaction.channel.send(content=f"🔔 {ping_str} 收到新的 200 等免試審核申請！", embed=audit_embed, view=view)

            return await interaction.followup.send(
                f"📝 **報名資料已送出！**\n"
                f"檢測到您的等級已達 **{level_val} 等**，系統已將您的免試申請送交最高管理員 ({ping_str}) 進行審核。審核同意後將自動發放 <@&{ROLE_APPLICANT}> 身分組並加入戰隊成員名單！",
                ephemeral=True
            )

        # 遞增 Ticket 計數器
        await db.execute(
            "INSERT OR IGNORE INTO guild_exam_settings (guild_id) VALUES (?)",
            (guild.id,)
        )
        await db.execute(
            "UPDATE guild_exam_settings SET ticket_counter = ticket_counter + 1 WHERE guild_id = ?",
            (guild.id,)
        )
        await db.commit()

        async with db.execute(
            "SELECT ticket_counter FROM guild_exam_settings WHERE guild_id = ?",
            (guild.id,)
        ) as cursor:
            row = await cursor.fetchone()
            counter = row[0] if row else 1

        # 建立開票頻道
        category = guild.get_channel(self.category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            return await interaction.followup.send("❌ 找不到開票類別頻道，請管理員重新設定！", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }

        # 獲取所有考官，也讓他們可以看到頻道以利接單
        async with db.execute("SELECT user_id FROM guild_examiners") as cursor:
            examiners = await cursor.fetchall()
            for r in examiners:
                # 優先使用 get_member, 找不到再嘗試 fetch_member 確保能加權限
                examiner_member = guild.get_member(r[0])
                if not examiner_member:
                    try:
                        examiner_member = await guild.fetch_member(r[0])
                    except Exception:
                        pass
                if examiner_member:
                    overwrites[examiner_member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        # 確保團長也有權限
        bypass_member = guild.get_member(BYPASS_USER_ID)
        if not bypass_member:
            try:
                bypass_member = await guild.fetch_member(BYPASS_USER_ID)
            except Exception:
                pass
        if bypass_member:
            overwrites[bypass_member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        channel_name = f"ticket-{counter:03d}"
        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"考生 {interaction.user.name} 開放考試"
        )

        # 記錄至 database
        now_str = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO guild_exam_tickets (channel_id, user_id, level, win_rate, rank, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticket_channel.id, interaction.user.id, self.level.value, self.win_rate.value, self.rank.value, 'waiting_select', now_str)
        )
        await db.commit()

        # 發送歡迎訊息與下拉選單
        welcome_embed = discord.Embed(
            title="🎫 考試頻道已建立",
            description=f"歡迎 {interaction.user.mention} 來到您的專屬考試頻道！",
            color=Colors.PRIMARY
        )
        welcome_embed.add_field(name="等級", value=self.level.value, inline=True)
        welcome_embed.add_field(name="勝率", value=self.win_rate.value, inline=True)
        welcome_embed.add_field(name="牌位", value=self.rank.value, inline=True)
        welcome_embed.add_field(
            name="說明",
            value="請在下方選單中選擇您要考的項目。\n普通考試**必須選擇 2 個項目**；\n若要考考官，請**只選擇 1 個『考考官』項目**（需擁有 YouTube 身份組）。",
            inline=False
        )

        view = TicketInitView(self.bot, ticket_channel.id, interaction.user.id, interaction.user)
        await ticket_channel.send(content=interaction.user.mention, embed=welcome_embed, view=view)

        await interaction.followup.send(f"✅ 您的專屬考試頻道已經建立：{ticket_channel.mention}", ephemeral=True)


class TicketInitView(discord.ui.View):
    """Ticket 頻道內的第一步：選單"""

    def __init__(self, bot, channel_id: int, user_id: int, member: discord.Member):
        super().__init__(timeout=None)
        self.bot = bot
        self.channel_id = channel_id
        self.user_id = user_id

        # 新增多選下拉選單 (支援選 1~2 個項目)
        self.add_item(ExamTypeSelect(bot, channel_id, user_id, member))


class ExamTypeSelect(discord.ui.Select):
    """考試項目下拉選單"""

    def __init__(self, bot, channel_id: int, user_id: int, member: discord.Member):
        self.bot = bot
        self.channel_id = channel_id
        self.user_id = user_id

        is_applicant = any(r.id == ROLE_APPLICANT for r in member.roles)

        options = []
        if is_applicant:
            # 已經考過一般考試 (核心成員)，只有考考官選項
            options.append(discord.SelectOption(label="考考官", value="考考官", emoji="👑", description="申請成為考官（需有核心成員角色組）"))
            min_val = 1
            max_val = 1
        else:
            options = [
                discord.SelectOption(label="小刀", value="小刀", emoji="🔪", description="進行小刀考試項目"),
                discord.SelectOption(label="步槍", value="步槍", emoji="🔫", description="進行步槍考試項目"),
                discord.SelectOption(label="狙擊", value="狙擊", emoji="🎯", description="進行狙擊考試項目"),
                discord.SelectOption(label="考考官", value="考考官", emoji="👑", description="申請成為考官（需有核心成員角色組）"),
            ]
            min_val = 1
            max_val = 2

        super().__init__(
            placeholder="請選擇考試項目...",
            min_values=min_val,
            max_values=max_val,
            options=options,
            custom_id=f"guild_exam:select:{channel_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ 只有考生本人可以選擇項目！", ephemeral=True)

        selected = self.values

        # 防呆與規則檢查
        if "考考官" in selected:
            if len(selected) > 1:
                return await interaction.response.send_message("❌ 選擇「考考官」時不能再與其他項目混選，請只勾選「考考官」！", ephemeral=True)

            # 檢查核心成員角色組 (ROLE_APPLICANT)
            role = interaction.guild.get_role(ROLE_APPLICANT)
            if not role or role not in interaction.user.roles:
                return await interaction.response.send_message(f"❌ 只有擁有 <@&{ROLE_APPLICANT}> 角色組的核心成員才能考考官！", ephemeral=True)
        else:
            if len(selected) != 2:
                return await interaction.response.send_message("❌ 普通考試請剛好選擇 2 個項目！(例如小刀 + 步槍)", ephemeral=True)

        await interaction.response.defer()
        db = self.bot.db.db

        # 更新 Ticket 狀態與項目
        exam_types_str = json.dumps(selected, ensure_ascii=False)
        now_str = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE guild_exam_tickets SET exam_types = ?, status = 'waiting_examiner', assigned_time = ? WHERE channel_id = ?",
            (exam_types_str, now_str, self.channel_id)
        )
        await db.commit()

        # 禁用選單並編輯原訊息
        self.disabled = True
        self.placeholder = f"已選擇項目: {', '.join(selected)}"
        await interaction.message.edit(view=self.view)

        # 執行考官配對與 ping 流程
        cog = self.bot.get_cog("GuildExam")
        if cog:
            await cog.assign_examiner(interaction.channel, selected)


class ExaminerAcceptButton(discord.ui.Button):
    """自訂考官接單按鈕，支援分項目接單"""

    def __init__(self, label: str, exam_type: str, match_examiners: List[int]):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.success,
            emoji="🙋‍♂️",
            custom_id=f"guild_exam:accept_btn:{exam_type}"
        )
        self.exam_type = exam_type
        self.match_examiners = match_examiners

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        db = view.bot.db.db
        
        # 1. 檢查考生 ID，防範自己接自己的單
        async with db.execute("SELECT user_id, assigned_examiner_id FROM guild_exam_tickets WHERE channel_id = ?", (view.ticket_channel_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return await interaction.response.send_message("❌ 找不到此考試單！", ephemeral=True)
            student_id, current_examiner_id = row
            if interaction.user.id == student_id:
                return await interaction.response.send_message("❌ 惡作劇退散！您不能自己接自己的考試單！", ephemeral=True)
                
        # 2. 驗證按按鈕者是否為符合條件的考官或超級管理員
        is_allowed = interaction.user.id in self.match_examiners or interaction.user.id == BYPASS_USER_ID or interaction.user.guild_permissions.administrator
        if not is_allowed:
            return await interaction.response.send_message("❌ 您不是此考試項目的符合考官，無法接單！", ephemeral=True)
            
        await interaction.response.defer()
        
        # 3. 更新已接單考官名單 (以逗號分隔字串儲存)
        new_examiner_id = str(interaction.user.id)
        if current_examiner_id:
            curr_list = [x for x in str(current_examiner_id).split(",") if x.isdigit()]
            if new_examiner_id not in curr_list:
                curr_list.append(new_examiner_id)
            examiner_save_val = ",".join(curr_list)
        else:
            examiner_save_val = new_examiner_id
            
        await db.execute(
            "UPDATE guild_exam_tickets SET assigned_examiner_id = ?, status = 'testing' WHERE channel_id = ?",
            (examiner_save_val, view.ticket_channel_id)
        )
        await db.commit()
        
        # 4. 更新按鈕狀態
        if self.exam_type == "all":
            # 禁用所有按鈕
            view.clear_items()
            await interaction.message.edit(content=f"✅ **已由 {interaction.user.mention} 接單主持全部考試**", view=view)
        else:
            # 禁用被點擊的按鈕
            self.disabled = True
            self.label = f"已接: {self.exam_type} ({interaction.user.display_name})"
            self.style = discord.ButtonStyle.secondary
            
            # 檢查是否所有特定項目按鈕都已被接單了
            all_specific_disabled = True
            for item in view.children:
                if isinstance(item, ExaminerAcceptButton) and item.exam_type != "all" and not item.disabled:
                    all_specific_disabled = False
                    break
                    
            if all_specific_disabled:
                view.clear_items()
                await interaction.message.edit(content=f"✅ **所有考試項目皆已由考官接單主持！**", view=view)
            else:
                await interaction.message.edit(view=view)
                
        # 5. 發送考試規則
        has_action_view = False
        async for msg in interaction.channel.history(limit=20):
            if msg.author.id == view.bot.user.id and msg.embeds:
                if msg.embeds[0].title == "📜 考試規則說明":
                    has_action_view = True
                    break
                    
        if not has_action_view:
            rules_embed = discord.Embed(title="📜 考試規則說明", color=Colors.PRIMARY)
            rules_embed.add_field(
                name="💡 正常考試規則",
                value=(
                    "🔹 **突擊步槍**：至少要打到 4 分\n"
                    "🔹 **小刀**：5 分\n"
                    "🔹 **狙擊**：5 分\n"
                    "🔹 **任意武器**：5 分\n"
                    "🔹 **考官指定武器**：4 分\n"
                    "🔹 **隨機武器**：4 分\n"
                    "📌 *全都要打，並與每個考官打 (需自行安排時間)*"
                ),
                inline=False
            )
            rules_embed.set_footer(text="請考官與考生開始進行考試。結束後考官請輸入「關單」、「close」或「結束考試」來結算成績。")
            
            action_view = ExaminerActionView(view.bot, view.ticket_channel_id, examiner_save_val)
            await interaction.channel.send(embed=rules_embed, view=action_view)


class ExaminerAcceptView(discord.ui.View):
    """考官接單 View (動態按鈕版)"""

    def __init__(self, bot, ticket_channel_id: int, match_examiners: List[int], allowed_roles: List[str]):
        super().__init__(timeout=None)
        self.bot = bot
        self.ticket_channel_id = ticket_channel_id
        self.match_examiners = match_examiners
        self.allowed_roles = allowed_roles

        # 根據考試項目動態添加按鈕
        # 如果大於 1 個項目，則分別建立各自項目的接單按鈕，並加上一個「一鍵全包」按鈕
        if len(allowed_roles) > 1:
            for role in allowed_roles:
                self.add_item(ExaminerAcceptButton(label=f"接單 - {role} (我在)", exam_type=role, match_examiners=match_examiners))
            self.add_item(ExaminerAcceptButton(label="一鍵全包接單 (我在)", exam_type="all", match_examiners=match_examiners))
        else:
            role = allowed_roles[0] if allowed_roles else "考試"
            self.add_item(ExaminerAcceptButton(label="接單 (我在)", exam_type="all", match_examiners=match_examiners))


class ExaminerActionView(discord.ui.View):
    """考官操作結算 View"""

    def __init__(self, bot, ticket_channel_id: int, examiner_id: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.ticket_channel_id = ticket_channel_id
        self.examiner_id = str(examiner_id)

    @discord.ui.button(
        label="結算/關閉考試",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="guild_exam:close_action_btn"
    )
    async def close_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 驗證操作者權限
        examiners = [int(x) for x in str(self.examiner_id).split(",") if x.isdigit()]
        is_allowed = interaction.user.id in examiners or interaction.user.id == BYPASS_USER_ID or interaction.user.guild_permissions.administrator
        if not is_allowed:
            return await interaction.response.send_message("❌ 只有主考官或管理員可以結算考試！", ephemeral=True)

        await interaction.response.defer()
        cog = self.bot.get_cog("GuildExam")
        if cog:
            await cog.prompt_settlement(interaction.channel, self.ticket_channel_id)


class SettlementView(discord.ui.View):
    """結算選項 View"""

    def __init__(self, bot, ticket_channel_id: int, examiner_id: str):
        super().__init__(timeout=120)
        self.bot = bot
        self.ticket_channel_id = ticket_channel_id
        self.examiner_id = str(examiner_id)

    @discord.ui.button(label="過 (Pass)", style=discord.ButtonStyle.success, emoji="✅", custom_id="guild_exam:pass")
    async def pass_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        examiners = [int(x) for x in str(self.examiner_id).split(",") if x.isdigit()]
        if not (interaction.user.id in examiners or interaction.user.id == BYPASS_USER_ID or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ 您無權限操作此結算！", ephemeral=True)

        await interaction.response.defer()
        cog = self.bot.get_cog("GuildExam")
        if cog:
            await cog.settle_result(interaction, self.ticket_channel_id, "pass")
            self.stop()

    @discord.ui.button(label="沒過 (Fail)", style=discord.ButtonStyle.danger, emoji="❌", custom_id="guild_exam:fail")
    async def fail_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        examiners = [int(x) for x in str(self.examiner_id).split(",") if x.isdigit()]
        if not (interaction.user.id in examiners or interaction.user.id == BYPASS_USER_ID or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ 您無權限操作此結算！", ephemeral=True)

        await interaction.response.defer()
        cog = self.bot.get_cog("GuildExam")
        if cog:
            await cog.settle_result(interaction, self.ticket_channel_id, "fail")
            self.stop()

    @discord.ui.button(label="直接關單 (無紀錄)", style=discord.ButtonStyle.secondary, emoji="🗑️", custom_id="guild_exam:direct_close")
    async def direct_close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        examiners = [int(x) for x in str(self.examiner_id).split(",") if x.isdigit()]
        if not (interaction.user.id in examiners or interaction.user.id == BYPASS_USER_ID or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ 您無權限操作此結算！", ephemeral=True)

        await interaction.response.defer()
        cog = self.bot.get_cog("GuildExam")
        if cog:
            await cog.settle_result(interaction, self.ticket_channel_id, "direct_close")
            self.stop()


class ExaminerTypeSelectView(discord.ui.View):
    """考官類型指派 View"""

    def __init__(self, bot, member: discord.Member, ticket_channel_id: int):
        super().__init__(timeout=120)
        self.bot = bot
        self.member = member
        self.ticket_channel_id = ticket_channel_id

    @discord.ui.select(
        placeholder="選擇新考官的擅長項目 (可多選)...",
        min_values=1,
        max_values=3,
        options=[
            discord.SelectOption(label="小刀考官", value="knife", emoji="🔪"),
            discord.SelectOption(label="步槍考官", value="rifle", emoji="🔫"),
            discord.SelectOption(label="狙擊考官", value="sniper", emoji="🎯"),
        ],
        custom_id="guild_exam:assign_examiner_types"
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer()
        db = self.bot.db.db

        knife = 1 if "knife" in select.values else 0
        rifle = 1 if "rifle" in select.values else 0
        sniper = 1 if "sniper" in select.values else 0

        # 寫入或更新考官資料庫
        await db.execute(
            "INSERT OR REPLACE INTO guild_examiners (user_id, knife, rifle, sniper) VALUES (?, ?, ?, ?)",
            (self.member.id, knife, rifle, sniper)
        )
        await db.commit()

        await interaction.channel.send(f"✅ 已成功將 {self.member.mention} 登記為對應項目考官！")
        
        # 觸發戰隊名單更新
        cog = self.bot.get_cog("GuildExam")
        if cog:
            await cog.update_member_list(interaction.guild)

        # 進行最後清理
        await interaction.channel.send("🧹 結算與登錄完畢，本頻道將在 5 秒後刪除...")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass
        self.stop()


class Exam200AuditView(discord.ui.View):
    """200等以上免試申請 審核 View (持久化按鈕)"""

    def __init__(self, bot, applicant_id: int = 0):
        super().__init__(timeout=None)
        self.bot = bot
        self.applicant_id = applicant_id

    @discord.ui.button(
        label="同意免試通過",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="guild_exam:audit_approve"
    )
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_allowed = interaction.user.id == BYPASS_USER_ID or interaction.user.guild_permissions.administrator
        if not is_allowed:
            return await interaction.response.send_message("❌ 只有團長/最高管理員可以審核此免試申請！", ephemeral=True)

        await interaction.response.defer()
        guild = interaction.guild

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        applicant_id = self.applicant_id
        if not applicant_id and embed:
            for field in embed.fields:
                if field.name == "考生":
                    import re
                    m = re.search(r'\d+', field.value)
                    if m:
                        applicant_id = int(m.group(0))

        if not applicant_id:
            return await interaction.followup.send("❌ 無法辨識被審核的考生 ID！", ephemeral=True)

        student = guild.get_member(applicant_id)
        if not student:
            try:
                student = await guild.fetch_member(applicant_id)
            except Exception:
                pass

        db = self.bot.db.db

        # 1. 賦予已通過身分組 (ROLE_APPLICANT: 1478335180069671044)
        role = guild.get_role(ROLE_APPLICANT)
        if not role:
            role = discord.utils.get(guild.roles, id=ROLE_APPLICANT)
        if role and student:
            try:
                if role not in student.roles:
                    await student.add_roles(role)
            except Exception as e:
                print(f"⚠️ 賦予通過身分組失敗: {e}")

        # 2. 新增至戰隊核心成員資料庫
        await db.execute(
            "INSERT OR IGNORE INTO guild_core_members (user_id, note) VALUES (?, ?)",
            (applicant_id, "")
        )
        await db.commit()

        # 3. 更新戰隊名單
        cog = self.bot.get_cog("GuildExam")
        if cog:
            await cog.update_member_list(guild)

        # 4. 更新審核 Embed 與停用按鈕
        for child in self.children:
            child.disabled = True

        new_embed = embed if embed else discord.Embed(title="🎯 200等免試審核通過", color=discord.Color.green())
        new_embed.title = "✅ 200等免試申請審核通過"
        new_embed.color = discord.Color.green()
        new_embed.add_field(name="審核者", value=interaction.user.mention, inline=True)
        new_embed.set_footer(text=f"已由 {interaction.user.display_name} 核准通過並加入戰隊成員名單")

        await interaction.message.edit(embed=new_embed, view=self)

        if student:
            try:
                await student.send(f"🎉 恭喜！您的 200 等免試申請已由管理員 {interaction.user.mention} 審核通過，已將您加入戰隊成員名單並賦予 <@&{ROLE_APPLICANT}> 身分組！")
            except Exception:
                pass

    @discord.ui.button(
        label="拒絕申請",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="guild_exam:audit_reject"
    )
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_allowed = interaction.user.id == BYPASS_USER_ID or interaction.user.guild_permissions.administrator
        if not is_allowed:
            return await interaction.response.send_message("❌ 只有團長/最高管理員可以審核此免試申請！", ephemeral=True)

        await interaction.response.defer()

        for child in self.children:
            child.disabled = True

        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed(title="❌ 免試審核拒絕")
        embed.title = "❌ 200等免試申請已拒絕"
        embed.color = discord.Color.red()
        embed.add_field(name="審核者", value=interaction.user.mention, inline=True)

        await interaction.message.edit(embed=embed, view=self)


class DeployGuildExamView(discord.ui.View):
    """考試面板 Deploy 視圖"""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="開始考試",
        style=discord.ButtonStyle.success,
        emoji="📝",
        custom_id="guild_exam:deploy_start"
    )
    async def start_exam(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id != TARGET_GUILD_ID:
            return await interaction.response.send_message("❌ 此功能為限定伺服器的完整考試系統，其他伺服器無法使用！", ephemeral=True)

        db = self.bot.db.db
        
        # 檢查是否已同時擁有核心成員與考官身分組
        is_applicant = any(r.id == ROLE_APPLICANT for r in interaction.user.roles)
        is_coach = any(r.id == ROLE_COACH for r in interaction.user.roles)

        if is_applicant and is_coach:
            return await interaction.response.send_message("❌ 您已同時擁有核心成員與考官身份，無法再進行考試！", ephemeral=True)

        # 檢查設定
        async with db.execute(
            "SELECT category_id FROM guild_exam_settings WHERE guild_id = ?",
            (interaction.guild.id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row or not row[0]:
                return await interaction.response.send_message("❌ 尚未設定開票類別頻道，請管理員使用 `/exam-guild-setup` 設定！", ephemeral=True)
            category_id = row[0]

        # 檢查是否有進行中的 ticket
        async with db.execute(
            "SELECT channel_id FROM guild_exam_tickets WHERE user_id = ? AND status != 'completed' AND status != 'failed'",
            (interaction.user.id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                chan = interaction.guild.get_channel(row[0])
                if chan:
                    return await interaction.response.send_message(f"❌ 您已建立了一個考試頻道：{chan.mention}，請前往完成考試！", ephemeral=True)
                else:
                    # 頻道已不存在但 DB 還有紀錄時清理
                    await db.execute("DELETE FROM guild_exam_tickets WHERE channel_id = ?", (row[0],))
                    await db.commit()

        # 彈出 Modal
        modal = ExamRegisterModal(self.bot, category_id)
        await interaction.response.send_modal(modal)


class GuildExam(commands.Cog):
    """限定伺服器 (1472826730300309629) 專屬完整考試系統"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_tickets_loop.start()
        self.performance_settle_loop.start()

    def cog_unload(self):
        self.check_tickets_loop.cancel()
        self.performance_settle_loop.cancel()

    async def cog_load(self):
        # 註冊持久化按鈕 (重啟後繼續可用)
        self.bot.add_view(DeployGuildExamView(self.bot))
        self.bot.add_view(Exam200AuditView(self.bot))
        await self.init_db()
        # 重新加載所有進行中 Ticket 的持久化 View
        self.bot.loop.create_task(self.reload_active_views())

    async def reload_active_views(self):
        """Bot 啟動時，自動從資料庫讀取所有進行中的 Ticket，並重新註冊它們的持久化 View"""
        await self.bot.wait_until_ready()
        db = self.bot.db.db
        guild = self.bot.get_guild(TARGET_GUILD_ID)
        if not guild:
            try:
                guild = await self.bot.fetch_guild(TARGET_GUILD_ID)
            except Exception:
                pass
        if not guild:
            print("⚠️ 重新加載進行中考試 View 失敗：找不到目標伺服器")
            return

        try:
            async with db.execute(
                "SELECT channel_id, exam_types, assigned_examiner_id, status FROM guild_exam_tickets WHERE status != 'completed' AND status != 'failed'"
            ) as cursor:
                rows = await cursor.fetchall()

            for row in rows:
                channel_id, exam_types_json, assigned_examiner_id, status = row
                
                try:
                    exam_types = json.loads(exam_types_json)
                except Exception:
                    exam_types = []
                    
                # 重新計算 match_examiners
                conditions = []
                if "小刀" in exam_types:
                    conditions.append("knife = 1")
                if "步槍" in exam_types:
                    conditions.append("rifle = 1")
                if "狙擊" in exam_types:
                    conditions.append("sniper = 1")

                if "考考官" in exam_types or not conditions:
                    async with db.execute("SELECT user_id FROM guild_examiners") as cursor:
                        examiners_rows = await cursor.fetchall()
                        match_examiners = [r[0] for r in examiners_rows]
                    for uid in [BYPASS_USER_ID, 1458091320764661922, 1438132914712744009]:
                        if uid not in match_examiners:
                            match_examiners.append(uid)
                else:
                    query = "SELECT user_id FROM guild_examiners WHERE " + " OR ".join(conditions)
                    async with db.execute(query) as cursor:
                        examiners_rows = await cursor.fetchall()
                        match_examiners = [r[0] for r in examiners_rows]

                # 根據狀態重新註冊 View
                if status == 'waiting_examiner':
                    view = ExaminerAcceptView(self.bot, channel_id, match_examiners, exam_types)
                    self.bot.add_view(view)
                    print(f"🔄 [Reload View] 已成功為 Ticket 頻道 {channel_id} 重新載入 ExaminerAcceptView")
                elif status == 'testing' and assigned_examiner_id:
                    view = ExaminerActionView(self.bot, channel_id, str(assigned_examiner_id))
                    self.bot.add_view(view)
                    print(f"🔄 [Reload View] 已成功為 Ticket 頻道 {channel_id} 重新載入 ExaminerActionView")
        except Exception as e:
            print(f"❌ 重新加載進行中考試 View 出錯: {e}")

    async def init_db(self):
        """建立資料表與初始化預設考官與核心成員"""
        db = self.bot.db.db
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS guild_exam_settings (
                guild_id INTEGER PRIMARY KEY,
                panel_channel_id INTEGER,
                category_id INTEGER,
                member_channel_id INTEGER,
                ticket_counter INTEGER DEFAULT 0,
                member_list_message_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS guild_exam_tickets (
                channel_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                level TEXT,
                win_rate TEXT,
                rank TEXT,
                exam_types TEXT,
                assigned_examiner_id INTEGER,
                assigned_time TEXT,
                status TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS guild_examiners (
                user_id INTEGER PRIMARY KEY,
                knife INTEGER DEFAULT 0,
                rifle INTEGER DEFAULT 0,
                sniper INTEGER DEFAULT 0
            );

             CREATE TABLE IF NOT EXISTS guild_core_members (
                 user_id INTEGER PRIMARY KEY,
                 note TEXT
             );

             CREATE TABLE IF NOT EXISTS voice_time_tracker (
                 user_id INTEGER PRIMARY KEY,
                 seconds_this_month INTEGER DEFAULT 0,
                 last_join_time TEXT
             );
         """)
        await db.commit()

        # 如果考官表為空，寫入預設考官
        async with db.execute("SELECT COUNT(*) FROM guild_examiners") as cursor:
            row = await cursor.fetchone()
            if row and row[0] == 0:
                for uid, k, r, s in DEFAULT_EXAMINERS:
                    await db.execute(
                        "INSERT OR IGNORE INTO guild_examiners (user_id, knife, rifle, sniper) VALUES (?, ?, ?, ?)",
                        (uid, k, r, s)
                    )
                await db.commit()
                print("✅ 已成功初始化預設考官名單")

        # 如果核心成員表為空，寫入預設成員
        async with db.execute("SELECT COUNT(*) FROM guild_core_members") as cursor:
            row = await cursor.fetchone()
            if row and row[0] == 0:
                for uid, note in DEFAULT_CORE_MEMBERS:
                    await db.execute(
                        "INSERT OR IGNORE INTO guild_core_members (user_id, note) VALUES (?, ?)",
                        (uid, note)
                    )
                await db.commit()
                print("✅ 已成功初始化預設戰隊核心成員名單")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 背景循環任務：24 小時未接單輪替與 10 天無活動自動清理
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @tasks.loop(minutes=10)
    async def check_tickets_loop(self):
        if not getattr(self.bot, "is_active_node", True):
            return

        guild = self.bot.get_guild(TARGET_GUILD_ID)
        if not guild:
            return

        try:
            db = self.bot.db.db
            if not db:
                return
            now = datetime.now(timezone.utc)

            # 1. 查詢所有待處理的 Ticket
            async with db.execute(
                "SELECT channel_id, user_id, exam_types, assigned_time, status, created_at FROM guild_exam_tickets WHERE status != 'completed' AND status != 'failed'"
            ) as cursor:
                rows = await cursor.fetchall()

            for row in rows:
                channel_id, user_id, exam_types_json, assigned_time_str, status, created_at_str = row
                channel = guild.get_channel(channel_id)
                if not channel:
                    # 頻道已手動刪除，從資料庫中移除
                    await db.execute("DELETE FROM guild_exam_tickets WHERE channel_id = ?", (channel_id,))
                    await db.commit()
                    continue

                # A. 24 小時無考官接單輪替
                if status == 'waiting_examiner' and assigned_time_str:
                    assigned_time = datetime.fromisoformat(assigned_time_str)
                    if now - assigned_time >= timedelta(hours=24):
                        # 超過 24 小時，重新指派
                        try:
                            exam_types = json.loads(exam_types_json)
                            await channel.send("⏰ 由於接單期限已過 (24小時無考官接單)，系統正在重新為您尋找其他在線考官...")
                            await self.assign_examiner(channel, exam_types)
                        except Exception as e:
                            print(f"Error re-assigning examiners for channel {channel_id}: {e}")

                # B. 10 天無活動自動關閉
                try:
                    last_activity = None
                    # 讀取最後一條訊息
                    async for message in channel.history(limit=1):
                        last_activity = message.created_at

                    # 如果沒有任何訊息，則以建立時間為準
                    if not last_activity and created_at_str:
                        last_activity = datetime.fromisoformat(created_at_str)

                    if last_activity:
                        # 轉換為 offsets-aware 統一時區比對
                        if last_activity.tzinfo is None:
                            last_activity = last_activity.replace(tzinfo=timezone.utc)
                        else:
                            last_activity = last_activity.astimezone(timezone.utc)

                        if now - last_activity >= timedelta(days=10):
                            await channel.send("⏰ 此 Ticket 頻道由於 10 天內無 any 新對話與活動，系統將進行自動清理與關閉。")
                            await asyncio.sleep(5)
                            try:
                                await channel.delete()
                            except Exception:
                                pass
                            await db.execute("DELETE FROM guild_exam_tickets WHERE channel_id = ?", (channel_id,))
                            await db.commit()
                except Exception as e:
                    print(f"Error checking inactivity for channel {channel_id}: {e}")
        except Exception as e:
            print(f"Error in check_tickets_loop: {e}")

    @check_tickets_loop.before_loop
    async def before_check_tickets_loop(self):
        await self.bot.wait_until_ready()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 考官配對與結算邏輯
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    async def assign_examiner(self, channel: discord.TextChannel, exam_types: List[str]):
        """配對考官並在頻道中發送接單面板"""
        db = self.bot.db.db
        guild = channel.guild

        # 找符合考試項目的考官
        conditions = []
        if "小刀" in exam_types:
            conditions.append("knife = 1")
        if "步槍" in exam_types:
            conditions.append("rifle = 1")
        if "狙擊" in exam_types:
            conditions.append("sniper = 1")

        if "考考官" in exam_types or not conditions:
            # 考考官時，撈取所有登錄的考官
            async with db.execute("SELECT user_id FROM guild_examiners") as cursor:
                rows = await cursor.fetchall()
                match_examiners = [r[0] for r in rows]
            # 確保團長、副團長、副副團長也在名單內
            for uid in [BYPASS_USER_ID, 1458091320764661922, 1438132914712744009]:
                if uid not in match_examiners:
                    match_examiners.append(uid)
        else:
            query = "SELECT user_id FROM guild_examiners WHERE " + " OR ".join(conditions)
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                match_examiners = [r[0] for r in rows]

        # 篩選在線 (online, idle, dnd) 的考官。使用 fetch_member 強制拉取，避免 Discord cache get_member 漏失
        online_examiners = []
        for uid in match_examiners:
            try:
                m = await guild.fetch_member(uid)
                if m and m.status != discord.Status.offline:
                    online_examiners.append(m)
            except Exception:
                m = guild.get_member(uid)
                if m and m.status != discord.Status.offline:
                    online_examiners.append(m)

        # 決定被 ping 的考官與顯示名稱
        ping_mentions = []
        # 接單按鈕權限 match_examiners 永遠包含所有符合該項目的考官！
        target_examiners_ids = match_examiners

        if "考考官" in exam_types:
            # 考考官特別處理
            admin_mentions = []
            for uid in [BYPASS_USER_ID, 1458091320764661922, 1438132914712744009]:
                m = guild.get_member(uid)
                if m:
                    admin_mentions.append(m.mention)
            ping_mentions = admin_mentions if admin_mentions else [f"<@{BYPASS_USER_ID}>"]
        else:
            if online_examiners:
                # 優先一次找 2 個在線考官
                selected_members = online_examiners[:2]
                ping_mentions = [m.mention for m in selected_members]
            else:
                # 都沒有人在線，隨機挑選或直接 ping 全部符合考官的前 3 位
                ping_mentions = [f"<@{uid}>" for uid in match_examiners[:3] if guild.get_member(uid)]

        # 獲取考生 ID
        async with db.execute("SELECT user_id FROM guild_exam_tickets WHERE channel_id = ?", (channel.id,)) as cursor:
            row = await cursor.fetchone()
            student_id = row[0] if row else None
        student_mention = f"<@{student_id}>" if student_id else "未知"

        # 更新指派時間
        now_str = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE guild_exam_tickets SET assigned_time = ? WHERE channel_id = ?",
            (now_str, channel.id)
        )
        await db.commit()

        ping_str = " ".join(ping_mentions)
        embed = discord.Embed(
            title="🎯 新考試待接單",
            description=(
                f"**考生**：{student_mention}\n"
                f"**考試項目**：{', '.join(exam_types)}\n"
                f"**限時時間**：24 小時內 (一天後若無人接單將重新配對)\n\n"
                "請合適的考官點擊下方的 **「接單」** 按鈕以開始主持考試。"
            ),
            color=Colors.SUCCESS
        )

        view = ExaminerAcceptView(self.bot, channel.id, target_examiners_ids, exam_types)
        await channel.send(content=f"{ping_str} 有新的考試申請！", embed=embed, view=view)

    async def prompt_settlement(self, channel: discord.TextChannel, ticket_channel_id: int):
        db = self.bot.db.db
        async with db.execute(
            "SELECT user_id, assigned_examiner_id FROM guild_exam_tickets WHERE channel_id = ?",
            (ticket_channel_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return

            user_id, examiner_id = row
            # 如果資料庫沒有登記 examiner，預設為 BYPASS
            examiner_id = examiner_id or BYPASS_USER_ID

        embed = discord.Embed(
            title="🔒 結算考試結果",
            description="請考官點選以下結算結果：\n\n- **過 (Pass)**: 成員考試通過，賦予對應身份組\n- **沒過 (Fail)**: 考試不通過，提示一週後再來\n- **直接關單**: 不結算成績直接刪除此 Ticket 頻道",
            color=Colors.WARNING
        )
        view = SettlementView(self.bot, ticket_channel_id, examiner_id)
        await channel.send(embed=embed, view=view)

    async def settle_result(self, interaction: discord.Interaction, ticket_channel_id: int, result: str):
        db = self.bot.db.db
        guild = interaction.guild

        async with db.execute(
            "SELECT user_id, exam_types FROM guild_exam_tickets WHERE channel_id = ?",
            (ticket_channel_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return await interaction.channel.send("❌ 找不到此 Ticket 的考試紀錄。")
            user_id, exam_types_json = row

        student = guild.get_member(user_id)
        exam_types = json.loads(exam_types_json)
        is_coach_exam = "考考官" in exam_types

        # 變更狀態
        status = "completed" if result == "pass" else ("failed" if result == "fail" else "direct_close")
        await db.execute(
            "UPDATE guild_exam_tickets SET status = ? WHERE channel_id = ?",
            (status, ticket_channel_id)
        )
        await db.commit()

        if result == "direct_close":
            await interaction.channel.send("🧹 正在直接關閉頻道...")
            await db.execute("DELETE FROM guild_exam_tickets WHERE channel_id = ?", (ticket_channel_id,))
            await db.commit()
            await asyncio.sleep(5)
            try:
                await interaction.channel.delete()
            except Exception:
                pass
            return

        if result == "fail":
            await interaction.channel.send("😔 **可惜沒過，一個禮拜再過來考吧....**\n本頻道將在 5 秒後刪除...")
            await db.execute("DELETE FROM guild_exam_tickets WHERE channel_id = ?", (ticket_channel_id,))
            await db.commit()
            await asyncio.sleep(5)
            try:
                await interaction.channel.delete()
            except Exception:
                pass
            return

        # 通過 (pass)
        if student:
            if is_coach_exam:
                # 考考官通過：新增 ROLE_COACH 角色組
                role = guild.get_role(ROLE_COACH)
                if role:
                    try:
                        await student.add_roles(role)
                    except Exception as e:
                        await interaction.channel.send(f"⚠️ 無法為成員加上考官身份組: {e}")

                # 讓考官選擇新考官擅長項目
                await interaction.channel.send(
                    f"🎉 恭喜 {student.mention} 通過「考考官」考試！請主考官指派其擅長項目：",
                    view=ExaminerTypeSelectView(self.bot, student, ticket_channel_id)
                )
                return
            else:
                # 一般考試通過：新增 ROLE_APPLICANT 角色組
                role = guild.get_role(ROLE_APPLICANT)
                if role:
                    try:
                        await student.add_roles(role)
                    except Exception as e:
                        await interaction.channel.send(f"⚠️ 無法為成員加上核心成員身份組: {e}")

                # 新增核心成員至資料庫名單
                try:
                    await db.execute(
                        "INSERT OR IGNORE INTO guild_core_members (user_id, note) VALUES (?, ?)",
                        (student.id, "")
                    )
                    await db.commit()
                except Exception as e:
                    print(f"⚠️ 資料庫寫入失敗: {e}")

                await interaction.channel.send(f"🎉 **恭喜 {student.mention} 通過考試，成功加入！**")
                
                # 更新戰隊名單
                await self.update_member_list(guild)

                await interaction.channel.send("🧹 結算完畢，本頻道將在 5 秒後刪除...")
                await db.execute("DELETE FROM guild_exam_tickets WHERE channel_id = ?", (ticket_channel_id,))
                await db.commit()
                await asyncio.sleep(5)
                try:
                    await interaction.channel.delete()
                except Exception:
                    pass

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 戰隊名單動態渲染與發送
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    async def update_member_list(self, guild: discord.Guild):
        """根據伺服器角色組與考官資料庫更新成員名單 (固定編輯現有訊息)"""
        db = self.bot.db.db

        # 預設成員名單頻道 ID 為 1472873824914772121
        member_channel_id = 1472873824914772121
        last_message_id = None

        async with db.execute(
            "SELECT member_channel_id, member_list_message_id FROM guild_exam_settings WHERE guild_id = ?",
            (guild.id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                if row[0]:
                    member_channel_id = row[0]
                last_message_id = row[1]

        channel = guild.get_channel(member_channel_id)
        if not channel:
            try:
                channel = await guild.fetch_channel(member_channel_id)
            except Exception:
                return

        # 撈取考官分類
        knife_list = []
        rifle_list = []
        sniper_list = []

        async with db.execute("SELECT user_id, knife, rifle, sniper FROM guild_examiners") as cursor:
            rows = await cursor.fetchall()
            for r in rows:
                uid, k, r_val, s = r
                m = guild.get_member(uid)
                if not m:
                    continue
                mention_str = f"➤ <@{uid}>"
                if k:
                    knife_list.append(mention_str)
                if r_val:
                    rifle_list.append(mention_str)
                if s:
                    sniper_list.append(mention_str)

        # 從資料庫中讀取所有核心成員與備註
        core_members = []
        async with db.execute("SELECT user_id, note FROM guild_core_members") as cursor:
            rows = await cursor.fetchall()
            for r in rows:
                uid, note = r
                note_str = note if note else ""
                core_members.append(f"➤ <@{uid}>{note_str}")

        # 組合戰隊名單字串 (使用標準 Unicode Emoji)
        roster_text = (
            "╔════════════════════╗\n"
            "               ✨ 戰 隊 名 單 ✨ \n"
            "╚════════════════════╝\n\n"
            "👑 【團長】\n"
            f"➤ <@{BYPASS_USER_ID}>   💎 \n\n"
            " ⚔️ 【副團長】\n"
            f"➤ <@1458091320764661922>\n\n"
            " 🛡️ 【副副團長】\n"
            f"➤ <@1438132914712744009>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎓 【考官陣容】\n\n"
            "🔪 小刀考官\n"
            f"{chr(10).join(knife_list) if knife_list else '➤ *(無)*'}\n\n"
            "🎯 狙擊考官\n"
            f"{chr(10).join(sniper_list) if sniper_list else '➤ *(無)*'}\n\n"
            "🔫 步槍考官\n"
            f"{chr(10).join(rifle_list) if rifle_list else '➤ *(無)*'}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🛠️ 【管理團隊】\n"
            f"➤ <@1451749600636702751>\n"
            f"➤ <@1437408048934027274>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "👥 【核心成員】\n"
            f"{chr(10).join(core_members) if core_members else '➤ *(無)*'}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🌟 【Youtube】\n"
            f"<@&{ROLE_YOUTUBE}>\n\n"
            "⚔️ 「不是最強，但一定最敢打」🏆"
        )

        sent_msg = None
        if last_message_id:
            try:
                msg = await channel.fetch_message(last_message_id)
                await msg.edit(content=roster_text)
                sent_msg = msg
            except Exception:
                pass

        if not sent_msg:
            # 搜尋頻道中 Bot 發送過的最新成員名單訊息進行編輯
            try:
                async for historic_msg in channel.history(limit=20):
                    if historic_msg.author.id == self.bot.user.id and "戰 隊 名 單" in historic_msg.content:
                        await historic_msg.edit(content=roster_text)
                        sent_msg = historic_msg
                        break
            except Exception:
                pass

        if not sent_msg:
            # 找不到舊訊息時才發送新訊息
            sent_msg = await channel.send(content=roster_text)

        if sent_msg:
            await db.execute(
                "INSERT INTO guild_exam_settings (guild_id, member_channel_id, member_list_message_id) VALUES (?, ?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET member_channel_id=excluded.member_channel_id, member_list_message_id=excluded.member_list_message_id",
                (guild.id, member_channel_id, sent_msg.id)
            )
            await db.commit()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 監聽關閉命令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        
        # 僅在 Ticket 頻道內觸發
        if not isinstance(message.channel, discord.TextChannel) or not message.channel.name.startswith("ticket-"):
            return

        # 檢查資料庫是否有此進行中的 Ticket
        db = self.bot.db.db
        async with db.execute(
            "SELECT status, assigned_examiner_id FROM guild_exam_tickets WHERE channel_id = ?",
            (message.channel.id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return
            status, examiner_id = row

        # 指令解析
        content = message.content.strip().lower()
        if content in ["關單", "close", "結束考試"]:
            # 檢查權限 (主考官、團長、管理員)
            examiner_id = examiner_id or BYPASS_USER_ID
            examiners = [int(x) for x in str(examiner_id).split(",") if x.isdigit()]
            is_allowed = message.author.id in examiners or message.author.id == BYPASS_USER_ID or message.author.guild_permissions.administrator
            if not is_allowed:
                return await message.reply("❌ 只有主考官或管理員可以結算考試/關單！")

            await self.prompt_settlement(message.channel, message.channel.id)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 斜線指令管理群組
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    exam_guild = app_commands.Group(name="exam-guild", description="專屬完整考試系統管理")

    @exam_guild.command(name="setup", description="設定開票系統相關頻道與類別 (限定伺服器)")
    @app_commands.describe(
        panel_channel="放置開票面板的頻道",
        category="建立開票频道的類別",
        member_channel="放置戰隊名單的頻道"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @is_guild_limited()
    async def setup_settings(
        self,
        interaction: discord.Interaction,
        panel_channel: discord.TextChannel,
        category: discord.CategoryChannel,
        member_channel: discord.TextChannel
    ):
        db = self.bot.db.db
        try:
            await db.execute(
                "INSERT OR REPLACE INTO guild_exam_settings (guild_id, panel_channel_id, category_id, member_channel_id) VALUES (?, ?, ?, ?)",
                (interaction.guild.id, panel_channel.id, category.id, member_channel.id)
            )
            await db.commit()
        except Exception as e:
            return await interaction.response.send_message(
                f"❌ 設定寫入失敗: `{e}`\n若出現 `disk is full`，請至 Wispbyte 控制台清理磁碗空間！",
                ephemeral=True
            )

        await interaction.response.send_message(
            embed=EmbedFactory.success(
                "設定成功",
                f"✅ **開票面板頻道**：{panel_channel.mention}\n"
                f"✅ **開票類別**：`{category.name}`\n"
                f"✅ **成員名單頻道**：{member_channel.mention}"
            ),
            ephemeral=True
        )

    @exam_guild.command(name="panel", description="發送「開始考試」面板至設定的頻道 (限定伺服器)")
    @is_guild_limited()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def deploy_panel(self, interaction: discord.Interaction):
        db = self.bot.db.db
        async with db.execute(
            "SELECT panel_channel_id FROM guild_exam_settings WHERE guild_id = ?",
            (interaction.guild.id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row or not row[0]:
                return await interaction.response.send_message("❌ 尚未設定開票面板頻道，請先執行 `/exam-guild-setup`！", ephemeral=True)
            panel_channel_id = row[0]

        channel = interaction.guild.get_channel(panel_channel_id)
        if not channel:
            return await interaction.response.send_message("❌ 設定的面板頻道不存在，請重新設定！", ephemeral=True)

        embed = discord.Embed(
            title="⚔️ **戰隊考試申請入口**",
            description=(
                "歡迎申請加入我們的戰隊！請點擊下方的 **「開始考試」** 按鈕填寫報名表單。\n\n"
                "⚠️ **注意事項**：\n"
                "1. 點擊後，請輸入您的遊戲 **等級**、**勝率** 與 **牌位**。\n"
                "2. 系統會為您建立一個**專屬考試頻道**，請在該頻道中選擇您的考試項目。\n"
                "3. 考官將會接單進入頻道與您進行實戰或口試評估。"
            ),
            color=Colors.PRIMARY
        )

        view = DeployGuildExamView(self.bot)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ 考試開票面板已成功發送！", ephemeral=True)

    @exam_guild.command(name="update-roster", description="手動重新整理戰隊名單 (限定伺服器)")
    @is_guild_limited()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def force_update_roster(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.update_member_list(interaction.guild)
        await interaction.followup.send("✅ 戰隊成員名單已成功重新整理！", ephemeral=True)

    # 考官管理子群組
    examiners_group = app_commands.Group(name="examiner", description="管理考官名單與項目")

    @examiners_group.command(name="add", description="新增或修改考官項目")
    @app_commands.describe(member="要加入的考官", knife="是否考小刀", rifle="是否考步槍", sniper="是否考狙擊")
    @app_commands.checks.has_permissions(manage_guild=True)
    @is_guild_limited()
    async def examiner_add(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        knife: bool,
        rifle: bool,
        sniper: bool
    ):
        db = self.bot.db.db
        k = 1 if knife else 0
        r = 1 if rifle else 0
        s = 1 if sniper else 0

        await db.execute(
            "INSERT OR REPLACE INTO guild_examiners (user_id, knife, rifle, sniper) VALUES (?, ?, ?, ?)",
            (member.id, k, r, s)
        )
        await db.commit()

        # 賦予考官角色組
        role = interaction.guild.get_role(ROLE_COACH)
        if role:
            try:
                await member.add_roles(role)
            except Exception:
                pass

        await interaction.response.send_message(
            f"✅ 已成功將 {member.mention} 登記為考官！\n"
            f"🔪 小刀: {knife} | 🔫 步槍: {rifle} | 🎯 狙擊: {sniper}",
            ephemeral=True
        )
        await self.update_member_list(interaction.guild)

    @examiners_group.command(name="remove", description="刪除考官身分")
    @app_commands.describe(member="要移除的考官")
    @app_commands.checks.has_permissions(manage_guild=True)
    @is_guild_limited()
    async def examiner_remove(self, interaction: discord.Interaction, member: discord.Member):
        db = self.bot.db.db
        await db.execute("DELETE FROM guild_examiners WHERE user_id = ?", (member.id,))
        await db.commit()

        # 移除考官角色組
        role = interaction.guild.get_role(ROLE_COACH)
        if role:
            try:
                await member.remove_roles(role)
            except Exception:
                pass

        await interaction.response.send_message(f"✅ 已將 {member.mention} 從考官名單中移除。", ephemeral=True)
        await self.update_member_list(interaction.guild)

    @examiners_group.command(name="list", description="列出當前所有考官項目")
    @is_guild_limited()
    async def examiner_list(self, interaction: discord.Interaction):
        db = self.bot.db.db
        async with db.execute("SELECT user_id, knife, rifle, sniper FROM guild_examiners") as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return await interaction.response.send_message("❌ 目前尚無任何考官登錄資料。", ephemeral=True)

        embed = discord.Embed(title="📋 當前考官陣容項目", color=Colors.PRIMARY)
        details = ""
        for r in rows:
            uid, k, r_val, s = r
            m = interaction.guild.get_member(uid)
            name = m.mention if m else f"ID: {uid} (已離線/離群)"
            items = []
            if k: items.append("🔪 小刀")
            if r_val: items.append("🔫 步槍")
            if s: items.append("🎯 狙擊")
            details += f"• {name} — {', '.join(items) if items else '無指定項目'}\n"

        embed.description = details
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # 核心成員管理子群組
    members_group = app_commands.Group(name="member", description="管理核心成員名單")

    @members_group.command(name="add", description="手動新增成員至戰隊核心成員名單")
    @app_commands.describe(member="要新增的核心成員", note="備註說明 (例如: 950連勝!)")
    @app_commands.checks.has_permissions(manage_guild=True)
    @is_guild_limited()
    async def member_add(self, interaction: discord.Interaction, member: discord.Member, note: str = ""):
        db = self.bot.db.db
        note_formatted = f"  {note.strip()}  " if note.strip() else ""
        await db.execute("INSERT OR REPLACE INTO guild_core_members (user_id, note) VALUES (?, ?)", (member.id, note_formatted))
        await db.commit()

        role = interaction.guild.get_role(ROLE_APPLICANT)
        if role and role not in member.roles:
            try:
                await member.add_roles(role)
            except Exception:
                pass

        await interaction.response.send_message(f"✅ 已成功將 {member.mention} 新增至核心成員名單！", ephemeral=True)
        await self.update_member_list(interaction.guild)

    @members_group.command(name="remove", description="將成員從戰隊核心成員名單中移除")
    @app_commands.describe(member="要移除的核心成員")
    @app_commands.checks.has_permissions(manage_guild=True)
    @is_guild_limited()
    async def member_remove(self, interaction: discord.Interaction, member: discord.Member):
        db = self.bot.db.db
        await db.execute("DELETE FROM guild_core_members WHERE user_id = ?", (member.id,))
        await db.commit()

        role = interaction.guild.get_role(ROLE_APPLICANT)
        if role and role in member.roles:
            try:
                await member.remove_roles(role)
            except Exception:
                pass

        await interaction.response.send_message(f"✅ 已成功將 {member.mention} 從核心成員名單中移除！", ephemeral=True)
        await self.update_member_list(interaction.guild)

    @members_group.command(name="list", description="列出當前所有戰隊核心成員")
    @is_guild_limited()
    async def member_list(self, interaction: discord.Interaction):
        db = self.bot.db.db
        async with db.execute("SELECT user_id, note FROM guild_core_members") as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return await interaction.response.send_message("❌ 目前尚無任何核心成員資料。", ephemeral=True)

        embed = discord.Embed(title="👥 當前戰隊核心成員名單", color=Colors.PRIMARY)
        details = []
        for uid, note in rows:
            m = interaction.guild.get_member(uid)
            name = m.mention if m else f"ID: {uid}"
            note_str = f" `{note.strip()}`" if note and note.strip() else ""
            details.append(f"• {name}{note_str}")

        embed.description = "\n".join(details)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 考官語音業績追蹤與結算系統
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """監聽語音頻道狀態，累計考官的語音上線秒數"""
        if member.bot:
            return
        
        # 只記錄目標伺服器 (1472826730300309629)
        if member.guild.id != TARGET_GUILD_ID:
            return
            
        db = self.bot.db.db
        now_str = datetime.now(timezone.utc).isoformat()
        
        # 1. 剛加入語音頻道
        if before.channel is None and after.channel is not None:
            await db.execute(
                "INSERT OR IGNORE INTO voice_time_tracker (user_id, seconds_this_month, last_join_time) VALUES (?, 0, ?)",
                (member.id, now_str)
            )
            await db.execute(
                "UPDATE voice_time_tracker SET last_join_time = ? WHERE user_id = ?",
                (now_str, member.id)
            )
            await db.commit()
            
        # 2. 離開語音頻道
        elif before.channel is not None and after.channel is None:
            async with db.execute("SELECT last_join_time, seconds_this_month FROM voice_time_tracker WHERE user_id = ?", (member.id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    try:
                        join_time = datetime.fromisoformat(row[0])
                        duration = (datetime.now(timezone.utc) - join_time).total_seconds()
                        if duration > 0:
                            new_seconds = row[1] + int(duration)
                            await db.execute(
                                "UPDATE voice_time_tracker SET seconds_this_month = ?, last_join_time = NULL WHERE user_id = ?",
                                (new_seconds, member.id)
                            )
                            await db.commit()
                    except Exception as e:
                        print(f"Error updating voice duration: {e}")

    async def get_performance_report(self, guild: discord.Guild) -> tuple[str, discord.Embed]:
        """計算並產生考官業績分配報告"""
        db = self.bot.db.db
        
        # 1. 撈取所有考官
        async with db.execute("SELECT user_id FROM guild_examiners") as cursor:
            rows = await cursor.fetchall()
            examiner_ids = [r[0] for r in rows]
            
        if not examiner_ids:
            embed = discord.Embed(title="📊 考官業績分配報告", description="❌ 目前無登錄考官資料。", color=discord.Color.red())
            return "❌ 目前無登錄考官資料。", embed
            
        # 2. 獲取所有考官本月的語音秒數
        examiner_seconds = {}
        for uid in examiner_ids:
            async with db.execute("SELECT seconds_this_month FROM voice_time_tracker WHERE user_id = ?", (uid,)) as cursor:
                row = await cursor.fetchone()
                examiner_seconds[uid] = row[0] if row else 0
                
        # 3. 找出所有非團長的最低秒數
        others_seconds = [sec for uid, sec in examiner_seconds.items() if uid != BYPASS_USER_ID]
        min_others = min(others_seconds) if others_seconds else 0
        
        # 4. 團長時間調整 (最少原則)
        adjusted_seconds = {}
        for uid, sec in examiner_seconds.items():
            if uid == BYPASS_USER_ID:
                # 團長的上線時間調整為非團長最低時間的 0.8 倍 (以確保算出來的業績永遠最少)
                adjusted_seconds[uid] = int(min_others * 0.8)
            else:
                adjusted_seconds[uid] = sec
                
        total_adjusted = sum(adjusted_seconds.values())
        
        # 5. 產生 Embed 報告
        now = datetime.now()
        month_str = now.strftime("%Y年%m月")
        
        embed = discord.Embed(
            title=f"📊 {month_str} 考官語音業績分配報告",
            description="本報告依據考官本月語音上線時間進行業績權重分配，並套用「團長最少」原則進行微調。",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        
        details = []
        for uid in examiner_ids:
            actual_sec = examiner_seconds[uid]
            adj_sec = adjusted_seconds[uid]
            
            # 格式化實際時間
            hours = actual_sec // 3600
            minutes = (actual_sec % 3600) // 60
            time_str = f"`{hours}小時 {minutes}分鐘`"
            
            # 計算比例
            ratio = (adj_sec / total_adjusted * 100) if total_adjusted > 0 else 0.0
            
            member = guild.get_member(uid)
            mention_name = member.mention if member else f"<@{uid}>"
            
            tag = " 👑 (團長已調最少)" if uid == BYPASS_USER_ID else ""
            details.append((actual_sec, f"• {mention_name}：實際上線 {time_str} | **分配業績比例：{ratio:.2f}%**{tag}"))
            
        # 按實際時間排序
        details.sort(key=lambda x: x[0], reverse=True)
        embed.description += "\n\n" + "\n".join([d[1] for d in details])
        
        report_text = f"📊 **【考官月度業績報告】** ({month_str})\n"
        report_text += "詳細業績分配比率如下，請考官們知悉。"
        
        return report_text, embed

    @tasks.loop(hours=12)
    async def performance_settle_loop(self):
        """定時每個月 1 號進行自動結算發送"""
        if not getattr(self.bot, "is_active_node", True):
            return
            
        now = datetime.now()
        # 如果是 1 號 
        if now.day == 1:
            db = self.bot.db.db
            month_str = now.strftime("%Y-%m")
            
            # 查詢上次結算月份
            async with db.execute("SELECT value FROM global_settings WHERE key = 'last_settled_month'") as cursor:
                row = await cursor.fetchone()
                last_settled = row[0] if row else ""
                
            if last_settled != month_str:
                guild = self.bot.get_guild(TARGET_GUILD_ID)
                if guild:
                    # 業績發送目標頻道
                    performance_channel_id = 1499759365547098212
                    channel = guild.get_channel(performance_channel_id)
                    if channel:
                        report_text, embed = await self.get_performance_report(guild)
                        await channel.send(content=report_text, embed=embed)
                        
                        # 結算完畢，將所有人的語音秒數重設為 0
                        await db.execute("UPDATE voice_time_tracker SET seconds_this_month = 0")
                        
                        # 記錄本次結算月份
                        await db.execute(
                            "INSERT OR REPLACE INTO global_settings (key, value) VALUES ('last_settled_month', ?)",
                            (month_str,)
                        )
                        await db.commit()
                        print(f"📊 {month_str} 月度業績結算已自動發送並重設！")

    @performance_settle_loop.before_loop
    async def before_performance_settle_loop(self):
        await self.bot.wait_until_ready()

    @exam_guild.command(name="performance-check", description="預覽當前當月的考官語音業績分配報告 (限定伺服器)")
    @is_guild_limited()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def performance_check(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        report_text, embed = await self.get_performance_report(interaction.guild)
        await interaction.followup.send(content=report_text, embed=embed, ephemeral=True)

    @exam_guild.command(name="performance-settle", description="立即手動結算本月考官語音業績並發送至指定頻道 (限定伺服器)")
    @is_guild_limited()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def performance_settle(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db.db
        
        performance_channel_id = 1499759365547098212
        channel = interaction.guild.get_channel(performance_channel_id)
        if not channel:
            return await interaction.followup.send("❌ 找不到指定的業績發送頻道 `1499759365547098212`！", ephemeral=True)
            
        report_text, embed = await self.get_performance_report(interaction.guild)
        await channel.send(content=report_text, embed=embed)
        
        # 結算完畢，重設語音秒數
        await db.execute("UPDATE voice_time_tracker SET seconds_this_month = 0")
        
        # 記錄本次結算月份
        now = datetime.now()
        month_str = now.strftime("%Y-%m")
        await db.execute(
            "INSERT OR REPLACE INTO global_settings (key, value) VALUES ('last_settled_month', ?)",
            (month_str,)
        )
        await db.commit()
        
        await interaction.followup.send("✅ 業績已手動結算並發送成功，已重設當月考官語音累計秒數！", ephemeral=True)


    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 監聽身分組變動：自動同步核心成員名單
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """當成員獲得 ROLE_APPLICANT 身分組時，自動加入核心成員資料庫並更新名單"""
        if after.guild.id != TARGET_GUILD_ID:
            return

        # 找出新增的身分組
        before_role_ids = {r.id for r in before.roles}
        after_role_ids = {r.id for r in after.roles}
        added_roles = after_role_ids - before_role_ids

        if ROLE_APPLICANT not in added_roles:
            return

        db = self.bot.db.db

        # 若名單中已有此成員則跳過（INSERT OR IGNORE 保證不重複）
        async with db.execute(
            "SELECT 1 FROM guild_core_members WHERE user_id = ?",
            (after.id,)
        ) as cursor:
            existing = await cursor.fetchone()

        if existing:
            # 已在名單中，不重複新增，但仍確保名單是最新的
            return

        # 寫入資料庫
        await db.execute(
            "INSERT OR IGNORE INTO guild_core_members (user_id, note) VALUES (?, ?)",
            (after.id, "")
        )
        await db.commit()

        # 更新戰隊名單（固定頻道 1472873824914772121）
        await self.update_member_list(after.guild)
        print(f"✅ [on_member_update] {after.display_name} ({after.id}) 已自動加入核心成員名單")


async def setup(bot: commands.Bot):
    await bot.add_cog(GuildExam(bot))
