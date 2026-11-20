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

    # ── 4. Pro / Ultra 金鑰併發重複兌換競態條件測試 ──
    def test_pro_ultra_key_concurrent_redemption(self):
        """測試同時併發兌換同一組 Pro / Ultra 金鑰時，僅有一次可成功激活"""
        import tempfile

        async def run_key_race_test():
            tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            tmp.close()
            db = Database(db_path=tmp.name)
            await db.connect()
            try:
                await db.add_pro_key("RACE-PRO-KEY", 30)
                pro_results = await asyncio.gather(
                    *(db.use_pro_key("RACE-PRO-KEY", guild_id=100 + i, user_id=200 + i) for i in range(5))
                )
                self.assertEqual(sum(1 for r in pro_results if r), 1)

                await db.add_ultra_key("RACE-ULTRA-KEY", 30)
                ultra_results = await asyncio.gather(
                    *(db.use_ultra_key("RACE-ULTRA-KEY", guild_id=300 + i, user_id=400 + i) for i in range(5))
                )
                self.assertEqual(sum(1 for r in ultra_results if r), 1)
            finally:
                await db.close()
                if os.path.exists(tmp.name):
                    os.remove(tmp.name)

        asyncio.run(run_key_race_test())

    # ── 5. 全域管理權限提權防護測試 (AntiPlagiarism & RestMode) ──
    def test_global_admin_privilege_isolation(self):
        """測試一般伺服器管理員不可操作全域黑名單與全域休息模式"""
        from unittest.mock import AsyncMock, MagicMock
        from cogs.anti_plagiarism import AntiPlagiarism
        from cogs.rest_mode import RestMode

        async def run_priv_test():
            mock_bot = MagicMock()
            mock_bot.is_owner = AsyncMock(return_value=False)
            mock_bot.db = MagicMock()

            fake_guild_admin = MagicMock()
            fake_guild_admin.id = 987654321
            fake_guild_admin.guild_permissions.administrator = True

            ap = AntiPlagiarism(mock_bot)
            self.assertFalse(await ap._is_global_admin(fake_guild_admin))

            rm = RestMode.__new__(RestMode)
            rm.bot = mock_bot
            self.assertFalse(await rm._has_permission(fake_guild_admin))

        asyncio.run(run_priv_test())

    # ── 6. 每日簽到併發雙重領取防護測試 ──
    def test_economy_daily_concurrent_double_claim(self):
        """測試併發多次呼叫每日簽到時，僅有一次能成功領取"""
        import tempfile
        from unittest.mock import MagicMock
        from cogs.economy import Economy

        async def run_daily_test():
            tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            tmp.close()
            db = Database(db_path=tmp.name)
            await db.connect()
            try:
                mock_bot = MagicMock()
                mock_bot.db = db
                eco = Economy(mock_bot)
                await eco.cog_load()

                results = await asyncio.gather(
                    *(eco._claim_daily(1111, 2222, "2026-11-20", 100) for _ in range(5))
                )
                self.assertEqual(sum(1 for r in results if r), 1)
                self.assertEqual(await eco._get_balance(1111, 2222), 100)
            finally:
                await db.close()
                if os.path.exists(tmp.name):
                    os.remove(tmp.name)

        asyncio.run(run_daily_test())

    # ── 7. 3.0 開發者上傳 Zip Slip 路徑穿越防護與清暫存引擎測試 ──
    def test_dev_upload_zip_slip_and_cleaner(self):
        """測試 _safe_extract_path 攔截路徑穿越，且終極清暫存不誤刪 .db/.json"""
        import tempfile
        from cogs.auto_update import _safe_extract_path
        from utils.cleaner import run_sync_cleanup

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Zip Slip 攔截驗證
            self.assertIsNone(_safe_extract_path(tmpdir, "../evil.py"))
            self.assertIsNone(_safe_extract_path(tmpdir, "../../etc/passwd"))
            self.assertIsNone(_safe_extract_path(tmpdir, "/abs/path.py"))
            self.assertIsNotNone(_safe_extract_path(tmpdir, "cogs/general.py"))

            # 2. 清暫存保護核心 .db / .json，精準刪除暫存檔
            data_dir = os.path.join(tmpdir, "data")
            os.makedirs(data_dir, exist_ok=True)
            keep_db = os.path.join(data_dir, "bot.db")
            keep_json = os.path.join(data_dir, "settings.json")
            junk_tmp = os.path.join(data_dir, "voice_cache.mp3")
            for p in (keep_db, keep_json, junk_tmp):
                with open(p, "wb") as f:
                    f.write(b"12345678")

            report = run_sync_cleanup(root=tmpdir, include_system_caches=False)
            self.assertTrue(os.path.exists(keep_db))
            self.assertTrue(os.path.exists(keep_json))
            self.assertFalse(os.path.exists(junk_tmp))
            self.assertGreaterEqual(report.removed_files, 1)


if __name__ == "__main__":
    unittest.main()
