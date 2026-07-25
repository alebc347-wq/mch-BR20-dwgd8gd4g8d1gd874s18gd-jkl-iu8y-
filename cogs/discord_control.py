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
            self.coordination_loop.start()
            print(f"📡 已載入主備協調模組。當前主機: {self.server_id}，協調頻道: {self.channel_id}")
        else:
            print("ℹ️ 未設定 SERVER_ID 或 COORDINATION_CHANNEL_ID，已略過主備控制 (將維持單機運作)")

    def cog_unload(self):
        self.coordination_loop.cancel()

    async def get_coordination_message(self, channel: discord.TextChannel) -> discord.Message | None:
        """尋找或建立總控面板訊息"""
        # 搜尋最近 50 條訊息，看有沒有由自己發送且帶有標題的訊息
        async for message in channel.history(limit=50):
            if message.author.id == self.bot.user.id and message.embeds:
                embed = message.embeds[0]
                if embed.title == "🤖 倉鼠勇者 2.0 總控中心":
                    return message
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
            "heartbeats": {}
        }
        
        if not message.embeds or not message.embeds[0].footer or not message.embeds[0].footer.text:
            return default_data
            
        footer_text = message.embeds[0].footer.text
        if not footer_text.startswith("COORDINATION_DATA:"):
            return default_data
            
        try:
            json_str = footer_text.replace("COORDINATION_DATA:", "", 1)
            return json.loads(json_str)
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
            is_online = (now - last_seen < 35) if last_seen > 0 else False
            is_active = (sid == active_server)
            
            if is_online:
                status_emoji = "🟢" if is_active else "🟡"
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
                    "heartbeats": {self.server_id: time.time()}
                }
                embed = self.build_embed(initial_data)
                message = await channel.send(embed=embed, view=view)
                # 註冊 view 監聽器
                self.bot.add_view(view)
                data = initial_data
            else:
                # 註冊 view 監聽器，確保重啟後按鈕仍有用
                self.bot.add_view(view)
                # 解析現有狀態
                data = self.parse_footer_data(message)

            # 2. 更新自己這台主機的心跳時間
            now_time = time.time()
            if "heartbeats" not in data:
                data["heartbeats"] = {}
            data["heartbeats"][self.server_id] = now_time

            # 3. 處理強制重啟指令
            if data.get("restarting_pending") == self.server_id:
                print("🔄 接收到總控重啟要求，正在執行安全重啟流程...")
                # 清除重啟請求，避免重啟後一直卡在重啟循環
                data["restarting_pending"] = ""
                new_embed = self.build_embed(data)
                await message.edit(embed=new_embed)
                
                # 執行重啟
                self.bot.is_restarting = True
                self.bot.exit_code = 1
                await self.bot.close()
                return

            # 4. 主備故障轉移邏輯
            # 計算哪些節點是在線的 (心跳在 35 秒內)
            active_nodes = [
                sid for sid, ltime in data["heartbeats"].items()
                if now_time - ltime < 35
            ]

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
                        data["active"] = active_nodes[0]
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
            # 如果心跳失敗，為防全部 Bot 停擺，自動將自己設為 Active 防中斷
            self.bot.is_active_node = True


async def setup(bot: commands.Bot):
    await bot.add_cog(DiscordControl(bot))
