"""
考試系統 Cog
提供管理考試題目、部署考場入口、討論串作答，以及交卷回報至伺服器擁有者的完整流程
"""

import discord
from discord import app_commands
from discord.ext import commands
import json
import asyncio
import io
from datetime import datetime, timezone
from typing import Optional

from config import Colors, Emoji
from utils.embeds import EmbedFactory


class DeployExamView(discord.ui.View):
    """考試入口部署 View - 持久化按鈕"""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="開始考試",
        emoji="📝",
        style=discord.ButtonStyle.success,
        custom_id="exam:deploy_start"
    )
    async def start_exam(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = self.bot.db
        
        # 檢查是否已有進行中的考試
        async with db.db.execute(
            "SELECT thread_id FROM active_exams WHERE user_id = ? AND guild_id = ?",
            (interaction.user.id, interaction.guild.id)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                thread_id = row[0]
                thread = interaction.guild.get_thread(thread_id)
                if thread:
                    return await interaction.response.send_message(
                        embed=EmbedFactory.error("已在考試中", f"您已經有一個正在進行的考試討論串：{thread.mention}"),
                        ephemeral=True
                    )
                else:
                    # 討論串在 Discord 中已不存在但資料庫仍有紀錄時，執行清理
                    await db.delete_exam_session(thread_id)

        # 獲取題目
        questions = await db.get_exam_questions(interaction.guild.id)
        if not questions:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("尚無考試題目", "此伺服器目前沒有任何考試題目，請管理員先使用 `/exam-question add` 新增題目。"),
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        # 建立討論串
        thread_name = f"考試 - {interaction.user.display_name}"
        
        # 嘗試建立私密討論串，若不支援則建立公開討論串
        try:
            thread = await interaction.channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.private_thread,
                auto_archive_duration=60
            )
            is_private = True
        except Exception:
            thread = await interaction.channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.public_thread,
                auto_archive_duration=60
            )
            is_private = False

        # 建立會話，初始進度為 0
        await db.create_exam_session(thread.id, interaction.user.id, interaction.guild.id)

        # 將考生加入討論串
        try:
            await thread.add_user(interaction.user)
        except Exception:
            pass
            
        # 將伺服器擁有者加入討論串
        owner = interaction.guild.owner
        if not owner:
            try:
                owner = await interaction.guild.fetch_member(interaction.guild.owner_id)
            except Exception:
                pass
        if owner:
            try:
                await thread.add_user(owner)
            except Exception:
                pass

        # 說明 Embed
        welcome_embed = discord.Embed(
            title="📝 考試系統已啟動",
            description=(
                f"歡迎 {interaction.user.mention} 進入您的專屬考試討論串！\n\n"
                "💡 **答題說明**：\n"
                "1. 您可以使用下方選單任意切換要回答的題目。\n"
                "2. **直接在下方輸入訊息**，即可將該訊息記錄為目前選定題目的答案。\n"
                "3. 當您回答完一題，系統會自動儲存並切換至下一題。\n"
                "4. 全部回答完後，在討論串輸入 `我要交卷` 或點擊下方的「我要交卷」按鈕即可交卷。"
            ),
            color=Colors.PRIMARY
        )
        
        # 建立互動 View
        interactive_view = ExamInteractiveView(self.bot, thread.id, questions, 0, {})
        await thread.send(embed=welcome_embed, view=interactive_view)
        
        # 發送第一題題目內容
        first_q = questions[0]
        first_q_embed = discord.Embed(
            title="📝 目前題目：第 1 題",
            description=f"**題目內容**：\n{first_q['question_text']}",
            color=0x3498db
        )
        first_q_embed.add_field(name="**您的回答**", value="*(尚未回答)*", inline=False)
        await thread.send(embed=first_q_embed)

        private_hint = "（已建立私密討論串）" if is_private else "（不支援私密討論串，已建立公開討論串）"
        await interaction.followup.send(
            embed=EmbedFactory.success("考試討論串已建立", f"您的專屬考試討論串 {thread.mention} 已成功開啟，請進入開始答題！\n{private_hint}"),
            ephemeral=True
        )


