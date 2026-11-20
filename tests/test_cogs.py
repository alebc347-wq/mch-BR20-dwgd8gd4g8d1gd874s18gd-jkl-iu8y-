"""
全 Cog 載入與核心資料庫完整性測試套件
"""
import unittest
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import ProBot
from cogs.calculator import calculate_expression
from utils.embeds import EmbedFactory

class TestSystemIntegrity(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp_db.close()
        self.bot = ProBot(db_path=self._tmp_db.name)
        self.bot.wait_until_ready = lambda: asyncio.sleep(0)
        await self.bot.db.connect()

    async def asyncTearDown(self):
        for ext in list(self.bot.extensions.keys()):
            try:
                await self.bot.unload_extension(ext)
            except Exception:
                pass
        await self.bot.db.close()
        if os.path.exists(self._tmp_db.name):
            try:
                os.remove(self._tmp_db.name)
            except OSError:
                pass

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

    def test_tools_has_level_role_method(self):
        from cogs.tools import Tools
        self.assertTrue(hasattr(Tools, "ensure_and_assign_level_role"))
        self.assertTrue(hasattr(Tools, "on_member_join"))
        self.assertTrue(hasattr(Tools, "rank"))

    async def test_pro_keys_crud(self):
        test_key = "HERO-PRO-TEST-12345"
        await self.bot.db.add_pro_key(test_key, 30)
        unused = await self.bot.db.get_pro_keys()
        self.assertTrue(any(r["key"] == test_key for r in unused))
        # Test use
        used_ok = await self.bot.db.use_pro_key(test_key, 123456, 999999)
        self.assertTrue(used_ok)
        unused_after = await self.bot.db.get_pro_keys()
        self.assertFalse(any(r["key"] == test_key for r in unused_after))

    def test_embed_factory_without_icons(self):
        embed = EmbedFactory._base_embed(
            title="Test",
            description="Body",
            author_name="Tester",
            footer_text="Footer",
        )
        self.assertEqual(embed.author.name, "Tester")
        self.assertEqual(embed.footer.text, "Footer")

    async def test_3_0_visual_cards_render(self):
        """驗證 3.0 全部 7 款程式化 PNG 視覺卡片皆可正常快速渲染"""
        from utils.visual_cards import (
            render_help_banner,
            render_plan_card,
            render_ping_card,
            render_health_card,
            render_profile_card,
            render_server_card,
            render_version_card,
        )
        png_sig = b"\x89PNG\r\n\x1a\n"
        cards = [
            await render_help_banner(True, 10, 29, 42.5),
            await render_plan_card("測試伺服器", False),
            await render_ping_card(38.2, 0.45, True),
            await render_health_card(40.0, 0.5, True, "ACTIVE (wispbyte-1)", True, False, "2/4 在線", 29, "1時 20分", 12),
            await render_profile_card("倉鼠勇者", "hamster", 123456, True, ["團長", "開發者"], "2026-01-01", "2025-01-01", None),
            await render_server_card("測試群組", 999999, False, 128, 42, 15, 4, 12, 2, None),
            await render_version_card("3.0.0", True),
        ]
        for buf in cards:
            data = buf.getvalue()
            self.assertTrue(data.startswith(png_sig))
            self.assertGreater(len(data), 1000)

    async def test_3_0_speed_tier_free_vs_pro(self):
        """驗證 3.0 雙方案速率分流：免費版 3s 節流 vs Pro 版 0s 疾速連發"""
        from utils.speed_tier import SpeedTierManager
        mgr = SpeedTierManager()
        # 免費伺服器：第一次通過，第二次立即被節流
        ok1, wait1, is_pro1 = await mgr.check_rate_limit(self.bot.db, guild_id=5001, user_id=7001)
        self.assertTrue(ok1)
        self.assertFalse(is_pro1)
        ok2, wait2, is_pro2 = await mgr.check_rate_limit(self.bot.db, guild_id=5001, user_id=7001)
        self.assertFalse(ok2)
        self.assertGreater(wait2, 0.0)

        # 啟用 Pro 後清除快取 -> 0 秒極速連發
        await self.bot.db.add_pro_key("SPEED-PRO-30", 30)
        await self.bot.db.use_pro_key("SPEED-PRO-30", guild_id=5001, user_id=7001)
        mgr.invalidate_guild(5001)
        for _ in range(5):
            ok, wait, is_pro = await mgr.check_rate_limit(self.bot.db, guild_id=5001, user_id=7001)
            self.assertTrue(ok)
            self.assertTrue(is_pro)
            self.assertEqual(wait, 0.0)

    async def test_tool_delete_channels_modes(self):
        """驗證 /tool delete_channels 三種模式（刪除全部 / 保留指定 / 刪除指定）與排序邏輯"""
        import discord
        from unittest.mock import MagicMock
        from cogs.tools import Tools, _compute_channels_to_delete

        await self.bot.load_extension("cogs.tools")
        cog = self.bot.get_cog("tool") or self.bot.get_cog("Tools")
        self.assertIsNotNone(cog)
        cmd_names = [cmd.name for cmd in cog.app_command.commands]
        self.assertIn("delete_channels", cmd_names)

        ch_text1 = MagicMock(spec=discord.TextChannel)
        ch_text1.id, ch_text1.name = 101, "general"
        ch_text2 = MagicMock(spec=discord.TextChannel)
        ch_text2.id, ch_text2.name = 102, "chat"
        ch_cat = MagicMock(spec=discord.CategoryChannel)
        ch_cat.id, ch_cat.name = 201, "info-cat"
        channels = [ch_cat, ch_text1, ch_text2]

        # 1. 刪除所有頻道（含分類，且發起頻道 101 排最後）
        all_targets = _compute_channels_to_delete(channels, "all", set(), include_categories=True, origin_channel_id=101)
        self.assertEqual([c.id for c in all_targets], [102, 201, 101])

        # 2. 刪除所有頻道（不含分類）
        all_no_cat = _compute_channels_to_delete(channels, "all", set(), include_categories=False, origin_channel_id=101)
        self.assertEqual([c.id for c in all_no_cat], [102, 101])

        # 3. 保留指定頻道（保留 101）
        keep_targets = _compute_channels_to_delete(channels, "keep", {101}, include_categories=True, origin_channel_id=101)
        self.assertEqual([c.id for c in keep_targets], [102, 201])

        # 4. 僅刪除指定頻道（只刪 102 與 201）
        spec_targets = _compute_channels_to_delete(channels, "specific", {102, 201}, include_categories=False, origin_channel_id=101)
        self.assertEqual([c.id for c in spec_targets], [102, 201])

    async def test_coordination_channel_legacy_migration(self):
        """驗證已刪除之舊總控頻道 ID 自動遷移至新總控頻道 1573278907996577953"""
        from unittest.mock import patch
        from config import DEFAULT_COORDINATION_CHANNEL_ID, resolve_coordination_channel_id

        with patch.dict(os.environ, {"COORDINATION_CHANNEL_ID": "1473141984855199856"}):
            self.assertEqual(resolve_coordination_channel_id(), DEFAULT_COORDINATION_CHANNEL_ID)
            self.assertEqual(resolve_coordination_channel_id(), 1573278907996577953)

        with patch.dict(os.environ, {"COORDINATION_CHANNEL_ID": "1573278907996577953"}):
            self.assertEqual(resolve_coordination_channel_id(), 1573278907996577953)

        with patch.dict(os.environ, {"COORDINATION_CHANNEL_ID": ""}):
            self.assertEqual(resolve_coordination_channel_id(), 0)
