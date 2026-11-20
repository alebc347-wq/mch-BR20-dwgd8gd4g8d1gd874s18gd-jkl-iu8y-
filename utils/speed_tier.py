"""
倉鼠勇者 3.0 — 雙方案極速分流引擎 (Free vs Pro Turbo Tier)
提供：
1. 記憶體級 TTL 快取 (60s) 加速 Pro 權限查詢，消除每次指令的 SQLite I/O 延遲
2. 免費版標準節流 (3.0s) 與 Pro 疾速版無冷卻通道 (0.0s)
"""

import time
from typing import Tuple

# ─── 方案常數 ───────────────────────────────────────────────
FREE_COOLDOWN_SECONDS = 3.0
PRO_COOLDOWN_SECONDS = 0.0
PRO_CACHE_TTL_SECONDS = 60.0

BYPASS_USER_ID = 1437408048934027274

# 方案資訊（供 UI 與圖片卡片共用，無誇大行銷語句）
TIER_SPECS = {
    "free": {
        "name": "FREE 標準版",
        "cooldown_label": "3.0 秒 / 指令",
        "music_label": "單曲與 5 首內歌單",
        "card_label": "標準圖片卡片",
        "queue_label": "標準佇列",
    },
    "pro": {
        "name": "PRO 疾速版",
        "cooldown_label": "0 秒極速連發",
        "music_label": "24/7 不斷線 + 無限歌單",
        "card_label": "Pro 金箔主題圖卡優先渲染",
        "queue_label": "疾速優先通道",
    },
}


class SpeedTierManager:
    """3.0 雙方案快取與速率分流管理器"""

    def __init__(self):
        # guild_id -> (is_pro: bool, expires_at_monotonic: float)
        self._pro_cache: dict[int, tuple[bool, float]] = {}
        # (guild_id, user_id) -> last_command_monotonic: float
        self._user_cooldowns: dict[tuple[int, int], float] = {}
        self._last_gc: float = time.monotonic()

    async def is_guild_pro_fast(self, db, guild_id: int | None) -> bool:
        """超高速查詢伺服器是否為 Pro 方案（命中快取 < 0.01 ms）"""
        if not guild_id or db is None:
            return False

        now = time.monotonic()
        cached = self._pro_cache.get(guild_id)
        if cached is not None and now < cached[1]:
            return cached[0]

        try:
            is_pro = await db.is_guild_pro(guild_id)
        except Exception:
            is_pro = False

        self._pro_cache[guild_id] = (is_pro, now + PRO_CACHE_TTL_SECONDS)
        return is_pro

    def invalidate_guild(self, guild_id: int | None) -> None:
        """當伺服器啟用或變更 Pro 狀態時立即清除快取"""
        if guild_id is not None:
            self._pro_cache.pop(guild_id, None)

    def clear_all(self) -> None:
        self._pro_cache.clear()
        self._user_cooldowns.clear()

    def _maybe_gc(self, now: float) -> None:
        """每 5 分鐘回收過期的冷卻紀錄，防止記憶體增長"""
        if now - self._last_gc < 300.0:
            return
        self._last_gc = now
        cutoff = now - 60.0
        self._user_cooldowns = {
            k: ts for k, ts in self._user_cooldowns.items() if ts > cutoff
        }
        self._pro_cache = {
            gid: val for gid, val in self._pro_cache.items() if val[1] > now
        }

    async def check_rate_limit(
        self,
        db,
        guild_id: int | None,
        user_id: int,
        bypass: bool = False,
    ) -> Tuple[bool, float, bool]:
        """
        檢查使用者是否可立即執行指令。
        回傳: (allowed: bool, retry_after: float, is_pro: bool)
        """
        if bypass or user_id == BYPASS_USER_ID:
            return True, 0.0, True

        is_pro = await self.is_guild_pro_fast(db, guild_id)
        if is_pro:
            return True, 0.0, True

        now = time.monotonic()
        self._maybe_gc(now)

        key = (guild_id or 0, user_id)
        last_ts = self._user_cooldowns.get(key, 0.0)
        elapsed = now - last_ts

        if elapsed < FREE_COOLDOWN_SECONDS:
            return False, round(FREE_COOLDOWN_SECONDS - elapsed, 1), False

        self._user_cooldowns[key] = now
        return True, 0.0, False


# 全域單例
speed_tier = SpeedTierManager()
