"""
跨群聊天系統 Cog (多伺服器連線、智慧表單預填版)
提供不同 Ultra 旗艦版伺服器間進行跨群多向配對與即時聊天。
"""

import discord
from discord import app_commands
from discord.ext import commands
import random
import string
import typing
import asyncio

async def get_or_create_webhook(channel: discord.TextChannel) -> str:
    """獲取或建立跨群聊天專用 Webhook"""
    try:
        webhooks = await channel.webhooks()
        for wh in webhooks:
            if wh.name == "🛜-跨群聊天-Webhook":
                return wh.url
        # 建立新 Webhook
        webhook = await channel.create_webhook(name="🛜-跨群聊天-Webhook")
        return webhook.url
    except Exception as e:
        print(f"[Cross-Guild] 建立 Webhook 錯誤 ({channel.guild.name}): {e}")
        raise e


class CrossGuildCodeModal(discord.ui.Modal, title="輸入跨群聊天配對碼"):
    def __init__(self, cog: "CrossGuildChat", current_connections: list[tuple[str, str]]):
        super().__init__()
        self.cog = cog
        self.inputs = []

        # 建立 5 個輸入欄位，預填已連線的配對碼，並動態將伺服器名字顯示在標籤上
        for i in range(5):
            if i < len(current_connections):
                ccode, sname = current_connections[i]
                label_text = f"配對碼 {i+1} - {sname} (選填)"
                default_val = ccode
                is_required = False
            else:
                label_text = f"配對碼 {i+1}"
                if i == 0 and not current_connections:
                    label_text += " (必填)"
                else:
                    label_text += " (選填)"
                default_val = None
                is_required = (i == 0) and (not current_connections)

            text_input = discord.ui.TextInput(
                label=label_text[:45],  # Discord Label 限制最大 45 字元
                placeholder="例如: CG-XXXXXX",
                default=default_val,
                min_length=9,
                max_length=9,
                required=is_required
            )
            self.inputs.append(text_input)
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db = self.cog.bot.db
        guild_id = interaction.guild_id

        # 1. 檢查自己伺服器是否部署了跨群聊天
        async with db.db.execute(
            "SELECT channel_id, pairing_code FROM cross_guild_chat WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            self_row = await cursor.fetchone()
            if not self_row:
                return await interaction.followup.send("❌ 您的伺服器尚未部署跨群聊天！", ephemeral=True)
            self_channel_id, self_code = self_row

        # 2. 收集提交的配對碼
        submitted_codes = []
        for inp in self.inputs:
            if inp.value:
                cleaned = inp.value.strip().upper()
                if cleaned and cleaned not in submitted_codes:
                    submitted_codes.append(cleaned)

        # 3. 取得目前已建立的連線資訊
        async with db.db.execute(
            """SELECT c.connected_guild_id, cg.pairing_code 
               FROM cross_guild_connections c 
               JOIN cross_guild_chat cg ON c.connected_guild_id = cg.guild_id 
               WHERE c.guild_id = ?""",
            (guild_id,)
        ) as cursor:
            current_rows = await cursor.fetchall()
            current_connections = {row[1]: row[0] for row in current_rows if row[1]}

        # 4. 處理「移除」的連線：原本有，但這次提交的表單中被清空的
        removed_guilds = []
        for ccode, cid in current_connections.items():
            if ccode not in submitted_codes:
                await db.db.execute(
                    "DELETE FROM cross_guild_connections WHERE (guild_id = ? AND connected_guild_id = ?) OR (guild_id = ? AND connected_guild_id = ?)",
                    (guild_id, cid, cid, guild_id)
                )
                removed_guilds.append((cid, ccode))

        # 5. 處理「新增」的連線：這次有提交，但原本沒有建立連線的
        new_codes = [code for code in submitted_codes if code not in current_connections]

        success_targets = []
        failed_reasons = []

        is_self_ultra = await db.is_guild_ultra(guild_id)
        if new_codes and not is_self_ultra:
            return await interaction.followup.send("❌ 跨群聊天功能僅限啟用 Ultra 旗艦版權限的伺服器使用！", ephemeral=True)

        for code in new_codes:
            # 搜尋目標伺服器
            async with db.db.execute(
                "SELECT guild_id, channel_id FROM cross_guild_chat WHERE pairing_code = ?",
                (code,)
            ) as cursor:
                target_row = await cursor.fetchone()
                if not target_row:
                    failed_reasons.append(f"`{code}`: 找不到此配對碼。")
                    continue
                target_guild_id, target_channel_id = target_row

            if target_guild_id == guild_id:
                failed_reasons.append(f"`{code}`: 不能與自己的伺服器配對。")
                continue

            # 驗證目標伺服器的 Ultra 資格
            is_target_ultra = await db.is_guild_ultra(target_guild_id)
            if not is_target_ultra:
                failed_reasons.append(f"`{code}`: 對方伺服器尚未啟用 Ultra 旗艦版。")
                continue

            # 尋找對方伺服器與頻道
            target_guild = self.cog.bot.get_guild(target_guild_id)
            if not target_guild:
                failed_reasons.append(f"`{code}`: 無法連線到對方伺服器，可能機器人不在該伺服器。")
                continue

            target_channel = target_guild.get_channel(target_channel_id)
            if not target_channel:
                failed_reasons.append(f"`{code}`: 找不到對方的跨群聊天頻道，對方可能已刪除或取消部署。")
                continue

            # 寫入邀請表
            await db.db.execute(
                "INSERT OR IGNORE INTO cross_guild_invites (guild_id, inviter_guild_id) VALUES (?, ?)",
                (target_guild_id, guild_id)
            )
            await db.db.commit()

            # 向對方頻道發送邀請訊息
            embed = discord.Embed(
                title="🛜 收到跨群聊天邀請！",
                description=(
                    f"來自伺服器 **{interaction.guild.name}** (`{self_code}`) 發起了跨群配對邀請。\n\n"
                    f"👉 點擊下方的 **「接受邀請」** 按鈕建立雙向通訊連線。\n"
                    f"👉 點擊 **「拒絕邀請」** 拒絕此連線。"
                ),
                color=0xE67E22
            )
            try:
                await target_channel.send(embed=embed, view=CrossGuildInviteView())
                success_targets.append(target_guild.name)
            except Exception as e:
                failed_reasons.append(f"`{code}`: 發送邀請訊息失敗 ({e})。")

        # 6. 通知並刷新被中斷連線的對方伺服器控制面板
        for cid, ccode in removed_guilds:
            other_guild = self.cog.bot.get_guild(cid)
            if other_guild:
                async with db.db.execute(
                    "SELECT channel_id FROM cross_guild_chat WHERE guild_id = ?",
                    (cid,)
                ) as cursor:
                    other_chan_row = await cursor.fetchone()
                    if other_chan_row:
                        other_channel = other_guild.get_channel(other_chan_row[0])
                        if other_channel:
                            try:
                                await other_channel.send(f"🔌 **對方伺服器 ({interaction.guild.name}) 已與您斷開連線。**")
                            except Exception:
                                pass
                await self.cog.update_pairing_panel(cid)

        # 7. 提交資料庫更動並動態更新自己控制面板
        await db.db.commit()
        await self.cog.update_pairing_panel(guild_id)

        # 8. 建立回報訊息
        result_msg = ""
        if success_targets:
            result_msg += f"✅ 已成功向以下伺服器發送配對邀請：\n" + "\n".join([f"• **{name}**" for name in success_targets])
            self_channel = interaction.guild.get_channel(self_channel_id)
            if self_channel:
                targets_str = "、".join([f"**{name}**" for name in success_targets])
                await self_channel.send(f"⏳ 已向伺服器 {targets_str} 發送配對邀請，正在等待對方確認...")
        
        if removed_guilds:
            if result_msg:
                result_msg += "\n\n"
            removed_names = []
            for cid, ccode in removed_guilds:
                other_g = self.cog.bot.get_guild(cid)
                removed_names.append(other_g.name if other_g else f"未知伺服器 ({cid})")
            result_msg += f"🔌 已成功中斷與以下伺服器的連線：\n" + "\n".join([f"• **{name}**" for name in removed_names])
            self_channel = interaction.guild.get_channel(self_channel_id)
            if self_channel:
                await self_channel.send(f"🔌 已中斷與伺服器 「" + "、".join(removed_names) + "」的連線。")

        if failed_reasons:
            if result_msg:
                result_msg += "\n\n"
            result_msg += f"❌ 部份配對碼處理失敗：\n" + "\n".join([f"• {reason}" for reason in failed_reasons])

        if not result_msg:
            result_msg = "ℹ️ 表單提交完成，沒有任何變更。"

        await interaction.followup.send(result_msg, ephemeral=True)


class CrossGuildUnpairedView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="輸入配對碼", style=discord.ButtonStyle.primary, emoji="🛜", custom_id="cg_btn_input_code")
    async def input_code(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("CrossGuildChat")
        if not cog:
            return await interaction.response.send_message("❌ 跨群聊天系統目前不可用。", ephemeral=True)

        if not (interaction.user.guild_permissions.administrator or interaction.user.id == 1437408048934027274):
            return await interaction.response.send_message("❌ 您需要「管理員」權限才能進行配對輸入！", ephemeral=True)

        # 撈出當前已連線的伺服器名稱與配對代碼，用於預填 Modal 欄位
        db = interaction.client.db
        async with db.db.execute(
            """SELECT c.connected_guild_id, cg.pairing_code 
               FROM cross_guild_connections c 
               JOIN cross_guild_chat cg ON c.connected_guild_id = cg.guild_id 
               WHERE c.guild_id = ?""",
            (interaction.guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            current_connections = []
            for cid, ccode in rows:
                if ccode:
                    g = interaction.client.get_guild(cid)
                    name = g.name if g else f"未知伺服器 ({cid})"
                    current_connections.append((ccode, name))

        await interaction.response.send_modal(CrossGuildCodeModal(cog, current_connections))


class CrossGuildInviteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="接受邀請", style=discord.ButtonStyle.success, emoji="✅", custom_id="cg_btn_accept_invite")
    async def accept_invite(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("CrossGuildChat")
        if not cog:
            return await interaction.response.send_message("❌ 跨群聊天系統目前不可用。", ephemeral=True)

        if not (interaction.user.guild_permissions.administrator or interaction.user.id == 1437408048934027274):
            return await interaction.response.send_message("❌ 您需要「管理員」權限才能接受邀請！", ephemeral=True)

        await cog.handle_accept_invite(interaction)

    @discord.ui.button(label="拒絕邀請", style=discord.ButtonStyle.danger, emoji="❌", custom_id="cg_btn_reject_invite")
    async def reject_invite(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("CrossGuildChat")
        if not cog:
            return await interaction.response.send_message("❌ 跨群聊天系統目前不可用。", ephemeral=True)

        if not (interaction.user.guild_permissions.administrator or interaction.user.id == 1437408048934027274):
            return await interaction.response.send_message("❌ 您需要「管理員」權限才能拒絕邀請！", ephemeral=True)

        await cog.handle_reject_invite(interaction)


class CrossGuildPairedView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="輸入配對碼 (新增連線)", style=discord.ButtonStyle.primary, emoji="🛜", custom_id="cg_btn_add_connection")
    async def add_connection(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("CrossGuildChat")
        if not cog:
            return await interaction.response.send_message("❌ 跨群聊天系統目前不可用。", ephemeral=True)

        if not (interaction.user.guild_permissions.administrator or interaction.user.id == 1437408048934027274):
            return await interaction.response.send_message("❌ 您需要「管理員」權限才能進行配對！", ephemeral=True)

        # 撈出當前已連線的伺服器名稱與配對代碼，用於預填 Modal 欄位
        db = interaction.client.db
        async with db.db.execute(
            """SELECT c.connected_guild_id, cg.pairing_code 
               FROM cross_guild_connections c 
               JOIN cross_guild_chat cg ON c.connected_guild_id = cg.guild_id 
               WHERE c.guild_id = ?""",
            (interaction.guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            current_connections = []
            for cid, ccode in rows:
                if ccode:
                    g = interaction.client.get_guild(cid)
                    name = g.name if g else f"未知伺服器 ({cid})"
                    current_connections.append((ccode, name))

        await interaction.response.send_modal(CrossGuildCodeModal(cog, current_connections))

    @discord.ui.button(label="斷開連線", style=discord.ButtonStyle.danger, emoji="🔌", custom_id="cg_btn_disconnect")
    async def disconnect(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("CrossGuildChat")
        if not cog:
            return await interaction.response.send_message("❌ 跨群聊天系統目前不可用。", ephemeral=True)

        if not (interaction.user.guild_permissions.administrator or interaction.user.id == 1437408048934027274):
            return await interaction.response.send_message("❌ 您需要「管理員」權限才能斷開連線！", ephemeral=True)

        await cog.handle_disconnect(interaction)


class CrossGuildChat(commands.Cog):
    """跨群聊天系統管理 Cog"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # 註冊持久性 View 監聽器
        self.bot.add_view(CrossGuildUnpairedView())
        self.bot.add_view(CrossGuildInviteView())
        self.bot.add_view(CrossGuildPairedView())

    async def sync_guild_commands(self, guild: discord.Guild):
        """清除舊的伺服器特定指令，遷移至全域指令"""
        try:
            self.bot.tree.remove_command("部署跨群聊天", guild=guild)
            self.bot.tree.remove_command("移除跨群聊天", guild=guild)
            await self.bot.tree.sync(guild=guild)
        except Exception:
            pass

    async def update_pairing_panel(self, guild_id: int):
        """動態刷新控制面板 Embed 與按鈕"""
        db = self.bot.db
        
        async with db.db.execute(
            "SELECT channel_id, pairing_code, pairing_message_id FROM cross_guild_chat WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return
            channel_id, pairing_code, pairing_message_id = row

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        channel = guild.get_channel(channel_id)
        if not channel or not pairing_message_id:
            return

        # 撈出當前所有已建立的連線關係與其配對碼
        async with db.db.execute(
            """SELECT c.connected_guild_id, cg.pairing_code 
               FROM cross_guild_connections c 
               LEFT JOIN cross_guild_chat cg ON c.connected_guild_id = cg.guild_id 
               WHERE c.guild_id = ?""",
            (guild_id,)
        ) as cursor:
            connected_rows = await cursor.fetchall()

        if not connected_rows:
            # 無連線狀態，顯示未配對 Embed
            embed = discord.Embed(
                title="🛜 跨群聊天配對系統",
                description=(
                    f"本伺服器的配對碼為：`{pairing_code}`\n\n"
                    f"💡 **如何配對：**\n"
                    f"1. 將您的配對碼發給別的伺服器，讓他們點擊下方「輸入配對碼」進行配對。\n"
                    f"2. 或者點擊下方 **「輸入配對碼」**，輸入對方伺服器的配對碼。\n\n"
                    f"⚠️ **注意：** 跨群聊天僅限 Ultra 伺服器使用。雙方都必須是已啟用的 Ultra 伺服器。"
                ),
                color=0x3498DB
            )
            view = CrossGuildUnpairedView()
        else:
            # 渲染已連線伺服器清單 (顯示名字與對應的配對碼)
            server_list_str = ""
            for cid, ccode in connected_rows:
                other_g = self.bot.get_guild(cid)
                name = other_g.name if other_g else f"未知伺服器 ({cid})"
                code_suffix = f" (`{ccode}`)" if ccode else ""
                server_list_str += f"• 🟢 **{name}**{code_suffix}\n"

            embed = discord.Embed(
                title="🛜 跨群聊天已連線",
                description=(
                    f"本伺服器的配對碼為：`{pairing_code}`\n\n"
                    f"💡 **當前連線伺服器：**\n"
                    f"{server_list_str}\n"
                    f"💬 在此頻道發送任何訊息，對方伺服器都會即時收到您的訊息！\n"
                    f"您可以繼續點擊下方 **「輸入配對碼 (新增連線)」** 連結更多伺服器。"
                ),
                color=0x2ECC71
            )
            view = CrossGuildPairedView()

        try:
            msg = await channel.fetch_message(pairing_message_id)
            await msg.edit(embed=embed, view=view)
        except Exception as e:
            print(f"[Cross-Guild] 更新控制面板失敗 {guild.name}: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        # 準備就緒時，為所有伺服器動態同步指令樹
        for guild in self.bot.guilds:
            await self.sync_guild_commands(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self.sync_guild_commands(guild)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        # 被踢出伺服器時，清理其相關跨群資料列
        db = self.bot.db
        await db.db.execute("DELETE FROM cross_guild_chat WHERE guild_id = ?", (guild.id,))
        await db.db.execute("DELETE FROM cross_guild_connections WHERE guild_id = ? OR connected_guild_id = ?", (guild.id, guild.id))
        await db.db.execute("DELETE FROM cross_guild_invites WHERE guild_id = ? OR inviter_guild_id = ?", (guild.id, guild.id))
        await db.db.commit()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """當部署的跨群頻道被手動刪除時，自動處理多向斷開連線與清理設定"""
        if not isinstance(channel, discord.TextChannel):
            return

        guild_id = channel.guild.id
        db = self.bot.db

        async with db.db.execute(
            "SELECT channel_id FROM cross_guild_chat WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row or channel.id != row[0]:
                return

        print(f"[Cross-Guild] {channel.guild.name} 的跨群聊天頻道被手動刪除，開始清理...")

        # 1. 取得所有連線伺服器並進行斷開通知與更新
        async with db.db.execute(
            "SELECT connected_guild_id FROM cross_guild_connections WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            connected_rows = await cursor.fetchall()
            connected_ids = [r[0] for r in connected_rows]

        for other_id in connected_ids:
            # 刪除雙向連線
            await db.db.execute(
                "DELETE FROM cross_guild_connections WHERE (guild_id = ? AND connected_guild_id = ?) OR (guild_id = ? AND connected_guild_id = ?)",
                (guild_id, other_id, other_id, guild_id)
            )
            # 通知對方
            other_guild = self.bot.get_guild(other_id)
            if other_guild:
                async with db.db.execute(
                    "SELECT channel_id FROM cross_guild_chat WHERE guild_id = ?",
                    (other_id,)
                ) as other_cursor:
                    other_chan_row = await other_cursor.fetchone()
                    if other_chan_row:
                        other_chan = other_guild.get_channel(other_chan_row[0])
                        if other_chan:
                            try:
                                await other_chan.send(f"⚠️ **對方伺服器 ({channel.guild.name}) 已移除跨群聊天，連線已斷開。**")
                            except Exception:
                                pass
                await self.update_pairing_panel(other_id)

        # 2. 清除自身資料庫設定與邀請
        await db.db.execute("DELETE FROM cross_guild_chat WHERE guild_id = ?", (guild_id,))
        await db.db.execute("DELETE FROM cross_guild_connections WHERE guild_id = ? OR connected_guild_id = ?", (guild_id, guild_id))
        await db.db.execute("DELETE FROM cross_guild_invites WHERE guild_id = ? OR inviter_guild_id = ?", (guild_id, guild_id))
        await db.db.commit()

        # 3. 同步指令樹
        await self.sync_guild_commands(channel.guild)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """處理跨伺服器訊息轉發 (多向併發轉發)"""
        if message.author.bot or not message.guild:
            return

        db = self.bot.db
        guild_id = message.guild.id

        # 1. 檢查發言頻道是否為該伺服器的跨群聊天頻道
        async with db.db.execute(
            "SELECT channel_id FROM cross_guild_chat WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row or message.channel.id != row[0]:
                return

        # 2. 獲取所有連線伺服器與對方的頻道與 webhook
        async with db.db.execute(
            """SELECT c.connected_guild_id, c.webhook_url, cg.channel_id 
               FROM cross_guild_connections c 
               JOIN cross_guild_chat cg ON c.connected_guild_id = cg.guild_id 
               WHERE c.guild_id = ?""",
            (guild_id,)
        ) as cursor:
            connections = await cursor.fetchall()

        if not connections:
            return

        # 準備要傳送的檔案附件
        files = []
        for attachment in message.attachments:
            try:
                file = await attachment.to_file()
                files.append(file)
            except Exception:
                pass

        content = f"<@{message.author.id}> : {message.content or ''}"
        username = f"{message.author.display_name} | {message.guild.name}"
        avatar_url = message.author.display_avatar.url

        if not message.content and not files:
            return

        # 3. 使用 asyncio.gather 併發轉發至各個伺服器
        tasks = []
        for dest_guild_id, dest_webhook_url, dest_channel_id in connections:
            tasks.append(
                self.forward_to_single_connection(
                    guild_id, dest_guild_id, dest_webhook_url, dest_channel_id, content, username, avatar_url, files
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 4. 儲存訊息映射關係
        valid_results = []
        for res in results:
            if isinstance(res, tuple) and len(res) == 2:
                valid_results.append(res)

        if valid_results:
            group_id = f"{message.channel.id}-{message.id}"
            try:
                # 插入原始訊息
                await db.db.execute(
                    "INSERT OR IGNORE INTO cross_guild_message_mappings (group_id, channel_id, message_id) VALUES (?, ?, ?)",
                    (group_id, message.channel.id, message.id)
                )
                # 插入轉發後的訊息
                for dest_chan_id, dest_msg_id in valid_results:
                    await db.db.execute(
                        "INSERT OR IGNORE INTO cross_guild_message_mappings (group_id, channel_id, message_id) VALUES (?, ?, ?)",
                        (group_id, dest_chan_id, dest_msg_id)
                    )
                await db.db.commit()
            except Exception as e:
                print(f"[Cross-Guild] 儲存訊息對應失敗: {e}")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """同步訊息編輯"""
        if after.author.bot or not after.guild:
            return

        db = self.bot.db
        # 檢查是否為該伺服器的跨群聊天頻道
        async with db.db.execute(
            "SELECT channel_id FROM cross_guild_chat WHERE guild_id = ?", (after.guild.id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row or after.channel.id != row[0]:
                return

        # 查詢是否有對應的群組訊息
        async with db.db.execute(
            "SELECT group_id FROM cross_guild_message_mappings WHERE channel_id = ? AND message_id = ?",
            (after.channel.id, after.id)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return
            group_id = row[0]

        # 查詢群組內的所有其他訊息
        async with db.db.execute(
            "SELECT channel_id, message_id FROM cross_guild_message_mappings WHERE group_id = ? AND NOT (channel_id = ? AND message_id = ?)",
            (group_id, after.channel.id, after.id)
        ) as cursor:
            other_msgs = await cursor.fetchall()

        if not other_msgs:
            return

        content = f"<@{after.author.id}> : {after.content or ''}"

        # 對其他每個伺服器的對應訊息執行編輯
        for dest_chan_id, dest_msg_id in other_msgs:
            dest_channel = self.bot.get_channel(dest_chan_id)
            if not dest_channel:
                continue
            try:
                webhooks = await dest_channel.webhooks()
                webhook = discord.utils.get(webhooks, name="🛜-跨群聊天-Webhook")
                if webhook:
                    await webhook.edit_message(
                        dest_msg_id,
                        content=content,
                        allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=False)
                    )
            except Exception as e:
                print(f"[Cross-Guild] 編輯轉發訊息 {dest_msg_id} 失敗: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """同步新增表情符號"""
        if payload.user_id == self.bot.user.id:
            return

        db = self.bot.db
        async with db.db.execute(
            "SELECT group_id FROM cross_guild_message_mappings WHERE channel_id = ? AND message_id = ?",
            (payload.channel_id, payload.message_id)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return
            group_id = row[0]

        async with db.db.execute(
            "SELECT channel_id, message_id FROM cross_guild_message_mappings WHERE group_id = ? AND NOT (channel_id = ? AND message_id = ?)",
            (group_id, payload.channel_id, payload.message_id)
        ) as cursor:
            other_msgs = await cursor.fetchall()

        for dest_chan_id, dest_msg_id in other_msgs:
            dest_channel = self.bot.get_channel(dest_chan_id)
            if not dest_channel:
                continue
            try:
                msg = await dest_channel.fetch_message(dest_msg_id)
                await msg.add_reaction(payload.emoji)
            except Exception as e:
                print(f"[Cross-Guild] 同步反應失敗 (新增): {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """同步移除表情符號"""
        if payload.user_id == self.bot.user.id:
            return

        db = self.bot.db
        async with db.db.execute(
            "SELECT group_id FROM cross_guild_message_mappings WHERE channel_id = ? AND message_id = ?",
            (payload.channel_id, payload.message_id)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return
            group_id = row[0]

        async with db.db.execute(
            "SELECT channel_id, message_id FROM cross_guild_message_mappings WHERE group_id = ? AND NOT (channel_id = ? AND message_id = ?)",
            (group_id, payload.channel_id, payload.message_id)
        ) as cursor:
            other_msgs = await cursor.fetchall()

        for dest_chan_id, dest_msg_id in other_msgs:
            dest_channel = self.bot.get_channel(dest_chan_id)
            if not dest_channel:
                continue
            try:
                msg = await dest_channel.fetch_message(dest_msg_id)
                await msg.remove_reaction(payload.emoji, self.bot.user)
            except Exception as e:
                print(f"[Cross-Guild] 同步反應失敗 (移除): {e}")

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """同步訊息刪除"""
        db = self.bot.db
        # 查詢被刪除的訊息是否在映射表中
        async with db.db.execute(
            "SELECT group_id FROM cross_guild_message_mappings WHERE channel_id = ? AND message_id = ?",
            (payload.channel_id, payload.message_id)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return
            group_id = row[0]

        # 查詢群組內所有其他訊息
        async with db.db.execute(
            "SELECT channel_id, message_id FROM cross_guild_message_mappings WHERE group_id = ? AND NOT (channel_id = ? AND message_id = ?)",
            (group_id, payload.channel_id, payload.message_id)
        ) as cursor:
            other_msgs = await cursor.fetchall()

        # 刪除其他伺服器的對應訊息
        for dest_chan_id, dest_msg_id in other_msgs:
            dest_channel = self.bot.get_channel(dest_chan_id)
            if not dest_channel:
                continue
            try:
                # 取得對方的 Webhook 來刪除訊息 (Webhook 刪除訊息不需要管理訊息權限，且最不易出錯)
                webhooks = await dest_channel.webhooks()
                webhook = discord.utils.get(webhooks, name="🛜-跨群聊天-Webhook")
                if webhook:
                    await webhook.delete_message(dest_msg_id)
                else:
                    # 備用方案：使用 Bot 直接刪除
                    msg = await dest_channel.fetch_message(dest_msg_id)
                    await msg.delete()
            except Exception as e:
                print(f"[Cross-Guild] 刪除轉發訊息 {dest_msg_id} 失敗: {e}")

        # 清理資料庫中此群組的所有映射記錄
        try:
            await db.db.execute(
                "DELETE FROM cross_guild_message_mappings WHERE group_id = ?",
                (group_id,)
            )
            await db.db.commit()
        except Exception as e:
            print(f"[Cross-Guild] 清理訊息對應記錄失敗: {e}")

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        """同步批次訊息刪除 (例如 /purge 指令)"""
        db = self.bot.db
        for msg_id in payload.message_ids:
            # 查詢被刪除的訊息是否在映射表中
            async with db.db.execute(
                "SELECT group_id FROM cross_guild_message_mappings WHERE channel_id = ? AND message_id = ?",
                (payload.channel_id, msg_id)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    continue
                group_id = row[0]

            # 查詢群組內所有其他訊息
            async with db.db.execute(
                "SELECT channel_id, message_id FROM cross_guild_message_mappings WHERE group_id = ? AND NOT (channel_id = ? AND message_id = ?)",
                (group_id, payload.channel_id, msg_id)
            ) as cursor:
                other_msgs = await cursor.fetchall()

            # 刪除其他伺服器的對應訊息
            for dest_chan_id, dest_msg_id in other_msgs:
                dest_channel = self.bot.get_channel(dest_chan_id)
                if not dest_channel:
                    continue
                try:
                    webhooks = await dest_channel.webhooks()
                    webhook = discord.utils.get(webhooks, name="🛜-跨群聊天-Webhook")
                    if webhook:
                        await webhook.delete_message(dest_msg_id)
                    else:
                        msg = await dest_channel.fetch_message(dest_msg_id)
                        await msg.delete()
                except Exception as e:
                    print(f"[Cross-Guild] 刪除轉發訊息 {dest_msg_id} 失敗: {e}")

            # 清理資料庫中此群組的映射記錄
            try:
                await db.db.execute(
                    "DELETE FROM cross_guild_message_mappings WHERE group_id = ?",
                    (group_id,)
                )
            except Exception:
                pass
        await db.db.commit()

    async def forward_to_single_connection(self, sender_guild_id: int, dest_guild_id: int, dest_webhook_url: str, dest_channel_id: int, content: str, username: str, avatar_url: str, files: list):
        """單一伺服器的轉發子協程，含 Webhook 自動重建與容錯"""
        db = self.bot.db
        dest_guild = self.bot.get_guild(dest_guild_id)
        if not dest_guild:
            return
        dest_channel = dest_guild.get_channel(dest_channel_id)
        if not dest_channel:
            return

        try:
            # 複製檔案流，防止多 Webhook 共用導致檔案關閉錯誤
            cloned_files = []
            for f in files:
                if f.fp:
                    f.fp.seek(0)
                import io
                if hasattr(f.fp, 'read'):
                    b = f.fp.read()
                    f.fp.seek(0)
                    cloned_files.append(discord.File(io.BytesIO(b), filename=f.filename))
                else:
                    cloned_files.append(discord.File(f.fp, filename=f.filename))

            webhook_url = dest_webhook_url
            try:
                webhook = discord.Webhook.from_url(webhook_url, client=self.bot)
            except ValueError:
                webhook = None

            # 若無 Webhook 則自動補建
            if not webhook:
                webhook_url = await get_or_create_webhook(dest_channel)
                await db.db.execute(
                    "UPDATE cross_guild_connections SET webhook_url = ? WHERE guild_id = ? AND connected_guild_id = ?",
                    (webhook_url, sender_guild_id, dest_guild_id)
                )
                await db.db.commit()
                webhook = discord.Webhook.from_url(webhook_url, client=self.bot)

            # 發送訊息
            try:
                sent_msg = await webhook.send(
                    content=content,
                    username=username[:80],
                    avatar_url=avatar_url,
                    files=cloned_files,
                    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=False),
                    wait=True
                )
                return dest_channel.id, sent_msg.id
            except discord.NotFound:
                # 若 404 Webhook 已被刪除，則重新補建與更新發送
                webhook_url = await get_or_create_webhook(dest_channel)
                await db.db.execute(
                    "UPDATE cross_guild_connections SET webhook_url = ? WHERE guild_id = ? AND connected_guild_id = ?",
                    (webhook_url, sender_guild_id, dest_guild_id)
                )
                await db.db.commit()
                webhook = discord.Webhook.from_url(webhook_url, client=self.bot)
                sent_msg = await webhook.send(
                    content=content,
                    username=username[:80],
                    avatar_url=avatar_url,
                    files=cloned_files,
                    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=False),
                    wait=True
                )
                return dest_channel.id, sent_msg.id
        except Exception as e:
            print(f"[Cross-Guild] 轉發至伺服器 {dest_guild.name} 失敗: {e}")
            return None

    # ─── 邀請與連線處理函數 ──────────────────────────────────────

    async def handle_accept_invite(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        db = self.bot.db

        # 1. 查詢該伺服器收到的所有待處理邀請及其配對碼
        async with db.db.execute(
            """SELECT i.inviter_guild_id, cg.pairing_code 
               FROM cross_guild_invites i 
               LEFT JOIN cross_guild_chat cg ON i.inviter_guild_id = cg.guild_id 
               WHERE i.guild_id = ?""",
            (guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return await interaction.followup.send("❌ 沒有收到任何邀請，或邀請已過期。", ephemeral=True)

        if len(rows) == 1:
            # 只有一個邀請，直接接受
            await self.process_accept_invite(interaction, rows[0][0])
        else:
            # 有多個邀請，顯示下拉式選單讓管理員選擇
            options = []
            for iid, ccode in rows:
                other_g = self.bot.get_guild(iid)
                name = other_g.name if other_g else f"未知伺服器 ({iid})"
                options.append(discord.SelectOption(
                    label=f"{name[:20]} ({ccode or '未知'})",
                    description=f"接受來自 {name} 的配對邀請",
                    value=str(iid)
                ))

            class AcceptInviteSelect(discord.ui.Select):
                def __init__(self, cog, options):
                    super().__init__(
                        placeholder="選擇要接受配對的伺服器...",
                        min_values=1,
                        max_values=1,
                        options=options,
                        custom_id="cg_select_accept_invite"
                    )
                    self.cog = cog

                async def callback(self, select_interaction: discord.Interaction):
                    await select_interaction.response.defer(ephemeral=True)
                    await self.cog.process_accept_invite(select_interaction, int(self.values[0]))

            view = discord.ui.View(timeout=60)
            view.add_item(AcceptInviteSelect(self, options))
            await interaction.followup.send("請選擇要接受哪一個伺服器的邀請：", view=view, ephemeral=True)

    async def handle_reject_invite(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        db = self.bot.db

        # 1. 查詢該伺服器收到的所有待處理邀請及其配對碼
        async with db.db.execute(
            """SELECT i.inviter_guild_id, cg.pairing_code 
               FROM cross_guild_invites i 
               LEFT JOIN cross_guild_chat cg ON i.inviter_guild_id = cg.guild_id 
               WHERE i.guild_id = ?""",
            (guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return await interaction.followup.send("❌ 沒有收到任何邀請，或邀請已過期。", ephemeral=True)

        if len(rows) == 1:
            # 只有一個邀請，直接拒絕
            await self.process_reject_invite(interaction, rows[0][0])
        else:
            # 有多個邀請，顯示下拉式選單讓管理員選擇
            options = []
            for iid, ccode in rows:
                other_g = self.bot.get_guild(iid)
                name = other_g.name if other_g else f"未知伺服器 ({iid})"
                options.append(discord.SelectOption(
                    label=f"{name[:20]} ({ccode or '未知'})",
                    description=f"拒絕來自 {name} 的配對邀請",
                    value=str(iid)
                ))

            class RejectInviteSelect(discord.ui.Select):
                def __init__(self, cog, options):
                    super().__init__(
                        placeholder="選擇要拒絕配對的伺服器...",
                        min_values=1,
                        max_values=1,
                        options=options,
                        custom_id="cg_select_reject_invite"
                    )
                    self.cog = cog

                async def callback(self, select_interaction: discord.Interaction):
                    await select_interaction.response.defer(ephemeral=True)
                    await self.cog.process_reject_invite(select_interaction, int(self.values[0]))

            view = discord.ui.View(timeout=60)
            view.add_item(RejectInviteSelect(self, options))
            await interaction.followup.send("請選擇要拒絕哪一個伺服器的邀請：", view=view, ephemeral=True)

    async def process_accept_invite(self, interaction: discord.Interaction, inviter_guild_id: int):
        db = self.bot.db
        guild_id = interaction.guild_id

        # 1. 驗證雙方的 Ultra 旗艦版資格
        is_self_ultra = await db.is_guild_ultra(guild_id)
        is_inviter_ultra = await db.is_guild_ultra(inviter_guild_id)
        if not is_self_ultra or not is_inviter_ultra:
            return await interaction.followup.send("❌ 跨群聊天僅限雙方伺服器皆啟用 Ultra 旗艦版權限時才能使用！", ephemeral=True)

        # 2. 尋找對方伺服器與頻道
        inviter_guild = self.bot.get_guild(inviter_guild_id)
        if not inviter_guild:
            return await interaction.followup.send("❌ 找不到邀請來源伺服器，可能機器人已退出對方伺服器。", ephemeral=True)

        # 取得頻道
        async with db.db.execute(
            "SELECT channel_id, pairing_message_id FROM cross_guild_chat WHERE guild_id = ?",
            (inviter_guild_id,)
        ) as cursor:
            inviter_row = await cursor.fetchone()
            if not inviter_row:
                return await interaction.followup.send("❌ 對方伺服器已取消跨群聊天部署。", ephemeral=True)
            inviter_channel_id, inviter_message_id = inviter_row

        async with db.db.execute(
            "SELECT channel_id FROM cross_guild_chat WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            self_row = await cursor.fetchone()
            if not self_row:
                return await interaction.followup.send("❌ 您的伺服器尚未部署跨群聊天！", ephemeral=True)
            channel_id = self_row[0]

        inviter_channel = inviter_guild.get_channel(inviter_channel_id)
        self_channel = interaction.guild.get_channel(channel_id)
        if not inviter_channel or not self_channel:
            return await interaction.followup.send("❌ 找不到配對頻道，連線失敗。", ephemeral=True)

        # 3. 建立雙向 Webhooks
        try:
            self_webhook_url = await get_or_create_webhook(self_channel)
            inviter_webhook_url = await get_or_create_webhook(inviter_channel)
        except discord.Forbidden:
            return await interaction.followup.send("❌ 機器人缺少「管理 Webhook」權限，連線建立失敗。", ephemeral=True)
        except Exception as e:
            return await interaction.followup.send(f"❌ 建立 Webhook 時發生錯誤: {e}", ephemeral=True)

        # 4. 寫入連線關係表 (雙向對應)
        await db.db.execute(
            "INSERT OR IGNORE INTO cross_guild_connections (guild_id, connected_guild_id, webhook_url) VALUES (?, ?, ?)",
            (guild_id, inviter_guild_id, inviter_webhook_url)
        )
        await db.db.execute(
            "INSERT OR IGNORE INTO cross_guild_connections (guild_id, connected_guild_id, webhook_url) VALUES (?, ?, ?)",
            (inviter_guild_id, guild_id, self_webhook_url)
        )
        # 刪除已處理的邀請
        await db.db.execute(
            "DELETE FROM cross_guild_invites WHERE guild_id = ? AND inviter_guild_id = ?",
            (guild_id, inviter_guild_id)
        )
        await db.db.commit()

        # 5. 嘗試清除卡片訊息上的按鈕 View 
        if interaction.message and interaction.message.components:
            try:
                await interaction.message.delete()
            except Exception:
                pass

        # 6. 動態更新兩邊的控制面板
        await self.update_pairing_panel(guild_id)
        await self.update_pairing_panel(inviter_guild_id)

        # 7. 發送公告
        await self_channel.send(f"🛜 跨群通訊已建立！與 **{inviter_guild.name}** 開始聊天吧！")
        await inviter_channel.send(f"🛜 跨群通訊已建立！與 **{interaction.guild.name}** 開始聊天吧！")

        await interaction.followup.send(f"✅ 已成功接受邀請，與 **{inviter_guild.name}** 建立連線！", ephemeral=True)

    async def process_reject_invite(self, interaction: discord.Interaction, inviter_guild_id: int):
        db = self.bot.db
        guild_id = interaction.guild_id

        # 1. 刪除該邀請
        await db.db.execute(
            "DELETE FROM cross_guild_invites WHERE guild_id = ? AND inviter_guild_id = ?",
            (guild_id, inviter_guild_id)
        )
        await db.db.commit()

        # 2. 刪除卡片
        if interaction.message and interaction.message.components:
            try:
                await interaction.message.delete()
            except Exception:
                pass

        # 3. 通知對方
        inviter_guild = self.bot.get_guild(inviter_guild_id)
        if inviter_guild:
            async with db.db.execute(
                "SELECT channel_id FROM cross_guild_chat WHERE guild_id = ?",
                (inviter_guild_id,)
            ) as cursor:
                inviter_row = await cursor.fetchone()
                if inviter_row:
                    inviter_channel = inviter_guild.get_channel(inviter_row[0])
                    if inviter_channel:
                        try:
                            await inviter_channel.send(f"⚠️ **{interaction.guild.name}** 拒絕了您的跨群配對邀請。")
                        except Exception:
                            pass

        await interaction.followup.send(f"已拒絕來自 **{inviter_guild.name if inviter_guild else inviter_guild_id}** 的跨群聊天邀請。", ephemeral=True)

    async def handle_disconnect(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        db = self.bot.db

        # 1. 查詢所有連線中的伺服器與其配對碼
        async with db.db.execute(
            """SELECT c.connected_guild_id, cg.pairing_code 
               FROM cross_guild_connections c 
               LEFT JOIN cross_guild_chat cg ON c.connected_guild_id = cg.guild_id 
               WHERE c.guild_id = ?""",
            (guild_id,)
        ) as cursor:
            connected_rows = await cursor.fetchall()

        if not connected_rows:
            return await interaction.followup.send("❌ 尚未建立任何跨群聊天連線。", ephemeral=True)

        if len(connected_rows) == 1:
            # 只有一個連線，直接斷開
            await self.process_disconnect(interaction, connected_rows[0][0])
        else:
            # 多個連線，顯示下拉選單
            options = []
            for cid, ccode in connected_rows:
                other_g = self.bot.get_guild(cid)
                name = other_g.name if other_g else f"未知伺服器 ({cid})"
                options.append(discord.SelectOption(
                    label=f"{name[:20]} ({ccode or '未知'})",
                    description=f"中斷與 {name} 的連線",
                    value=str(cid)
                ))
            
            # 加入「全部斷開」選項
            options.append(discord.SelectOption(
                label="全部斷開",
                description="中斷目前所有的跨群連線關係",
                value="all",
                emoji="🔌"
            ))

            class DisconnectSelect(discord.ui.Select):
                def __init__(self, cog, options):
                    super().__init__(
                        placeholder="選擇要斷開連線的伺服器...",
                        min_values=1,
                        max_values=1,
                        options=options,
                        custom_id="cg_select_disconnect"
                    )
                    self.cog = cog

                async def callback(self, select_interaction: discord.Interaction):
                    await select_interaction.response.defer(ephemeral=True)
                    val = self.values[0]
                    if val == "all":
                        await self.cog.process_disconnect_all(select_interaction)
                    else:
                        await self.cog.process_disconnect(select_interaction, int(val))

            view = discord.ui.View(timeout=60)
            view.add_item(DisconnectSelect(self, options))
            await interaction.followup.send("請選擇要斷開連線的目標伺服器：", view=view, ephemeral=True)

    async def process_disconnect(self, interaction: discord.Interaction, other_guild_id: int):
        db = self.bot.db
        guild_id = interaction.guild_id

        # 1. 取得各自頻道資訊
        async with db.db.execute(
            "SELECT channel_id FROM cross_guild_chat WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            self_row = await cursor.fetchone()
            self_channel_id = self_row[0] if self_row else None

        async with db.db.execute(
            "SELECT channel_id FROM cross_guild_chat WHERE guild_id = ?",
            (other_guild_id,)
        ) as cursor:
            other_row = await cursor.fetchone()
            other_channel_id = other_row[0] if other_row else None

        # 2. 刪除雙向連線紀錄
        await db.db.execute(
            "DELETE FROM cross_guild_connections WHERE (guild_id = ? AND connected_guild_id = ?) OR (guild_id = ? AND connected_guild_id = ?)",
            (guild_id, other_guild_id, other_guild_id, guild_id)
        )
        await db.db.commit()

        # 3. 發送中斷公告
        self_channel = interaction.guild.get_channel(self_channel_id) if self_channel_id else None
        other_guild = self.bot.get_guild(other_guild_id)
        other_name = other_guild.name if other_guild else f"未知伺服器 ({other_guild_id})"
        
        if self_channel:
            await self_channel.send(f"🔌 **已中斷與 {other_name} 的連線。**")

        if other_guild and other_channel_id:
            other_channel = other_guild.get_channel(other_channel_id)
            if other_channel:
                await other_channel.send(f"🔌 **對方伺服器 ({interaction.guild.name}) 已與本伺服器斷開連線。**")

        # 4. 刷新雙方控制面板 UI
        await self.update_pairing_panel(guild_id)
        await self.update_pairing_panel(other_guild_id)

        await interaction.followup.send(f"✅ 已成功斷開與 **{other_name}** 的跨群聊天連線。", ephemeral=True)

    async def process_disconnect_all(self, interaction: discord.Interaction):
        db = self.bot.db
        guild_id = interaction.guild_id

        # 1. 取得自己頻道
        async with db.db.execute(
            "SELECT channel_id FROM cross_guild_chat WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            self_row = await cursor.fetchone()
            self_channel_id = self_row[0] if self_row else None

        # 2. 取得所有連線
        async with db.db.execute(
            "SELECT connected_guild_id FROM cross_guild_connections WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            connected_ids = [r[0] for r in rows]

        # 3. 遍歷移除並通知對方
        for other_id in connected_ids:
            await db.db.execute(
                "DELETE FROM cross_guild_connections WHERE (guild_id = ? AND connected_guild_id = ?) OR (guild_id = ? AND connected_guild_id = ?)",
                (guild_id, other_id, other_id, guild_id)
            )
            other_guild = self.bot.get_guild(other_id)
            if other_guild:
                async with db.db.execute(
                    "SELECT channel_id FROM cross_guild_chat WHERE guild_id = ?",
                    (other_id,)
                ) as cursor:
                    other_row = await cursor.fetchone()
                    if other_row:
                        other_channel = other_guild.get_channel(other_row[0])
                        if other_channel:
                            try:
                                await other_channel.send(f"🔌 **對方伺服器 ({interaction.guild.name}) 已與本伺服器斷開連線。**")
                            except Exception:
                                pass
                await self.update_pairing_panel(other_id)

        await db.db.commit()

        # 4. 通知自己頻道並刷新面板
        self_channel = interaction.guild.get_channel(self_channel_id) if self_channel_id else None
        if self_channel:
            await self_channel.send("🔌 **已中斷本伺服器所有的跨群聊天連線。**")
            
        await self.update_pairing_panel(guild_id)

        await interaction.followup.send("✅ 已成功中斷本伺服器所有的跨群聊天連線關係。", ephemeral=True)

    # ─── 指令回呼函數 ──────────────────────────────────────────

    @app_commands.command(name="部署跨群聊天", description="[Ultra 專屬] 部署跨群聊天專用頻道並啟用配對")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def deploy_cross_guild_chat(self, interaction: discord.Interaction):
        """部署跨群聊天指令回呼"""
        # 1. 檢查是否為 Ultra 伺服器
        ultra_cog = self.bot.get_cog("Ultra")
        if ultra_cog and not await ultra_cog.check_ultra(interaction):
            return

        # 2. 檢查使用權限 (管理員)
        if not (interaction.user.guild_permissions.administrator or interaction.user.id == 1437408048934027274):
            return await interaction.response.send_message("❌ 您需要「管理員」權限才能執行此指令！", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        db = self.bot.db

        # 檢查是否已部署
        async with db.db.execute(
            "SELECT channel_id FROM cross_guild_chat WHERE guild_id = ?", (guild.id,)
        ) as cursor:
            if await cursor.fetchone():
                await self.sync_guild_commands(guild)
                return await interaction.followup.send("❌ 您的伺服器已經部署過跨群聊天了！", ephemeral=True)

        # 3. 建立 `🛜-跨群聊天` 頻道
        try:
            channel = discord.utils.get(guild.text_channels, name="🛜-跨群聊天")
            if not channel:
                channel = await guild.create_text_channel(
                    name="🛜-跨群聊天",
                    topic="🛜 跨群聊天頻道 - 與其他伺服器連結通訊"
                )
        except discord.Forbidden:
            return await interaction.followup.send("❌ 機器人缺少「管理頻道」權限，無法建立 `🛜-跨群聊天` 頻道。", ephemeral=True)
        except Exception as e:
            return await interaction.followup.send(f"❌ 建立頻道時發生錯誤: {e}", ephemeral=True)

        # 4. 建立 Webhook
        try:
            webhook_url = await get_or_create_webhook(channel)
        except discord.Forbidden:
            return await interaction.followup.send("❌ 機器人缺少「管理 Webhook」權限，無法在頻道內建立 Webhook。", ephemeral=True)
        except Exception as e:
            return await interaction.followup.send(f"❌ 建立 Webhook 時發生錯誤: {e}", ephemeral=True)

        # 5. 產生唯一的隨機配對碼 (CG-XXXXXX)
        code = None
        while True:
            candidate = "CG-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            async with db.db.execute("SELECT guild_id FROM cross_guild_chat WHERE pairing_code = ?", (candidate,)) as cursor:
                if not await cursor.fetchone():
                    code = candidate
                    break

        # 6. 發送未配對狀態 Embed 訊息
        embed = discord.Embed(
            title="🛜 跨群聊天配對系統",
            description=(
                f"本伺服器的配對碼為：`{code}`\n\n"
                f"💡 **如何配對：**\n"
                f"1. 將您的配對碼發給別的伺服器，讓他們點擊下方「輸入配對碼」進行配對。\n"
                f"2. 或者點擊下方 **「輸入配對碼」**，輸入對方伺服器的配對碼。\n\n"
                f"⚠️ **注意：** 跨群聊天僅限 Ultra 伺服器使用。雙方都必須是已啟用的 Ultra 伺服器。"
            ),
            color=0x3498DB
        )
        pairing_message = await channel.send(embed=embed, view=CrossGuildUnpairedView())

        # 7. 寫入資料庫
        await db.db.execute(
            """INSERT INTO cross_guild_chat 
               (guild_id, channel_id, pairing_code, webhook_url, pairing_message_id) 
               VALUES (?, ?, ?, ?, ?)""",
            (guild.id, channel.id, code, webhook_url, pairing_message.id)
        )
        await db.db.commit()

        # 8. 同步指令樹（部署 -> 移除）
        await self.sync_guild_commands(guild)

        await interaction.followup.send(f"✅ 已成功為本伺服器部署跨群聊天！頻道已建立：{channel.mention}", ephemeral=True)

    @app_commands.command(name="移除跨群聊天", description="[Ultra 專屬] 移除跨群聊天設定並刪除頻道")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_cross_guild_chat(self, interaction: discord.Interaction):
        """移除跨群聊天指令回呼"""
        if not (interaction.user.guild_permissions.administrator or interaction.user.id == 1437408048934027274):
            return await interaction.response.send_message("❌ 您需要「管理員」權限才能執行此指令！", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        db = self.bot.db

        # 1. 取得部署狀態
        async with db.db.execute(
            "SELECT channel_id FROM cross_guild_chat WHERE guild_id = ?", (guild.id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                await self.sync_guild_commands(guild)
                return await interaction.followup.send("❌ 您的伺服器尚未部署跨群聊天！", ephemeral=True)
            channel_id = row[0]

        # 2. 取得所有連線並中斷
        async with db.db.execute(
            "SELECT connected_guild_id FROM cross_guild_connections WHERE guild_id = ?",
            (guild.id,)
        ) as cursor:
            connected_rows = await cursor.fetchall()
            connected_ids = [r[0] for r in connected_rows]

        for other_id in connected_ids:
            # 刪除雙向連線
            await db.db.execute(
                "DELETE FROM cross_guild_connections WHERE (guild_id = ? AND connected_guild_id = ?) OR (guild_id = ? AND connected_guild_id = ?)",
                (guild.id, other_id, other_id, guild.id)
            )
            # 通知對方
            other_guild = self.bot.get_guild(other_id)
            if other_guild:
                async with db.db.execute(
                    "SELECT channel_id FROM cross_guild_chat WHERE guild_id = ?",
                    (other_id,)
                ) as other_cursor:
                    other_chan_row = await other_cursor.fetchone()
                    if other_chan_row:
                        other_chan = other_guild.get_channel(other_chan_row[0])
                        if other_chan:
                            try:
                                await other_chan.send(f"⚠️ **對方伺服器 ({guild.name}) 已移除跨群聊天，連線已斷開。**")
                            except Exception:
                                pass
                await self.update_pairing_panel(other_id)

        # 3. 傳送成功回覆 (在刪除頻道前，避免頻道刪除導致 interaction 失效)
        try:
            await interaction.followup.send("✅ 已成功移除跨群聊天設定，並刪除頻道。", ephemeral=True)
        except Exception:
            pass

        # 4. 刪除與清理本地
        # 刪除頻道
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                await channel.delete()
            except Exception:
                pass

        # 刪除資料庫紀錄
        await db.db.execute("DELETE FROM cross_guild_chat WHERE guild_id = ?", (guild.id,))
        await db.db.execute("DELETE FROM cross_guild_connections WHERE guild_id = ? OR connected_guild_id = ?", (guild.id, guild.id))
        await db.db.execute("DELETE FROM cross_guild_invites WHERE guild_id = ? OR inviter_guild_id = ?", (guild.id, guild.id))
        await db.db.commit()

        # 同步指令
        await self.sync_guild_commands(guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(CrossGuildChat(bot))
