import os
import sys
import json
import time
import asyncio
import discord
from discord.ext import commands, tasks

# 全域權限繞過 ID
BYPASS_USER_ID = 1437408048934027274

class CoordinationView(discord.ui.View):
    """總控 Embed 下方的互動按鈕"""
    
    def __init__(self, cog):
        super().__init__(timeout=None) # 永不超時的持久 View
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """限制只有繞過 ID 或是 Bot 擁有者才能操作按鈕"""
        is_owner = await self.cog.bot.is_owner(interaction.user)
        if interaction.user.id == BYPASS_USER_ID or is_owner:
            return True
        await interaction.response.send_message("❌ 您沒有權限操作總控中心！", ephemeral=True)
        return False

    @discord.ui.button(label="強制 1 號 Active", style=discord.ButtonStyle.primary, custom_id="force_wisp1")
    async def force_wisp1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_control_action(interaction, "force", "wispbyte-1")

    @discord.ui.button(label="強制 2 號 Active", style=discord.ButtonStyle.primary, custom_id="force_wisp2")
    async def force_wisp2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_control_action(interaction, "force", "wispbyte-2")

    @discord.ui.button(label="自動調度模式", style=discord.ButtonStyle.success, custom_id="release_lock")
    async def release_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_control_action(interaction, "unlock", "")

    @discord.ui.button(label="重啟 1 號", style=discord.ButtonStyle.danger, custom_id="restart_wisp1")
    async def restart_wisp1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_control_action(interaction, "restart", "wispbyte-1")

    @discord.ui.button(label="重啟 2 號", style=discord.ButtonStyle.danger, custom_id="restart_wisp2")
    async def restart_wisp2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_control_action(interaction, "restart", "wispbyte-2")

    @discord.ui.button(label="同步 1 號 (Pull)", style=discord.ButtonStyle.secondary, custom_id="sync_wisp1")
    async def sync_wisp1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_control_action(interaction, "sync", "wispbyte-1")

    @discord.ui.button(label="同步 2 號 (Pull)", style=discord.ButtonStyle.secondary, custom_id="sync_wisp2")
    async def sync_wisp2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_control_action(interaction, "sync", "wispbyte-2")


