"""
經濟系統 Cog
金幣餘額、每日簽到、轉帳、排行榜、打工
使用 aiosqlite 資料庫存儲
"""

import discord
from discord import app_commands
from discord.ext import commands
import random
from datetime import datetime, timezone, timedelta
import os
import json

from config import Colors
from utils.embeds import EmbedFactory


class Economy(commands.GroupCog, name="economy", description="💰 經濟與金幣系統"):
    """經濟系統 — 金幣、簽到、轉帳、排行榜"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._work_cooldowns: dict[int, datetime] = {}

    async def cog_load(self):
        """Cog 載入時建立經濟表"""
        await self.bot.db.db.executescript("""
            CREATE TABLE IF NOT EXISTS economy (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                balance INTEGER DEFAULT 0,
                last_daily TEXT DEFAULT '',
                PRIMARY KEY (user_id, guild_id)
            );
        """)
        await self.bot.db.db.commit()

    async def _get_balance(self, user_id: int, guild_id: int) -> int:
        async with self.bot.db.db.execute(
            "SELECT balance FROM economy WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def _update_balance(self, user_id: int, guild_id: int, amount: int):
        await self.bot.db.db.execute(
            """INSERT INTO economy (user_id, guild_id, balance)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, guild_id)
               DO UPDATE SET balance = balance + ?""",
            (user_id, guild_id, max(0, amount), amount),
        )
        await self.bot.db.db.commit()

    async def _set_balance(self, user_id: int, guild_id: int, amount: int):
        await self.bot.db.db.execute(
            """INSERT INTO economy (user_id, guild_id, balance)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, guild_id)
               DO UPDATE SET balance = ?""",
            (user_id, guild_id, amount, amount),
        )
        await self.bot.db.db.commit()

    async def _get_last_daily(self, user_id: int, guild_id: int) -> str:
        async with self.bot.db.db.execute(
            "SELECT last_daily FROM economy WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else ""

    async def _set_last_daily(self, user_id: int, guild_id: int, date_str: str):
        await self.bot.db.db.execute(
            """INSERT INTO economy (user_id, guild_id, last_daily)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, guild_id)
               DO UPDATE SET last_daily = ?""",
            (user_id, guild_id, date_str, date_str),
        )
        await self.bot.db.db.commit()

    # ── 查看餘額 ──
    @app_commands.command(name="balance", description="💰 查看你的金幣餘額")
    @app_commands.describe(member="要查看的成員（可選）")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        bal = await self._get_balance(target.id, interaction.guild_id)

        embed = discord.Embed(
            title="💰 金幣餘額",
            description=f"{target.mention} 目前擁有 **{bal:,}** 🪙 金幣",
            color=Colors.GAME,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    # ── 每日簽到 ──
    @app_commands.command(name="daily", description="📅 每日簽到領取金幣")
    async def daily(self, interaction: discord.Interaction):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        last = await self._get_last_daily(interaction.user.id, interaction.guild_id)

        if last == today:
            embed = discord.Embed(
                title="📅 已簽到",
                description="你今天已經簽到過了！請明天再來吧 ✨",
                color=Colors.WARNING,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        reward = random.randint(50, 200)
        await self._update_balance(interaction.user.id, interaction.guild_id, reward)
        await self._set_last_daily(interaction.user.id, interaction.guild_id, today)

        bal = await self._get_balance(interaction.user.id, interaction.guild_id)
        embed = discord.Embed(
            title="📅 每日簽到成功！",
            description=f"🎉 你獲得了 **{reward}** 🪙 金幣！\n💰 目前餘額：**{bal:,}** 🪙",
            color=Colors.SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    async def _transfer(self, sender_id: int, receiver_id: int, guild_id: int, amount: int) -> bool:
        """原子化扣款轉帳，防範雙重支付競態條件"""
        if amount <= 0:
            return False
        cursor = await self.bot.db.db.execute(
            "UPDATE economy SET balance = balance - ? WHERE user_id = ? AND guild_id = ? AND balance >= ?",
            (amount, sender_id, guild_id, amount)
        )
        if cursor.rowcount == 0:
            return False
        await self._update_balance(receiver_id, guild_id, amount)
        await self.bot.db.db.commit()
        return True

    # ── 轉帳 ──
    @app_commands.command(name="pay", description="💸 轉帳金幣給其他成員")
    @app_commands.describe(member="要轉帳的對象", amount="金額")
    async def pay(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if member.id == interaction.user.id:
            return await interaction.response.send_message("❌ 你不能轉帳給自己！", ephemeral=True)
        if member.bot:
            return await interaction.response.send_message("❌ 你不能轉帳給機器人！", ephemeral=True)
        if amount <= 0:
            return await interaction.response.send_message("❌ 金額必須大於 0！", ephemeral=True)

        success = await self._transfer(interaction.user.id, member.id, interaction.guild_id, amount)
        if not success:
            bal = await self._get_balance(interaction.user.id, interaction.guild_id)
            return await interaction.response.send_message(
                f"❌ 你的金幣不足或轉帳失敗！目前餘額：**{bal:,}** 🪙", ephemeral=True
            )

        embed = discord.Embed(
            title="💸 轉帳成功",
            description=f"{interaction.user.mention} ➜ {member.mention}\n金額：**{amount:,}** 🪙",
            color=Colors.SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    # ── 排行榜 ──
    @app_commands.command(name="leaderboard", description="🏆 金幣排行榜")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        async with self.bot.db.db.execute(
            "SELECT user_id, balance FROM economy WHERE guild_id = ? ORDER BY balance DESC LIMIT 10",
            (interaction.guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return await interaction.followup.send(
                embed=discord.Embed(title="🏆 排行榜", description="還沒有人有金幣！", color=Colors.WARNING)
            )

        embed = discord.Embed(title="🏆 金幣排行榜 — Top 10", color=Colors.GAME)

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, row in enumerate(rows):
            user = interaction.guild.get_member(row[0])
            name = user.display_name if user else f"Unknown ({row[0]})"
            medal = medals[i] if i < 3 else f"`{i + 1}.`"
            lines.append(f"{medal} **{name}** — {row[1]:,} 🪙")

        embed.description = "\n".join(lines)
        await interaction.followup.send(embed=embed)

    # ── 打工 ──
    @app_commands.command(name="work", description="🔨 打工賺取金幣（冷卻 30 分鐘）")
    async def work(self, interaction: discord.Interaction):
        now = datetime.now(timezone.utc)
        last_work = self._work_cooldowns.get(interaction.user.id)

        if last_work and (now - last_work) < timedelta(minutes=30):
            remaining = timedelta(minutes=30) - (now - last_work)
            mins = int(remaining.total_seconds() // 60)
            secs = int(remaining.total_seconds() % 60)
            return await interaction.response.send_message(
                f"⏳ 你需要休息一下！再等 **{mins}** 分 **{secs}** 秒才能繼續打工。",
                ephemeral=True,
            )

        jobs = [
            ("👨‍🍳 廚師", "在餐廳裡煮了一桌好菜"),
            ("🧹 清潔工", "把整個辦公室打掃得乾乾淨淨"),
            ("📦 快遞員", "送了 50 個包裹"),
            ("🎨 畫家", "畫了一幅超棒的風景畫"),
            ("🖥️ 程式設計師", "修了 100 個 Bug"),
            ("🎤 歌手", "在街頭唱了一場表演"),
            ("🐕 遛狗員", "帶了 5 隻狗去公園散步"),
            ("📚 圖書管理員", "整理了 200 本書"),
            ("🚗 司機", "開了 100 公里的車"),
            ("🎮 遊戲測試員", "測試了新遊戲 5 小時"),
        ]

        job, desc = random.choice(jobs)
        earnings = random.randint(30, 150)
        await self._update_balance(interaction.user.id, interaction.guild_id, earnings)
        self._work_cooldowns[interaction.user.id] = now

        bal = await self._get_balance(interaction.user.id, interaction.guild_id)
        embed = discord.Embed(
            title=f"🔨 打工 — {job}",
            description=f"{desc}，賺取了 **{earnings}** 🪙 金幣！\n💰 目前餘額：**{bal:,}** 🪙",
            color=Colors.SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # REDEEM CODES — 兌換碼系統
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    CODES_FILE = os.path.join("data", "redeem_codes.json")
    ALLOWED_ADMINS = [1070737811474493511, 1355788320151703653]

    def _load_codes(self) -> dict:
        os.makedirs("data", exist_ok=True)
        if not os.path.exists(self.CODES_FILE):
            with open(self.CODES_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f)
        try:
            with open(self.CODES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_codes(self, codes: dict):
        with open(self.CODES_FILE, "w", encoding="utf-8") as f:
            json.dump(codes, f, indent=4, ensure_ascii=False)

    @app_commands.command(name="redeem_code", description="兌換一個兌換碼領取獎勵")
    @app_commands.describe(code="請輸入兌換碼")
    async def redeem_code(self, interaction: discord.Interaction, code: str):
        codes = self._load_codes()
        code = code.strip()

        if code not in codes:
            return await interaction.response.send_message("❌ 無效的兌換碼！", ephemeral=True)

        if codes[code]["used"]:
            return await interaction.response.send_message("⚠️ 這個兌換碼已經被使用過了！", ephemeral=True)

        reward = codes[code]["reward"]
        
        # 標記為已使用
        codes[code]["used"] = True
        self._save_codes(codes)

        # 整合進新版經濟系統中
        # 檢查 reward 是否是純數字，如果是，直接加金幣
        if reward.isdigit():
            coins = int(reward)
            await self._update_balance(interaction.user.id, interaction.guild_id, coins)
            new_bal = await self._get_balance(interaction.user.id, interaction.guild_id)
            embed = EmbedFactory.success(
                "兌換成功 🎉",
                f"你獲得了 **{coins}** 🪙 金幣！\n💰 目前餘額：**{new_bal:,}** 🪙"
            )
        else:
            embed = EmbedFactory.success(
                "兌換成功 🎉",
                f"您獲得了額外獎勵：**{reward}**"
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="add_code", description="新增一個兌換碼 (限管理員或指定人員)")
    @app_commands.describe(code="兌換碼名稱", reward="兌換獎勵 (若輸入數字則兌換金幣)")
    async def add_code(self, interaction: discord.Interaction, code: str, reward: str):
        is_admin = interaction.user.guild_permissions.administrator or (interaction.user.id in self.ALLOWED_ADMINS)
        if not is_admin:
            return await interaction.response.send_message("❌ 你沒有權限使用這個指令！", ephemeral=True)

        codes = self._load_codes()
        code = code.strip()

        if code in codes:
            return await interaction.response.send_message("⚠️ 這個兌換碼已經存在了！", ephemeral=True)

        codes[code] = {"used": False, "reward": reward}
        self._save_codes(codes)

        await interaction.response.send_message(f"✅ 已新增兌換碼 `{code}`，獎勵：**{reward}**", ephemeral=True)

    @app_commands.command(name="reset_code", description="重置兌換碼狀態為未使用 (限管理員或指定人員)")
    @app_commands.describe(code="兌換碼名稱")
    async def reset_code(self, interaction: discord.Interaction, code: str):
        is_admin = interaction.user.guild_permissions.administrator or (interaction.user.id in self.ALLOWED_ADMINS)
        if not is_admin:
            return await interaction.response.send_message("❌ 你沒有權限使用這個指令！", ephemeral=True)

        codes = self._load_codes()
        code = code.strip()

        if code not in codes:
            return await interaction.response.send_message("❌ 找不到這個兌換碼！", ephemeral=True)

        codes[code]["used"] = False
        self._save_codes(codes)

        await interaction.response.send_message(f"✅ 兌換碼 `{code}` 已成功重置為未使用狀態！", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
