"""
全 Cog 載入與核心資料庫完整性測試套件
"""
import unittest
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import ProBot
from cogs.calculator import calculate_expression

class TestSystemIntegrity(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = ProBot()
        self.bot.wait_until_ready = lambda: asyncio.sleep(0)
        await self.bot.db.connect()

    async def asyncTearDown(self):
        await self.bot.db.close()

    async def test_all_29_cogs_load(self):
        cog_files = [
            "cogs.general", "cogs.moderation", "cogs.auto_mod", "cogs.logging_cog",
            "cogs.youtube", "cogs.sponsor", "cogs.music", "cogs.pro", "cogs.ultra",
            "cogs.entertainment", "cogs.giveaway", "cogs.tools", "cogs.crypto",
            "cogs.calculator", "cogs.community", "cogs.fun_text", "cogs.economy",
            "cogs.disaster", "cogs.auto_reply", "cogs.exam", "cogs.guild_exam",
            "cogs.cross_guild_chat", "cogs.competitor", "cogs.auto_update",
            "cogs.discord_control", "cogs.role_claim", "cogs.anti_plagiarism",
            "cogs.appeal", "cogs.rest_mode"
        ]
        for c in cog_files:
            with self.subTest(cog=c):
                await self.bot.load_extension(c)

    async def test_database_favorite_songs(self):
        user_id = 999999999
        # 測試加入
        ok = await self.bot.db.add_favorite_song(user_id, "Test Track", "https://youtu.be/test", "Artist", 120000)
        self.assertTrue(ok)
        # 測試重複加入
        ok_dup = await self.bot.db.add_favorite_song(user_id, "Test Track", "https://youtu.be/test", "Artist", 120000)
        self.assertFalse(ok_dup)
        # 測試查詢
        favs = await self.bot.db.get_favorite_songs(user_id)
        self.assertEqual(len(favs), 1)
        self.assertEqual(favs[0]["title"], "Test Track")
        # 測試刪除
        del_ok = await self.bot.db.remove_favorite_song(user_id, favs[0]["id"])
        self.assertTrue(del_ok)
        favs_after = await self.bot.db.get_favorite_songs(user_id)
        self.assertEqual(len(favs_after), 0)

    def test_calculator_default_param(self):
        val = calculate_expression("10 * 5 + 2")
        self.assertEqual(val, 52)