class DiscordControl(commands.Cog):
    """Discord 內建多主機總控與協調系統"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.server_id = os.getenv("SERVER_ID")
        channel_id_str = os.getenv("COORDINATION_CHANNEL_ID")
        self.channel_id = int(channel_id_str) if channel_id_str and channel_id_str.isdigit() else None
        
        # 預設狀態
        self.bot.is_active_node = True
        
        # 如果有設定 COORDINATION_CHANNEL_ID，才啟動主備控制
        if self.server_id and self.channel_id:
            # 預設為備用，直到心跳確認
            self.bot.is_active_node = False
            self.last_seen_counters = {}
            self.counter_miss_ticks = {}
            self.coordination_loop.start()
            print(f"📡 已載入主備協調模組。當前主機: {self.server_id}，協調頻道: {self.channel_id}")
        else:
            print("ℹ️ 未設定 SERVER_ID 或 COORDINATION_CHANNEL_ID，已略過主備控制 (將維持單機運作)")

    def cog_unload(self):
        self.coordination_loop.cancel()

    async def get_coordination_message(self, channel: discord.TextChannel) -> discord.Message | None:
        """尋找或建立總控面板訊息"""
        # 1. 優先從釘選訊息中尋找
        try:
            pins = await channel.pins()
            for message in pins:
                if message.author.id == self.bot.user.id and message.embeds:
                    embed = message.embeds[0]
                    if embed.title == "🤖 倉鼠勇者 2.0 總控中心":
                        return message
        except Exception:
            pass

        # 2. 若釘選訊息中沒有，再搜尋最近 100 條訊息
        try:
            async for message in channel.history(limit=100):
                if message.author.id == self.bot.user.id and message.embeds:
                    embed = message.embeds[0]
                    if embed.title == "🤖 倉鼠勇者 2.0 總控中心":
                        return message
        except Exception:
            pass
        return None

    async def handle_control_action(self, interaction: discord.Interaction, action: str, target: str):
        """處理按鈕點擊互動"""
        await interaction.response.defer(ephemeral=True)
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            return await interaction.followup.send("❌ 找不到協調頻道！", ephemeral=True)
            
        message = await self.get_coordination_message(channel)
        if not message:
            return await interaction.followup.send("❌ 找不到總控面板訊息！", ephemeral=True)

        # 解析當前狀態
        data = self.parse_footer_data(message)
        
        if action == "force":
            data["locked"] = target
            data["active"] = target
            msg_text = f"已手動強制指定 `{target}` 為 Active 運作主機。"
        elif action == "unlock":
            data["locked"] = ""
            msg_text = "已解除手動鎖定，回復自動故障轉移模式。"
        elif action == "restart":
            data["restarting_pending"] = target
            msg_text = f"已向 `{target}` 發送安全重啟要求，主機在下次心跳時會執行重新啟動。"
        elif action == "sync":
            data["sync_pending"] = target
            msg_text = f"已向 `{target}` 發送程式碼同步要求，主機在下次心跳時會從 GitHub 拉取並安全重啟。"

        # 編輯更新 Embed
        new_embed = self.build_embed(data)
        await message.edit(embed=new_embed)
        await interaction.followup.send(f"✅ 操作成功：{msg_text}", ephemeral=True)

    def parse_footer_data(self, message: discord.Message) -> dict:
        """解析 Embed Footer 裡儲存的 JSON 狀態資料"""
        default_data = {
            "active": "",
            "locked": "",
            "restarting_pending": "",
            "sync_pending": "",
            "heartbeats": {},
            "counters": {}
        }
        
        if not message.embeds or not message.embeds[0].footer or not message.embeds[0].footer.text:
            return default_data
            
        footer_text = message.embeds[0].footer.text
        if not footer_text.startswith("COORDINATION_DATA:"):
            return default_data
            
        try:
            json_str = footer_text.replace("COORDINATION_DATA:", "", 1)
            parsed = json.loads(json_str)
            for k, v in default_data.items():
                if k not in parsed:
                    parsed[k] = v
            return parsed
        except Exception:
            return default_data

    def build_embed(self, data: dict) -> discord.Embed:
        """根據狀態資料建立總控 Embed 畫面"""
        active_server = data.get("active", "無")
        locked_server = data.get("locked", "")
        mode_text = f"🔒 手動鎖定於 `{locked_server}`" if locked_server else "🔄 自動容災調度中"
        
        embed = discord.Embed(
            title="🤖 倉鼠勇者 2.0 總控中心",
            description=(
                f"**目前主備模式**：{mode_text}\n"
                f"**當前運作中主機 (Active)**：🏆 `{active_server}`\n"
                "────────────────────────"
            ),
            color=discord.Color.dark_theme()
        )
        
        # 列出所有主機狀態
        now = int(time.time())
        heartbeats = data.get("heartbeats", {})
        
        # 確保 wispbyte-1 & wispbyte-2 都會顯示
        all_monitored = sorted(list(set(["wispbyte-1", "wispbyte-2"] + list(heartbeats.keys()))))
        
        for sid in all_monitored:
            last_seen = heartbeats.get(sid, 0)
            if hasattr(self, "counter_miss_ticks") and sid in self.counter_miss_ticks:
                is_online = self.counter_miss_ticks.get(sid, 0) < 3
            else:
                is_online = (now - last_seen < 35) if last_seen > 0 else False
            is_active = (sid == active_server)
            
            if is_online:
                status_emoji = "🟢" if is_active else "🟡"
                if data.get("restarting_pending") == sid:
                    status_text = "🔄 重啟指令發送中..."
                elif data.get("sync_pending") == sid:
                    status_text = "📥 同步指令發送中..."
                else:
                    status_text = "ACTIVE (運作中)" if is_active else "IDLE (靜默備用)"
                time_str = f"<t:{int(last_seen)}:R>"
            else:
                status_emoji = "🔴"
                status_text = "OFFLINE (已中斷)"
                time_str = "無心跳回報"
                
            embed.add_field(
                name=f"{status_emoji} {sid}",
                value=f"**狀態**：`{status_text}`\n**最後心跳**：{time_str}",
                inline=True
            )
            
        embed.set_footer(text=f"COORDINATION_DATA:{json.dumps(data)}")
        return embed

    @tasks.loop(seconds=15)
    async def coordination_loop(self):
        """主要主備控制與心跳定時任務"""
        await self.bot.wait_until_ready()
        
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            print(f"❌ 總控協調失敗：找不到頻道 ID {self.channel_id}")
            return
            
        try:
            # 1. 取得總控訊息
            message = await self.get_coordination_message(channel)
            view = CoordinationView(self)
            
            if not message:
                # 建立新訊息
                initial_data = {
                    "active": self.server_id,
                    "locked": "",
                    "restarting_pending": "",
                    "sync_pending": "",
                    "heartbeats": {self.server_id: time.time()},
                    "counters": {self.server_id: 1}
                }
                embed = self.build_embed(initial_data)
                message = await channel.send(embed=embed, view=view)
                try:
                    await message.pin()
                except Exception:
                    pass
                # 註冊 view 監聽器
                self.bot.add_view(view)
                data = initial_data
            else:
                # 註冊 view 監聽器，確保重啟後按鈕仍有用
                self.bot.add_view(view)
                # 解析現有狀態
                data = self.parse_footer_data(message)

            # 2. 更新自己這台主機的心跳時間與計數器
            now_time = time.time()
            if "heartbeats" not in data:
                data["heartbeats"] = {}
            data["heartbeats"][self.server_id] = now_time

            if "counters" not in data:
                data["counters"] = {}
            data["counters"][self.server_id] = data["counters"].get(self.server_id, 0) + 1

            # 3. 處理強制重啟指令
            if data.get("restarting_pending") == self.server_id:
                print("🔄 接收到總控重啟要求，正在執行安全重啟流程...")
                # 清除重啟請求，避免重啟後一直卡在重啟循環
                data["restarting_pending"] = ""
                new_embed = self.build_embed(data)
                await message.edit(embed=new_embed)
                
                # 設定狀態為請勿打擾與正在重新啟動的活動，並等待狀態更新
                try:
                    await self.bot.change_presence(
                        status=discord.Status.dnd,
                        activity=discord.Game("正在重新啟動...")
                    )
                    await asyncio.sleep(1.5)
                except Exception:
                    pass
                
                # 執行重啟
                self.bot.is_restarting = True
                self.bot.exit_code = 1
                await self.bot.close()
                return

            # 3.5. 處理強制同步更新指令
            if data.get("sync_pending") == self.server_id:
                print("🔄 接收到總控同步要求，正在執行從 GitHub 更新流程...")
                # 清除同步請求，避免重啟後一直卡在更新循環
                data["sync_pending"] = ""
                new_embed = self.build_embed(data)
                await message.edit(embed=new_embed)
                
                # 取得 AutoUpdate Cog 並調用核心更新流程
                auto_update_cog = self.bot.get_cog("AutoUpdate")
                if auto_update_cog:
                    async def update_status(text: str):
                        print(f"[Panel Sync Update] {text}")
                    # 在背景安全執行同步覆蓋與重啟
                    asyncio.create_task(auto_update_cog.run_update_process(update_status))
                    return

            # 4. 主備故障轉移邏輯
            if "counters" not in data:
                data["counters"] = {}

            active_nodes = []
            for sid, ltime in list(data["heartbeats"].items()):
                counter = data["counters"].get(sid, 0)
                
                # 混合時間差與計數器變化判斷在線狀態
                is_timestamp_recent = (now_time - ltime < 120) if ltime > 0 else False
                if not is_timestamp_recent:
                    self.counter_miss_ticks[sid] = 3
                else:
                    if sid not in self.last_seen_counters:
                        self.last_seen_counters[sid] = counter
                        self.counter_miss_ticks[sid] = 0
                    elif counter > self.last_seen_counters[sid]:
                        self.last_seen_counters[sid] = counter
                        self.counter_miss_ticks[sid] = 0
                    else:
                        self.counter_miss_ticks[sid] = self.counter_miss_ticks.get(sid, 0) + 1

                if self.counter_miss_ticks.get(sid, 0) < 3:
                    active_nodes.append(sid)

            locked_server = data.get("locked", "")
            current_active = data.get("active", "")

            if locked_server:
                # 手動鎖定模式：以手動指定優先，即使離線也維持設定（由管理員操作）
                data["active"] = locked_server
            else:
                # 自動調度模式：如果當前 active 離線，或者根本還沒有 active
                if not current_active or current_active not in active_nodes:
                    if active_nodes:
                        # 排序選擇優先權最高者
                        active_nodes.sort()
                        new_active = active_nodes[0]
                        data["active"] = new_active
                        
                        # ⚠️ 觸發自動故障轉移警報：原本有 active，但該 active 離線了，因而更換 active 主機
                        if current_active and current_active != new_active:
                            try:
                                alert_msg = (
                                    f"⚠️ **【緊急警報】主機 `{current_active}` 發生故障離線！**\n"
                                    f"🔄 系統已自動將服務轉移至備用主機 `{new_active}`。\n"
                                    f"🔔 請管理員 <@1437408048934027274> 儘速檢查 Wispbyte 主機狀態！"
                                )
                                await channel.send(alert_msg)
                            except Exception as alert_err:
                                print(f"❌ 發送緊急警報失敗: {alert_err}")
                    else:
                        data["active"] = ""

            # 5. 判斷自己是 Active 還是 Idle，並設定全域狀態
            final_active = data.get("active")
            if final_active == self.server_id:
                if not self.bot.is_active_node:
                    print("🏆 本機已被指派為 Active，開始響應 Discord 指令！")
                self.bot.is_active_node = True
            else:
                if self.bot.is_active_node:
                    print("💤 本機已退役為 Idle，進入靜默待命狀態...")
                self.bot.is_active_node = False

            # 6. 更新並儲存回 Discord
            new_embed = self.build_embed(data)
            await message.edit(embed=new_embed)

        except Exception as e:
            print(f"❌ 總控協調迴圈錯誤: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(DiscordControl(bot))