class ExamQuestionSelect(discord.ui.Select):
    """切換考試題目的下拉選單"""

    def __init__(self, bot, thread_id: int, questions: list[dict], current_index: int, answers: dict):
        self.bot = bot
        self.thread_id = thread_id
        self.questions = questions
        self.answers = answers
        
        options = []
        for i, q in enumerate(questions[:25]):  # Discord 選單限制最多 25 個選項
            is_default = (i == current_index)
            q_id_str = str(q['id'])
            is_answered = q_id_str in answers
            emoji = "✅" if is_answered else "📝"
            
            options.append(discord.SelectOption(
                label=f"第 {i+1} 題",
                description=f"{q['question_text'][:50]}...",
                value=str(i),
                default=is_default,
                emoji=emoji
            ))
            
        super().__init__(
            placeholder="選擇切換要回答的題目...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"exam:select:{thread_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        db = self.bot.db
        session = await db.get_exam_session(self.thread_id)
        if not session:
            return await interaction.response.send_message("❌ 找不到此考試會話。", ephemeral=True)

        if interaction.user.id != session['user_id']:
            return await interaction.response.send_message("❌ 只有考生本人可以操作此選單！", ephemeral=True)

        idx = int(self.values[0])
        answers = json.loads(session['answers'])
        
        # 更新當前選中題目索引
        await db.update_exam_session(self.thread_id, idx, answers)

        # 重新建立視圖更新 UI 預選值
        new_view = ExamInteractiveView(self.bot, self.thread_id, self.questions, idx, answers)
        await interaction.response.edit_message(view=new_view)

        # 在討論串顯示該題題目
        question_text = self.questions[idx]['question_text']
        embed = discord.Embed(
            title=f"📝 目前題目：第 {idx+1} 題",
            description=f"**題目內容**：\n{question_text}",
            color=0x3498db
        )
        
        q_id_str = str(self.questions[idx]['id'])
        current_ans = answers.get(q_id_str, "*(尚未回答)*")
        embed.add_field(name="**您的回答**", value=f"```\n{current_ans}\n```", inline=False)
        
        await interaction.channel.send(embed=embed)


class ExamInteractiveView(discord.ui.View):
    """考試討論串內的互動 View"""

    def __init__(self, bot, thread_id: int, questions: list[dict], current_index: int, answers: dict):
        super().__init__(timeout=None)
        self.bot = bot
        self.thread_id = thread_id
        self.questions = questions
        self.current_index = current_index
        self.answers = answers
        
        # 動態添加題目下拉選單
        self.add_item(ExamQuestionSelect(bot, thread_id, questions, current_index, answers))

    @discord.ui.button(label="我要交卷", emoji="📤", style=discord.ButtonStyle.danger, custom_id="exam:btn_submit")
    async def submit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = self.bot.db
        session = await db.get_exam_session(self.thread_id)
        if not session:
            return await interaction.response.send_message("❌ 找不到此考試會話，可能已交卷或已關閉。", ephemeral=True)
        
        if interaction.user.id != session['user_id']:
            return await interaction.response.send_message("❌ 只有考生本人可以交卷！", ephemeral=True)

        cog = self.bot.get_cog("Exam")
        if cog:
            await interaction.response.defer()
            await cog.prompt_submit(interaction.channel, session)
        else:
            await interaction.response.send_message("❌ 系統錯誤：無法讀取 Exam 模組。", ephemeral=True)


class ConfirmSubmitView(discord.ui.View):
    """確認交卷 View"""

    def __init__(self, cog: "Exam", thread_id: int, user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.thread_id = thread_id
        self.user_id = user_id

    @discord.ui.button(label="確認交卷", emoji="✅", style=discord.ButtonStyle.danger, custom_id="exam:confirm_submit_btn")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ 只有考生本人可以點擊此確認按鈕！", ephemeral=True)
        
        await interaction.response.defer()
        await self.cog.submit_exam(interaction, self.thread_id, self.user_id)
        self.stop()


class Exam(commands.Cog):
    """考試系統 — 題目管理、部署與作答功能"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # 註冊 DeployExamView 持久化視圖
        self.bot.add_view(DeployExamView(self.bot))

    # 題目管理指令群組
    exam_question = app_commands.Group(name="exam-question", description="管理考試題目")

    @exam_question.command(name="add", description="新增考試題目 (上限 25 題)")
    @app_commands.describe(question_text="題目內容")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def add_question(self, interaction: discord.Interaction, question_text: str):
        db = self.bot.db
        questions = await db.get_exam_questions(interaction.guild_id)
        if len(questions) >= 25:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("無法新增題目", "❌ 為了系統穩定與下拉選單限制，每個伺服器最多只能設定 25 個考試題目！"),
                ephemeral=True
            )

        new_id = await db.add_exam_question(interaction.guild_id, question_text)
        await interaction.response.send_message(
            embed=EmbedFactory.success("新增題目成功", f"已成功新增題目！\n**ID**: `{new_id}`\n**內容**: {question_text}"),
            ephemeral=True
        )

    @exam_question.command(name="delete", description="刪除指定 ID 的考試題目")
    @app_commands.describe(question_id="要刪除的題目 ID")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def delete_question(self, interaction: discord.Interaction, question_id: int):
        db = self.bot.db
        success = await db.delete_exam_question(interaction.guild_id, question_id)
        if success:
            await interaction.response.send_message(
                embed=EmbedFactory.success("刪除成功", f"已成功刪除 ID 為 `{question_id}` 的題目。"),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=EmbedFactory.error("刪除失敗", f"找不到 ID 為 `{question_id}` 的題目，請確認 ID 是否正確。"),
                ephemeral=True
            )

    @exam_question.command(name="list", description="列出此伺服器的所有考試題目")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def list_questions(self, interaction: discord.Interaction):
        db = self.bot.db
        questions = await db.get_exam_questions(interaction.guild_id)
        if not questions:
            return await interaction.response.send_message(
                embed=EmbedFactory.info("尚無題目", "此伺服器目前沒有任何考試題目。"),
                ephemeral=True
            )

        embed = discord.Embed(
            title="📝 考試題目列表",
            description=f"此伺服器目前共有 `{len(questions)}` 個題目：",
            color=Colors.PRIMARY
        )
        for i, q in enumerate(questions):
            embed.add_field(
                name=f"ID: {q['id']} (第 {i+1} 題)",
                value=q['question_text'],
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # 部署指令
    @app_commands.command(name="exam-deploy", description="部署考試入口到指定頻道")
    @app_commands.describe(channel="部署的頻道 (留空則為目前頻道)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def deploy_exam(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        target_channel = channel or interaction.channel
        
        embed = discord.Embed(
            title="📝 **線上考試系統**",
            description=(
                "歡迎參加本次線上考試！請點擊下方的 **「開始考試」** 按鈕開始。\n\n"
                "⚠️ **注意事項**：\n"
                "1. 點擊後，系統將為您建立一個**專屬的個人考試討論串**。\n"
                "2. **伺服器擁有者**會被自動加入該討論串以進行監控與評分。\n"
                "3. 請在專屬討論串中進行答題與交卷。\n"
                "4. 考試過程中請遵守誠實原則。"
            ),
            color=Colors.PRIMARY
        )
        
        view = DeployExamView(self.bot)
        try:
            await target_channel.send(embed=embed, view=view)
            await interaction.response.send_message(
                embed=EmbedFactory.success("部署成功", f"考試入口已成功發送至 {target_channel.mention} 頻道。"),
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=EmbedFactory.error("部署失敗", f"Bot 缺少發送訊息至 {target_channel.mention} 的權限！"),
                ephemeral=True
            )

    # 監聽作答訊息
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        
        if not isinstance(message.channel, discord.Thread):
            return
            
        thread = message.channel
        db = self.bot.db
        session = await db.get_exam_session(thread.id)
        if not session:
            return
            
        # 僅限考生本人
        if message.author.id != session['user_id']:
            return

        # 處理交卷關鍵字
        if message.content.strip() == "我要交卷":
            await self.prompt_submit(thread, session)
            return

        # 獲取題目
        questions = await db.get_exam_questions(message.guild.id)
        if not questions:
            return

        current_idx = session['current_question_index']
        if current_idx >= len(questions):
            return

        active_q = questions[current_idx]
        q_id_str = str(active_q['id'])

        answers = json.loads(session['answers'])
        answers[q_id_str] = message.content

        # 自動跳下一題
        next_idx = current_idx + 1
        new_active_idx = next_idx if next_idx < len(questions) else current_idx
        await db.update_exam_session(thread.id, new_active_idx, answers)

        # 回覆儲存成功
        save_embed = discord.Embed(
            title="✅ 答案已記錄",
            description=f"已將您的回答記錄至 **第 {current_idx + 1} 題**。\n\n**答案內容**：\n```\n{message.content}\n```",
            color=Colors.SUCCESS
        )
        await message.reply(embed=save_embed, mention_author=False)

        # 更新討論串主選單的狀態（打勾已答題目）
        async for msg in thread.history(limit=50):
            if msg.author.id == self.bot.user.id and msg.components:
                has_select = False
                for action_row in msg.components:
                    for child in action_row.children:
                        if getattr(child, "custom_id", None) and child.custom_id.startswith("exam:select:"):
                            has_select = True
                            break
                if has_select:
                    new_view = ExamInteractiveView(self.bot, thread.id, questions, new_active_idx, answers)
                    try:
                        await msg.edit(view=new_view)
                    except Exception:
                        pass
                    break

        if next_idx < len(questions):
            next_q = questions[next_idx]

            # 發送下一題題目
            next_embed = discord.Embed(
                title=f"👉 下一題：第 {next_idx + 1} 題",
                description=f"**題目內容**：\n{next_q['question_text']}",
                color=0x3498db
            )
            next_q_id_str = str(next_q['id'])
            old_ans = answers.get(next_q_id_str, "*(尚未回答)*")
            next_embed.add_field(name="**您的回答**", value=f"```\n{old_ans}\n```", inline=False)
            
            await thread.send(embed=next_embed)
        else:
            finish_embed = discord.Embed(
                title="✨ 所有題目已回答完畢！",
                description="您已填寫所有題目的答案。若確認無誤，請輸入 `我要交卷` 或點擊下方的「我要交卷」按鈕以完成考試。",
                color=0x2ecc71
            )
            await thread.send(embed=finish_embed)

    async def prompt_submit(self, thread: discord.Thread, session: dict):
        embed = discord.Embed(
            title="📤 **確認交卷**",
            description="您確定要繳交考卷嗎？\n交卷後將無法修改答案，且此討論串將會被鎖定並封存。",
            color=0xe67e22
        )
        view = ConfirmSubmitView(self, thread.id, session['user_id'])
        await thread.send(embed=embed, view=view)

    async def submit_exam(self, interaction: discord.Interaction, thread_id: int, user_id: int):
        db = self.bot.db
        session = await db.get_exam_session(thread_id)
        if not session:
            return

        try:
            student = await self.bot.fetch_user(user_id)
        except Exception:
            student = interaction.user

        questions = await db.get_exam_questions(interaction.guild_id)
        answers = json.loads(session['answers'])

        # 作答回報 Embed
        report_embed = discord.Embed(
            title="📥 【考試作答回報】",
            description=f"考生 {student.mention} ({student.name} / ID: {student.id}) 已完成考試並交卷。",
            color=Colors.SUCCESS,
            timestamp=datetime.now(timezone.utc)
        )
        report_embed.add_field(name="**伺服器**", value=f"{interaction.guild.name} ({interaction.guild.id})", inline=True)
        report_embed.add_field(name="**考試頻道**", value=interaction.channel.mention, inline=True)

        details = ""
        for i, q in enumerate(questions):
            q_id_str = str(q['id'])
            ans = answers.get(q_id_str, "*(未回答)*")
            details += f"**第 {i+1} 題**：{q['question_text']}\n**作答**：\n```\n{ans}\n```\n"

        # 製作成文字檔案，防止字數限制報錯
        report_text = f"考試作答報告\n"
        report_text += f"========================\n"
        report_text += f"伺服器：{interaction.guild.name} ({interaction.guild.id})\n"
        report_text += f"考生：{student.name} (ID: {student.id})\n"
        report_text += f"交卷時間：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        report_text += f"========================\n\n"
        for i, q in enumerate(questions):
            q_id_str = str(q['id'])
            ans = answers.get(q_id_str, "*(未回答)*")
            report_text += f"第 {i+1} 題：{q['question_text']}\n"
            report_text += f"作答內容：\n{ans}\n"
            report_text += f"------------------------\n\n"

        # 寫入 Byte 串流
        file_data = io.BytesIO(report_text.encode('utf-8'))

        # 獲取擁有者並傳送私訊
        owner = interaction.guild.owner
        if not owner:
            try:
                owner = await interaction.guild.fetch_member(interaction.guild.owner_id)
            except Exception:
                pass

        dm_success = False
        if owner:
            try:
                file_data.seek(0)
                report_file_owner = discord.File(file_data, filename=f"exam_report_{student.name}_{user_id}.txt")
                
                # 如果詳情字數符合限制就放入 embed
                if len(details) < 1000:
                    report_embed.add_field(name="**作答內容**", value=details, inline=False)
                else:
                    report_embed.description += "\n\n📄 **完整作答詳情已夾帶於下方的文字檔案中。**"
                
                await owner.send(embed=report_embed, file=report_file_owner)
                dm_success = True
            except Exception as e:
                print(f"Failed to DM owner: {e}")
                dm_success = False

        # 刪除會話
        await db.delete_exam_session(thread_id)

        # 討論串收尾
        thread = interaction.channel
        if dm_success:
            await thread.send(embed=EmbedFactory.success("交卷成功", "🎉 您的作答結果已成功發送給伺服器擁有者！本討論串即將鎖定並封存。"))
        else:
            file_data.seek(0)
            report_file_thread = discord.File(file_data, filename=f"exam_report_{student.name}_{user_id}.txt")
            report_embed.add_field(name="⚠️ 注意", value="由於無法私訊伺服器擁有者，已將您的作答報告備份在此討論串中。", inline=False)
            if len(details) < 1000 and "**作答內容**" not in [f.name for f in report_embed.fields]:
                report_embed.add_field(name="**作答內容**", value=details, inline=False)
                
            await thread.send(embed=report_embed, file=report_file_thread)
            await thread.send("🎉 考試已交卷！本討論串即將鎖定並封存。")

        # 鎖定並封存討論串
        try:
            await thread.edit(locked=True, archived=True)
        except Exception as e:
            print(f"Failed to archive thread: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Exam(bot))
