"""
休息模式系統 Cog
支援低耗電休息模式設定、請勿打擾 (DND) 狀態、自訂起訖時間、排程喚醒與自動檢測白名單
"""

import os
import sys
import json
import time
import re
import asyncio
from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Colors, BadgeImages

REST_CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "rest_mode.json")
BYPASS_USER_ID = 1437408048934027274


def parse_duration_or_time(args_str: str) -> tuple[datetime, datetime] | None:
    """
    解析使用者輸入的時間參數，支援：
    1. 相對時間: 30m, 2h, 1h30m, 90m, 1d, 45
    2. 單一結束時間: 07:00, 23:30 (開始時間為當前時間)
    3. 起訖時間: 22:00 06:00, 14:30 18:00
    4. 完整日期時間: 2026-08-31 18:00 2026-08-31 20:00
    """
    now = datetime.now()
    text = args_str.strip()
    if not text:
        return None

    # 1. 相對時長解析 (例如 30m, 2h, 1h30m, 1d, 45s)
    rel_pattern = r'^(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s)?$'
    rel_match = re.match(rel_pattern, text.lower())
    if rel_match and any(rel_match.groups()):
        days = int(rel_match.group(1) or 0)
        hours = int(rel_match.group(2) or 0)
        minutes = int(rel_match.group(3) or 0)
        seconds = int(rel_match.group(4) or 0)
        delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        if delta.total_seconds() > 0:
            return now, now + delta

    # 純數字預設為分鐘 (例如 45 -> 45 分鐘)
    if text.isdigit():
        minutes = int(text)
        if minutes > 0:
            return now, now + timedelta(minutes=minutes)

    # 2. 完整日期時間解析 (例如 2026-08-31 14:00 2026-08-31 18:00)
    full_dt_pattern = r'^(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2})\s+(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2})$'
    full_match = re.match(full_dt_pattern, text)
    if full_match:
        try:
            start_dt = datetime.strptime(full_match.group(1), "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(full_match.group(2), "%Y-%m-%d %H:%M")
            if end_dt > start_dt:
                return start_dt, end_dt
        except Exception:
            pass

    # 3. 雙時分範圍 (例如 22:00 06:00 或 14:00 18:00)
    two_times_pattern = r'^(\d{1,2}:\d{2})\s+(\d{1,2}:\d{2})$'
    two_match = re.match(two_times_pattern, text)
    if two_match:
        try:
            t1_str, t2_str = two_match.group(1), two_match.group(2)
            t1 = datetime.strptime(t1_str, "%H:%M").time()
            t2 = datetime.strptime(t2_str, "%H:%M").time()

            start_dt = datetime.combine(now.date(), t1)
            end_dt = datetime.combine(now.date(), t2)

            # 若結束時間小於等於開始時間，視為跨天至隔日
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)

            # 若開始時間與結束時間都在過去，整體往後移一天
            if end_dt < now:
                start_dt += timedelta(days=1)
                end_dt += timedelta(days=1)

            return start_dt, end_dt
        except Exception:
            pass

    # 4. 單一時分 (例如 07:00 -> 當前時間至下一個 07:00)
    one_time_pattern = r'^(\d{1,2}:\d{2})$'
    one_match = re.match(one_time_pattern, text)
    if one_match:
        try:
            t_str = one_match.group(1)
            t = datetime.strptime(t_str, "%H:%M").time()
            end_dt = datetime.combine(now.date(), t)
            # 若該時間今天已經過了，則設為明天的該時間
            if end_dt <= now:
                end_dt += timedelta(days=1)
            return now, end_dt
        except Exception:
            pass

    return None


