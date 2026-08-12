"""
專案安全性主動攻擊測試套件 (Security Vulnerability Automated Test Suite)
測試項目：
1. Calculator AST Pow CPU DoS 攻擊測試
2. Economy 併行雙重支付 / 競態條件攻擊測試
3. Database 金鑰天數溢位 / TypeError 攻擊測試
"""

import unittest
import asyncio
import os
import sys
import aiosqlite
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cogs.calculator import calculate_expression
from utils.database import Database


class TestSecurityVulnerabilities(unittest.TestCase):
    
    # ── 1. 計算機 AST Pow DoS 攻擊測試 ──
    def test_calculator_pow_dos_prevention(self):
        """測試超大指數攻擊是否被安全攔截而非卡死 CPU"""
        payloads = [
            "2^10000",
            "9^9^9",
            "10^1000000",
            "999999999999999^99999999999999",
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaises((ValueError, OverflowError)):
                    calculate_expression(payload, scientific=True)

    def test_calculator_normal_eval(self):
        """測試正常算式計算是否依舊精確"""
        self.assertEqual(calculate_expression("1+2*3", scientific=False), 7)
        self.assertEqual(calculate_expression("sqrt(16)", scientific=True), 4)

    # ── 2. Database 金鑰溢位攻擊測試 ──
    def test_database_safe_days_overflow(self):
        """測試 Pro / Ultra 金鑰超大天數或 None 是否會引發 OverflowError/TypeError"""
        async def run_db_test():
            db_file = "test_security_temp.db"
            if os.path.exists(db_file):
                os.remove(db_file)
            
            db = Database()
            db.db = await aiosqlite.connect(db_file)
            db.db.row_factory = aiosqlite.Row

            # 初始化表格
            await db.db.executescript("""
                CREATE TABLE IF NOT EXISTS pro_keys (
                    key TEXT PRIMARY KEY,
                    expires_in_days INTEGER,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS used_keys (
                    key TEXT,
                    guild_id INTEGER,
                    user_id INTEGER,
                    used_at TEXT
                );
                CREATE TABLE IF NOT EXISTS pro_guilds (
                    guild_id INTEGER PRIMARY KEY,
                    activated_by INTEGER,
                    activated_at TEXT,
                    expires_at TEXT
                );
                CREATE TABLE IF NOT EXISTS ultra_guilds (
                    guild_id INTEGER PRIMARY KEY,
                    activated_by INTEGER,
                    activated_at TEXT,
                    expires_at TEXT
                );
            """)
            await db.db.commit()
            
            try:
                # 插入帶有超大天數 (99999999) 的金鑰
                await db.db.execute(
                    "INSERT INTO pro_keys (key, expires_in_days, created_at) VALUES (?, ?, ?)",
                    ("KEY_OVERFLOW_TEST", 99999999, "2026-08-12T00:00:00")
                )
                await db.db.commit()

                # 嘗試使用該金鑰
                success = await db.use_pro_key("KEY_OVERFLOW_TEST", guild_id=123, user_id=456)
                self.assertTrue(success, "金鑰激活應該成功，不應被 OverflowError 阻斷")
                
                # 檢查激活記錄
                is_pro = await db.is_guild_pro(123)
                self.assertTrue(is_pro, "伺服器應成功激活 Pro 權限")
            finally:
                await db.db.close()
                if os.path.exists(db_file):
                    os.remove(db_file)

        asyncio.run(run_db_test())

    # ── 3. 經濟系統雙重支付競態條件測試 ──
    def test_economy_race_condition_double_spend(self):
        """測試平行發起多次轉帳請求時，是否會發生雙重扣款或負餘額漏洞"""
        async def run_economy_test():
            db_file = "test_security_economy_temp.db"
            if os.path.exists(db_file):
                os.remove(db_file)
            
            db = Database()
            db.db = await aiosqlite.connect(db_file)
            db.db.row_factory = aiosqlite.Row

            # 初始化表格
            await db.db.executescript("""
                CREATE TABLE IF NOT EXISTS economy (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    balance INTEGER DEFAULT 0,
                    last_daily TEXT DEFAULT '',
                    PRIMARY KEY (user_id, guild_id)
                );
            """)
            await db.db.commit()

            sender_id = 1001
            receiver_id = 2002
            guild_id = 999

            # 給予發送者 100 金幣
            await db.db.execute(
                "INSERT INTO economy (user_id, guild_id, balance) VALUES (?, ?, ?)",
                (sender_id, guild_id, 100)
            )
            await db.db.commit()

            # 模擬併行原子轉帳函數
            async def atomic_transfer(amount: int):
                cursor = await db.db.execute(
                    "UPDATE economy SET balance = balance - ? WHERE user_id = ? AND guild_id = ? AND balance >= ?",
                    (amount, sender_id, guild_id, amount)
                )
                if cursor.rowcount > 0:
                    await db.db.execute(
                        """INSERT INTO economy (user_id, guild_id, balance)
                           VALUES (?, ?, ?)
                           ON CONFLICT(user_id, guild_id)
                           DO UPDATE SET balance = balance + ?""",
                        (receiver_id, guild_id, amount, amount)
                    )
                    await db.db.commit()
                    return True
                return False

            # 同時發起 5 個 100 金幣的轉帳請求 (併行發射)
            results = await asyncio.gather(
                atomic_transfer(100),
                atomic_transfer(100),
                atomic_transfer(100),
                atomic_transfer(100),
                atomic_transfer(100),
            )

            success_count = sum(1 for r in results if r)
            self.assertEqual(success_count, 1, "在 100 金幣餘額下發起 5 次 100 金幣轉帳，應精確只有 1 次成功")

            # 驗證發送者最終餘額不得為負數
            async with db.db.execute("SELECT balance FROM economy WHERE user_id = ? AND guild_id = ?", (sender_id, guild_id)) as cur:
                row = await cur.fetchone()
                sender_bal = row[0]

            self.assertEqual(sender_bal, 0, "發送者最終餘額必須精確為 0，不可為負數")

            await db.db.close()
            if os.path.exists(db_file):
                os.remove(db_file)

        asyncio.run(run_economy_test())


if __name__ == "__main__":
    unittest.main()