class RestMode(commands.Cog):
    """倉鼠勇者 2.0 - 低耗電休息模式管理模組"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.is_resting = False
        self.bot.rest_info = {}
        self._load_rest_state()
        self.rest_checker_loop.start()

    def cog_unload(self):
        self.rest_checker_loop.cancel()

    def _load_rest_state(self):
        """載入儲存的休息狀態"""
        if os.path.exists(REST_CONFIG_FILE):
            try:
                with open(REST_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("enabled"):
                        end_time_str = data.get("end_time")
                        start_time_str = data.get("start_time")
                        if end_time_str:
                            end_dt = datetime.fromisoformat(end_time_str)
                            start_dt = datetime.fromisoformat(start_time_str) if start_time_str else datetime.now()
                            now = datetime.now()
                            if end_dt > now:
                                self.bot.rest_info = {
                                    "enabled": True,
                                    "start_time": start_dt,
                                    "end_time": end_dt,
                                    "start_time_str": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                                    "end_time_str": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                                    "reason": data.get("reason", "排程休息"),
                                    "initiated_by": data.get("initiated_by", "系統"),
                                }
                                if start_dt <= now:
                                    self.bot.is_resting = True
                                return
            except Exception as e:
                print(f"⚠️ 載入休息模式設定失敗: {e}")

        # 預設未開啟
        self.bot.is_resting = False
        self.bot.rest_info = {
            "enabled": False,
            "start_time": None,
            "end_time": None,
            "start_time_str": None,
            "end_time_str": None,
            "reason": None,
            "initiated_by": None,
        }

    def _save_rest_state(self):
        """儲存休息狀態至檔案"""
        try:
            os.makedirs(os.path.dirname(REST_CONFIG_FILE), exist_ok=True)
            info = getattr(self.bot, "rest_info", {})
            data = {
                "enabled": info.get("enabled", False),
                "start_time": info["start_time"].isoformat() if info.get("start_time") else None,
                "end_time": info["end_time"].isoformat() if info.get("end_time") else None,
                "reason": info.get("reason", "手動設定"),
                "initiated_by": info.get("initiated_by", "管理者"),
            }
            with open(REST_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 儲存休息模式設定失敗: {e}")

    async def _has_permission(self, user: discord.User | discord.Member) -> bool:
        """檢查是否有權限管理休息模式"""
        if user.id == BYPASS_USER_ID:
            return True
        if await self.bot.is_owner(user):
            return True
        if isinstance(user, discord.Member) and user.guild_permissions.administrator:
            return True
        return False

    async def start_rest(self, start_dt: datetime, end_dt: datetime, initiated_by: str, reason: str = "低耗電節能模式") -> bool:
        """啟動或排程休息模式"""
        now = datetime.now()
        is_immediate = (start_dt <= now)

        self.bot.rest_info = {
            "enabled": True,
            "start_time": start_dt,
            "end_time": end_dt,
            "start_time_str": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time_str": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "reason": reason,
            "initiated_by": initiated_by,
        }
        self._save_rest_state()

        if is_immediate:
            self.bot.is_resting = True
            try:
                time_display = end_dt.strftime("%H:%M")
                await self.bot.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.playing,
                        name=f"正在休息 (預計 {time_display} 喚醒)",
                    ),
                    status=discord.Status.dnd,
                )
            except Exception as e:
                print(f"⚠️ 設定休息狀態 Presence 失敗: {e}")
        else:
            self.bot.is_resting = False

        return True

    async def stop_rest(self, reason: str = "手動結束") -> bool:
        """解除休息模式，恢復正常狀態"""
        self.bot.is_resting = False
        self.bot.rest_info = {
            "enabled": False,
            "start_time": None,
            "end_time": None,
            "start_time_str": None,
            "end_time_str": None,
            "reason": None,
            "initiated_by": None,
        }
        self._save_rest_state()

        try:
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="伺服器 | .help",
                ),
                status=discord.Status.online,
            )
            if hasattr(self.bot, "status_event"):
                self.bot.status_event.set()
        except Exception as e:
            print(f"⚠️ 恢復正常狀態 Presence 失敗: {e}")

        return True

    @tasks.loop(seconds=10)
    async def rest_checker_loop(self):
        """背景定時檢查休息模式狀態與喚醒排程"""
        try:
            info = getattr(self.bot, "rest_info", {})
            if not info.get("enabled"):
                return

            now = datetime.now()
            start_dt = info.get("start_time")
            end_dt = info.get("end_time")

            # 1. 休息時間已過 -> 自動喚醒
            if end_dt and now >= end_dt:
                print(f"⏰ [RestMode] 休息時間已於 {end_dt.strftime('%H:%M:%S')} 結束，正在自動喚醒恢復正常運作...")
                await self.stop_rest(reason="休息時間結束自動喚醒")
                return

            # 2. 排程休息時間到達 -> 進入休息模式
            if start_dt and end_dt and (start_dt <= now < end_dt):
                if not getattr(self.bot, "is_resting", False):
                    print(f"💤 [RestMode] 排程休息時間已到達 ({start_dt.strftime('%H:%M:%S')} ~ {end_dt.strftime('%H:%M:%S')})，進入低耗電請勿打擾模式...")
                    self.bot.is_resting = True
                    time_display = end_dt.strftime("%H:%M")
                    await self.bot.change_presence(
                        activity=discord.Activity(
                            type=discord.ActivityType.playing,
                            name=f"正在休息 (預計 {time_display} 喚醒)",
                        ),
                        status=discord.Status.dnd,
                    )
        except Exception as e:
            print(f"⚠️ 休息檢查排程錯誤: {e}")

    @rest_checker_loop.before_loop
    async def before_rest_checker(self):
        await self.bot.wait_until_ready()

    def create_status_embed(self) -> discord.Embed:
        """產生休息模式當前狀態 Embed"""
        info = getattr(self.bot, "rest_info", {})
        is_resting = getattr(self.bot, "is_resting", False)
        is_enabled = info.get("enabled", False)

        embed = discord.Embed(
            title="🌙 機器人休息模式 (低耗電節能系統)",
            color=discord.Color.dark_purple() if is_resting else discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )

        if is_resting:
            now = datetime.now()
            end_dt = info.get("end_time")
            remaining = (end_dt - now) if end_dt else timedelta()
            rem_str = ""
            if remaining.total_seconds() > 0:
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                parts = []
                if hours > 0:
                    parts.append(f"{hours} 小時")
                if minutes > 0:
                    parts.append(f"{minutes} 分鐘")
                if seconds > 0 or not parts:
                    parts.append(f"{seconds} 秒")
                rem_str = " (剩餘 " + "".join(parts) + ")"

            embed.description = "💤 **目前狀態：正在休息中 (低耗電請勿打擾模式)**"
            embed.add_field(name="⏰ 開始時間", value=f"`{info.get('start_time_str', '即刻')}`", inline=True)
            embed.add_field(name="⏳ 結束/喚醒時間", value=f"`{info.get('end_time_str', '未指定')}`{rem_str}", inline=True)
            embed.add_field(name="👤 設定者", value=f"`{info.get('initiated_by', '系統')}`", inline=True)
            embed.add_field(
                name="🛡️ 運作規則 (白名單機制)",
                value=(
                    "• ❌ **前綴指令**：暫停使用（降低伺服器負載）\n"
                    "• ✅ **斜線指令 (`/`)**：全面維持正常可用\n"
                    "• ✅ **自動檢測系統**：地震天災速報、雙主機協調、安全防禦持續全天候運行"
                ),
                inline=False
            )
        elif is_enabled and info.get("start_time") and info["start_time"] > datetime.now():
            embed.description = "🕒 **目前狀態：已排程休息模式 (等待時間到達)**"
            embed.add_field(name="⏰ 排程開始時間", value=f"`{info.get('start_time_str')}`", inline=True)
            embed.add_field(name="⏳ 排程結束時間", value=f"`{info.get('end_time_str')}`", inline=True)
            embed.add_field(name="👤 設定者", value=f"`{info.get('initiated_by', '系統')}`", inline=True)
        else:
            embed.description = "🟢 **目前狀態：全功能正常運作中 (未處於休息狀態)**"
            embed.add_field(
                name="💡 如何設定休息模式？",
                value=(
                    "• `.rest 30m` — 休息 30 分鐘後自動喚醒\n"
                    "• `.rest 2h` — 休息 2 小時後自動喚醒\n"
                    "• `.rest 23:00 07:00` — 設定今晚 23:00 休息至明晨 07:00\n"
                    "• `.rest 07:00` — 從現在休息至 07:00\n"
                    "• `.rest off` — 立即解除休息模式並恢復上線"
                ),
                inline=False
            )

        embed.set_footer(text="勇者 2.0 高可用系統 ｜ 低耗電節能與容災協同")
        if hasattr(BadgeImages, "INFO"):
            embed.set_thumbnail(url=BadgeImages.INFO)
        return embed

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 前綴指令 (.rest / .休息 / .sleep / .低耗電)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @commands.command(name="rest", aliases=["休息", "sleep", "低耗電", "restmode"])
    async def rest_prefix_command(self, ctx: commands.Context, *, args: str = ""):
        """設定或查詢機器人休息模式 (.rest <時長/起訖時間/off>)"""
        arg_clean = args.strip().lower()

        # 1. 查詢狀態 (無參數或 status / info / 狀態 / 查詢)
        if not arg_clean or arg_clean in {"status", "info", "狀態", "查詢"}:
            embed = self.create_status_embed()
            return await ctx.send(embed=embed)

        # 2. 權限檢查
        if not await self._has_permission(ctx.author):
            return await ctx.send("❌ 你沒有權限設定或更改機器人休息模式！", delete_after=5)

        # 3. 結束/關閉休息模式
        if arg_clean in {"off", "stop", "cancel", "0", "結束", "關閉", "醒來", "停止"}:
            await self.stop_rest(reason=f"由 {ctx.author.name} 手動解除")
            embed = discord.Embed(
                title="☀️ 休息模式已解除",
                description="機器人已成功退出休息模式！狀態已恢復為 `在線 (Online)`，所有前綴指令與子功能已重新全面啟用。",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text="勇者 2.0 系統已恢復滿載運作")
            return await ctx.send(embed=embed)

        # 4. 解析時間參數
        time_result = parse_duration_or_time(args)
        if not time_result:
            embed = discord.Embed(
                title="❌ 參數格式錯誤",
                description=(
                    "無法辨識您輸入的休息時間格式！請參考以下範例：\n\n"
                    "• **相對時間**：`.rest 30m`、`.rest 2h`、`.rest 1h30m`\n"
                    "• **指定時段**：`.rest 23:00 07:00` (晚上11點至隔日早上7點)\n"
                    "• **指定結束時間**：`.rest 07:00` (即刻起休息至7點)\n"
                    "• **解除休息**：`.rest off`"
                ),
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        start_dt, end_dt = time_result
        now = datetime.now()

        if end_dt <= now:
            return await ctx.send("❌ 結束時間必須晚於當前時間！")

        await self.start_rest(
            start_dt=start_dt,
            end_dt=end_dt,
            initiated_by=f"{ctx.author.name} ({ctx.author.id})",
            reason="管理者指令排程"
        )

        is_immediate = (start_dt <= now)
        embed = discord.Embed(
            title="🌙 休息模式設定成功",
            description=(
                f"{'💤 **機器人已立即進入休息模式 (請勿打擾)**' if is_immediate else '🕒 **已成功排程休息模式**'}\n\n"
                f"⏰ **開始時間:** `{start_dt.strftime('%Y-%m-%d %H:%M:%S')}`\n"
                f"⏳ **結束時間:** `{end_dt.strftime('%Y-%m-%d %H:%M:%S')}` (預計此時自動喚醒)\n\n"
                f"💡 **運作提示:**\n"
                f"• 休息期間前綴指令已暫停使用以降低負載。\n"
                f"• **斜線指令 (`/`)** 與 **天災地震監控/自動安全防護** 仍保持 24 小時正常運作！\n"
                f"• 若需提前解除，請輸入 `.rest off`。"
            ),
            color=discord.Color.purple(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"設定者: {ctx.author.name}")
        await ctx.send(embed=embed)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 斜線指令 (/rest)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.command(name="rest", description="🌙 設定或查詢機器人低耗電休息模式")
    @app_commands.describe(
        action="動作選項 (查詢狀態 / 啟動休息 / 解除休息)",
        time_setting="設定時長或起訖時間 (例如: 30m, 2h, 23:00 07:00, 07:00)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="📊 查詢當前狀態", value="status"),
        app_commands.Choice(name="💤 啟動/設定休息模式", value="start"),
        app_commands.Choice(name="☀️ 解除/結束休息模式", value="stop"),
    ])
    async def rest_slash_command(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        time_setting: str = ""
    ):
        if action.value == "status":
            embed = self.create_status_embed()
            return await interaction.response.send_message(embed=embed)

        if not await self._has_permission(interaction.user):
            return await interaction.response.send_message("❌ 你沒有權限設定或更改機器人休息模式！", ephemeral=True)

        if action.value == "stop":
            await self.stop_rest(reason=f"由 {interaction.user.name} 手動解除")
            embed = discord.Embed(
                title="☀️ 休息模式已解除",
                description="機器人已成功退出休息模式！狀態已恢復為 `在線 (Online)`，所有功能已重新全面啟用。",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            return await interaction.response.send_message(embed=embed)

        if action.value == "start":
            if not time_setting.strip():
                return await interaction.response.send_message(
                    "❌ 請在 `time_setting` 欄位填寫休息時長或起訖時間！例如：`30m`、`2h` 或 `23:00 07:00`。",
                    ephemeral=True
                )

            time_result = parse_duration_or_time(time_setting)
            if not time_result:
                return await interaction.response.send_message(
                    "❌ 無法解析時間格式！範例：`30m` (30分鐘)、`2h` (2小時)、`23:00 07:00` (指定時段)。",
                    ephemeral=True
                )

            start_dt, end_dt = time_result
            now = datetime.now()
            if end_dt <= now:
                return await interaction.response.send_message("❌ 結束時間必須晚於當前時間！", ephemeral=True)

            await self.start_rest(
                start_dt=start_dt,
                end_dt=end_dt,
                initiated_by=f"{interaction.user.name} ({interaction.user.id})",
                reason="Slash 指令排程"
            )

            is_immediate = (start_dt <= now)
            embed = discord.Embed(
                title="🌙 休息模式設定成功",
                description=(
                    f"{'💤 **機器人已立即進入休息模式 (請勿打擾)**' if is_immediate else '🕒 **已成功排程休息模式**'}\n\n"
                    f"⏰ **開始時間:** `{start_dt.strftime('%Y-%m-%d %H:%M:%S')}`\n"
                    f"⏳ **結束時間:** `{end_dt.strftime('%Y-%m-%d %H:%M:%S')}` (預計此時自動喚醒)\n\n"
                    f"💡 **運作提示:**\n"
                    f"• 休息期間前綴指令暫停使用以降低負載。\n"
                    f"• **斜線指令 (`/`)** 與 **天災地震監控/自動安全防護** 仍保持 24 小時正常運作！\n"
                    f"• 若需提前解除，請使用 `/rest action:解除/結束休息模式` 或 `.rest off`。"
                ),
                color=discord.Color.purple(),
                timestamp=discord.utils.utcnow()
            )
            return await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(RestMode(bot))
