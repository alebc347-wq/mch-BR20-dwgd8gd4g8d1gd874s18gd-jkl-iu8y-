"""
SQLite 資料庫管理
使用 aiosqlite 進行非同步資料庫操作
"""

import aiosqlite
import os
import json
from datetime import datetime, timezone


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "bot.db")


class Database:
    """非同步 SQLite 資料庫管理器"""

    def __init__(self):
        self.db: aiosqlite.Connection | None = None

    async def connect(self):
        """連接資料庫並建立表"""
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.db = await aiosqlite.connect(DB_PATH)
        self.db.row_factory = aiosqlite.Row
        await self._create_tables()
        
        # 自動遷移舊的 YouTube Channel ID 預設值為 @CalebYT-t1g
        try:
            async with self.db.execute(
                "SELECT value FROM global_settings WHERE key = 'owner_youtube_channel_id'"
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0] == "UC-lHJZR3Gqxm24_Vd_AJ5Yw":
                    await self.db.execute(
                        "UPDATE global_settings SET value = '@CalebYT-t1g' WHERE key = 'owner_youtube_channel_id'"
                    )
                    await self.db.commit()
                    print("✅ 資料庫已自動遷移舊的 YouTube 頻道設定為 @CalebYT-t1g")
        except Exception as e:
            print(f"自動遷移舊版頻道設定失敗: {e}")

    async def close(self):
        """關閉資料庫連接"""
        if self.db:
            await self.db.close()

    async def _create_tables(self):
        """建立所有必要的表"""
        await self.db.executescript("""
            -- 警告紀錄
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            -- 伺服器設定
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                log_channel_id INTEGER,
                autorole_id INTEGER,
                automod_enabled INTEGER DEFAULT 0,
                automod_bad_words TEXT DEFAULT '[]',
                automod_spam_enabled INTEGER DEFAULT 1,
                automod_links_enabled INTEGER DEFAULT 0,
                automod_caps_enabled INTEGER DEFAULT 0,
                automod_mentions_max INTEGER DEFAULT 5,
                automod_whitelist_channels TEXT DEFAULT '[]',
                automod_whitelist_roles TEXT DEFAULT '[]',
                warn_actions TEXT DEFAULT '{}',
                log_events TEXT DEFAULT '["all"]'
            );

            -- 抽獎
            CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                host_id INTEGER NOT NULL,
                prize TEXT NOT NULL,
                winners_count INTEGER DEFAULT 1,
                entries TEXT DEFAULT '[]',
                ends_at TEXT NOT NULL,
                ended INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            -- 反刷屏追蹤
            CREATE TABLE IF NOT EXISTS spam_tracker (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                message_hash TEXT NOT NULL,
                count INTEGER DEFAULT 1,
                last_message_at TEXT NOT NULL,
                PRIMARY KEY (user_id, guild_id)
            );

            -- 使用者最愛音樂清單
            CREATE TABLE IF NOT EXISTS user_favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                uri TEXT NOT NULL,
                author TEXT,
                duration INTEGER,
                created_at TEXT NOT NULL
            );

            -- Pro 金鑰與伺服器啟用狀態
            CREATE TABLE IF NOT EXISTS pro_keys (
                key TEXT PRIMARY KEY,
                expires_in_days INTEGER DEFAULT 30,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS used_keys (
                key TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                used_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pro_guilds (
                guild_id INTEGER PRIMARY KEY,
                activated_by INTEGER NOT NULL,
                activated_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            -- Ultra 金鑰與伺服器啟用狀態
            CREATE TABLE IF NOT EXISTS ultra_keys (
                key TEXT PRIMARY KEY,
                expires_in_days INTEGER DEFAULT 30,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS used_ultra_keys (
                key TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                used_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ultra_guilds (
                guild_id INTEGER PRIMARY KEY,
                activated_by INTEGER NOT NULL,
                activated_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            -- 全域設定
            CREATE TABLE IF NOT EXISTS global_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            -- YouTube 訂閱通知
            CREATE TABLE IF NOT EXISTS youtube_subscriptions (
                channel_id TEXT NOT NULL,
                channel_name TEXT,
                guild_id INTEGER NOT NULL,
                notification_channel_id INTEGER NOT NULL,
                last_video_id TEXT,
                last_published TEXT,
                PRIMARY KEY (channel_id, guild_id)
            );

            -- 金主排行榜設定
            CREATE TABLE IF NOT EXISTS sponsor_settings (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                message_id INTEGER
            );

            -- 金主名單與排序
            CREATE TABLE IF NOT EXISTS sponsor_leaderboard (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                position INTEGER DEFAULT 0,
                note TEXT,
                PRIMARY KEY (guild_id, user_id)
            );

            -- 考試題目
            CREATE TABLE IF NOT EXISTS exam_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                question_text TEXT NOT NULL
            );

            -- 活動中的考試會話
            CREATE TABLE IF NOT EXISTS active_exams (
                thread_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                current_question_index INTEGER DEFAULT 0,
                answers TEXT DEFAULT '{}',
                started_at TEXT NOT NULL
            );

            -- 伺服器自訂功能開關 (如重啟通知)
            CREATE TABLE IF NOT EXISTS guild_features (
                guild_id INTEGER,
                feature_name TEXT,
                enabled INTEGER,
                PRIMARY KEY (guild_id, feature_name)
            );

            -- 被禁止使用 say 指令的使用者
            CREATE TABLE IF NOT EXISTS blocked_users_say (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );

            -- 跨群聊天系統
            CREATE TABLE IF NOT EXISTS cross_guild_chat (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                pairing_code TEXT UNIQUE,
                paired_guild_id INTEGER,
                webhook_url TEXT,
                invite_from_guild_id INTEGER,
                pairing_message_id INTEGER
            );

            -- 跨群聊天連線關係表 (多對多)
            CREATE TABLE IF NOT EXISTS cross_guild_connections (
                guild_id INTEGER,
                connected_guild_id INTEGER,
                webhook_url TEXT,
                PRIMARY KEY (guild_id, connected_guild_id)
            );

            -- 跨群聊天邀請表 (多重邀請)
            CREATE TABLE IF NOT EXISTS cross_guild_invites (
                guild_id INTEGER,
                inviter_guild_id INTEGER,
                PRIMARY KEY (guild_id, inviter_guild_id)
            );

            -- 跨群聊天訊息對應表
            CREATE TABLE IF NOT EXISTS cross_guild_message_mappings (
                group_id TEXT,
                channel_id INTEGER,
                message_id INTEGER,
                PRIMARY KEY (channel_id, message_id)
            );

            -- 競爭者名單設定
            CREATE TABLE IF NOT EXISTS competitor_settings (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                message_id INTEGER
            );

            -- 競爭者名單成員
            CREATE TABLE IF NOT EXISTS competitor_roster (
                guild_id INTEGER NOT NULL,
                discord_id INTEGER NOT NULL,
                roblox_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, discord_id)
            );
        """)
        await self.db.commit()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 警告系統
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
        """新增警告，回傳累計警告數"""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason, now),
        )
        await self.db.commit()
        return await self.get_warning_count(guild_id, user_id)

    async def get_warning_count(self, guild_id: int, user_id: int) -> int:
        """取得用戶警告數"""
        async with self.db.execute(
            "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_warnings(self, guild_id: int, user_id: int) -> list:
        """取得用戶所有警告紀錄"""
        async with self.db.execute(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
            (guild_id, user_id),
        ) as cursor:
            return await cursor.fetchall()

    async def clear_warning(self, guild_id: int, user_id: int, warn_id: int = None) -> bool:
        """清除警告（指定 ID 或全部）"""
        if warn_id:
            await self.db.execute(
                "DELETE FROM warnings WHERE id = ? AND guild_id = ? AND user_id = ?",
                (warn_id, guild_id, user_id),
            )
        else:
            await self.db.execute(
                "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
        await self.db.commit()
        return True

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 伺服器設定
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def get_guild_settings(self, guild_id: int) -> dict:
        """取得伺服器設定"""
        async with self.db.execute(
            "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            # 建立預設設定
            await self.db.execute(
                "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,)
            )
            await self.db.commit()
            return {
                "guild_id": guild_id,
                "log_channel_id": None,
                "autorole_id": None,
                "automod_enabled": 0,
                "automod_bad_words": "[]",
                "automod_spam_enabled": 1,
                "automod_links_enabled": 0,
                "automod_caps_enabled": 0,
                "automod_mentions_max": 5,
                "automod_whitelist_channels": "[]",
                "automod_whitelist_roles": "[]",
                "warn_actions": "{}",
                "log_events": '["all"]',
            }

    async def update_guild_setting(self, guild_id: int, key: str, value) -> None:
        """更新單一伺服器設定"""
        await self.db.execute(
            "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,)
        )
        await self.db.execute(
            f"UPDATE guild_settings SET {key} = ? WHERE guild_id = ?", (value, guild_id)
        )
        await self.db.commit()

    async def get_log_channel(self, guild_id: int) -> int | None:
        """取得日誌頻道 ID"""
        settings = await self.get_guild_settings(guild_id)
        return settings.get("log_channel_id")

    async def set_log_channel(self, guild_id: int, channel_id: int) -> None:
        """設定日誌頻道"""
        await self.update_guild_setting(guild_id, "log_channel_id", channel_id)

    async def get_autorole(self, guild_id: int) -> int | None:
        """取得自動角色 ID"""
        settings = await self.get_guild_settings(guild_id)
        return settings.get("autorole_id")

    async def set_autorole(self, guild_id: int, role_id: int | None) -> None:
        """設定自動角色"""
        await self.update_guild_setting(guild_id, "autorole_id", role_id)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 自動審核
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def get_bad_words(self, guild_id: int) -> list:
        """取得過濾詞彙清單"""
        settings = await self.get_guild_settings(guild_id)
        return json.loads(settings.get("automod_bad_words", "[]"))

    async def add_bad_word(self, guild_id: int, word: str) -> None:
        """新增過濾詞彙"""
        words = await self.get_bad_words(guild_id)
        if word.lower() not in words:
            words.append(word.lower())
            await self.update_guild_setting(guild_id, "automod_bad_words", json.dumps(words))

    async def remove_bad_word(self, guild_id: int, word: str) -> bool:
        """移除過濾詞彙"""
        words = await self.get_bad_words(guild_id)
        if word.lower() in words:
            words.remove(word.lower())
            await self.update_guild_setting(guild_id, "automod_bad_words", json.dumps(words))
            return True
        return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 抽獎系統
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def create_giveaway(self, guild_id: int, channel_id: int, message_id: int, host_id: int, prize: str, winners_count: int, ends_at: str) -> int:
        """建立抽獎，回傳 ID"""
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.db.execute(
            "INSERT INTO giveaways (guild_id, channel_id, message_id, host_id, prize, winners_count, ends_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (guild_id, channel_id, message_id, host_id, prize, winners_count, ends_at, now),
        )
        await self.db.commit()
        return cursor.lastrowid

    async def add_giveaway_entry(self, giveaway_id: int, user_id: int) -> bool:
        """參加抽獎"""
        async with self.db.execute(
            "SELECT entries FROM giveaways WHERE id = ?", (giveaway_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False
            entries = json.loads(row[0])
            if user_id in entries:
                return False
            entries.append(user_id)
            await self.db.execute(
                "UPDATE giveaways SET entries = ? WHERE id = ?",
                (json.dumps(entries), giveaway_id),
            )
            await self.db.commit()
            return True

    async def get_giveaway(self, giveaway_id: int) -> dict | None:
        """取得抽獎資料"""
        async with self.db.execute(
            "SELECT * FROM giveaways WHERE id = ?", (giveaway_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_active_giveaways(self, guild_id: int) -> list:
        """取得進行中的抽獎"""
        async with self.db.execute(
            "SELECT * FROM giveaways WHERE guild_id = ? AND ended = 0",
            (guild_id,),
        ) as cursor:
            return await cursor.fetchall()

    async def end_giveaway(self, giveaway_id: int) -> None:
        """結束抽獎"""
        await self.db.execute(
            "UPDATE giveaways SET ended = 1 WHERE id = ?", (giveaway_id,)
        )
        await self.db.commit()

    async def get_giveaway_by_message(self, message_id: int) -> dict | None:
        """透過訊息 ID 取得抽獎"""
        async with self.db.execute(
            "SELECT * FROM giveaways WHERE message_id = ?", (message_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 反刷屏
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def track_message(self, user_id: int, guild_id: int, message_hash: str) -> int:
        """追蹤訊息用於刷屏偵測，回傳短時間內的重複計數"""
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.execute(
            "SELECT count, message_hash FROM spam_tracker WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[1] == message_hash:
                new_count = row[0] + 1
                await self.db.execute(
                    "UPDATE spam_tracker SET count = ?, last_message_at = ? WHERE user_id = ? AND guild_id = ?",
                    (new_count, now, user_id, guild_id),
                )
            else:
                new_count = 1
                await self.db.execute(
                    "INSERT OR REPLACE INTO spam_tracker (user_id, guild_id, message_hash, count, last_message_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, guild_id, message_hash, 1, now),
                )
            await self.db.commit()
            return new_count

    async def reset_spam_tracker(self, user_id: int, guild_id: int) -> None:
        """重置刷屏追蹤"""
        await self.db.execute(
            "DELETE FROM spam_tracker WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        await self.db.commit()

    async def get_spam_limit(self, guild_id: int, default: int = 7) -> int:
        """取得伺服器刷屏限制次數"""
        if not self.db:
            return default
        try:
            async with self.db.execute(
                "SELECT enabled FROM guild_features WHERE guild_id = ? AND feature_name = 'spam_limit'",
                (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row is not None:
                    return int(row[0])
        except Exception:
            pass
        return default

    async def set_spam_limit(self, guild_id: int, limit: int):
        """設定伺服器刷屏限制次數"""
        if not self.db:
            return
        try:
            await self.db.execute(
                "INSERT OR REPLACE INTO guild_features (guild_id, feature_name, enabled) VALUES (?, 'spam_limit', ?)",
                (guild_id, limit)
            )
            await self.db.commit()
        except Exception as e:
            print(f"Error setting spam limit: {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 音樂系統 - 使用者最愛清單
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def add_favorite_song(self, user_id: int, title: str, uri: str, author: str = "", duration: int = 0) -> bool:
        """新增最愛歌曲，若已存在則不重複新增"""
        async with self.db.execute(
            "SELECT id FROM user_favorites WHERE user_id = ? AND uri = ?", (user_id, uri)
        ) as cursor:
            if await cursor.fetchone():
                return False  # 已存在
        
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "INSERT INTO user_favorites (user_id, title, uri, author, duration, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, title, uri, author, duration, now),
        )
        await self.db.commit()
        return True

    async def get_favorite_songs(self, user_id: int) -> list:
        """取得使用者的所有最愛歌曲"""
        async with self.db.execute(
            "SELECT * FROM user_favorites WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ) as cursor:
            return await cursor.fetchall()

    async def remove_favorite_song(self, user_id: int, song_id: int) -> bool:
        """依 ID 移除最愛歌曲"""
        cursor = await self.db.execute(
            "DELETE FROM user_favorites WHERE id = ? AND user_id = ?", (song_id, user_id)
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def is_favorite_song(self, user_id: int, uri: str) -> bool:
        """檢查歌曲是否已被加入最愛"""
        async with self.db.execute(
            "SELECT id FROM user_favorites WHERE user_id = ? AND uri = ?", (user_id, uri)
        ) as cursor:
            return await cursor.fetchone() is not None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Pro 系統金鑰與狀態管理
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def add_pro_key(self, key: str, expires_in_days: int = 30) -> None:
        """新增一個未使用的 Pro 激活金鑰"""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "INSERT INTO pro_keys (key, expires_in_days, created_at) VALUES (?, ?, ?)",
            (key, expires_in_days, now)
        )
        await self.db.commit()

    async def get_pro_keys(self) -> list:
        """獲取所有未使用的 Pro 金鑰"""
        async with self.db.execute("SELECT * FROM pro_keys ORDER BY created_at DESC") as cursor:
            return await cursor.fetchall()

    async def get_used_keys(self) -> list:
        """獲取所有已使用的 Pro 金鑰記錄"""
        async with self.db.execute("SELECT * FROM used_keys ORDER BY used_at DESC") as cursor:
            return await cursor.fetchall()

    async def use_pro_key(self, key: str, guild_id: int, user_id: int) -> bool:
        """使用金鑰激活該伺服器的 Pro 權限"""
        # 1. 檢查金鑰是否存在於未使用的列表中
        async with self.db.execute("SELECT expires_in_days FROM pro_keys WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False
            expires_in_days = row[0]

        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        
        # 計算過期時間
        from datetime import timedelta
        expires_at = (now + timedelta(days=expires_in_days)).isoformat()

        # 2. 插入使用記錄
        await self.db.execute(
            "INSERT INTO used_keys (key, guild_id, user_id, used_at) VALUES (?, ?, ?, ?)",
            (key, guild_id, user_id, now_str)
        )

        # 3. 刪除未使用的金鑰
        await self.db.execute("DELETE FROM pro_keys WHERE key = ?", (key,))

        # 4. 更新/插入伺服器 Pro 狀態
        # 如果已經是 Pro 且未過期，則延長時間，否則從現在開始算
        async with self.db.execute("SELECT expires_at FROM pro_guilds WHERE guild_id = ?", (guild_id,)) as cursor:
            existing = await cursor.fetchone()
            if existing:
                try:
                    ext_expires = datetime.fromisoformat(existing[0])
                    if ext_expires.replace(tzinfo=timezone.utc) > now.replace(tzinfo=timezone.utc):
                        expires_at = (ext_expires.replace(tzinfo=timezone.utc) + timedelta(days=expires_in_days)).isoformat()
                except Exception:
                    pass

        await self.db.execute(
            "INSERT OR REPLACE INTO pro_guilds (guild_id, activated_by, activated_at, expires_at) VALUES (?, ?, ?, ?)",
            (guild_id, user_id, now_str, expires_at)
        )

        await self.db.commit()
        return True

    async def is_guild_pro(self, guild_id: int) -> bool:
        """檢查該伺服器是否擁有有效的 Pro 權限"""
        # 若已擁有 Ultra 權限，自動判定為擁有 Pro 權限
        if await self.is_guild_ultra(guild_id):
            return True

        async with self.db.execute("SELECT expires_at FROM pro_guilds WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False
            
            expires_at_str = row[0]
            try:
                expires_at = datetime.fromisoformat(expires_at_str).replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                return expires_at > now
            except Exception:
                return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Ultra 系統金鑰與狀態管理
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def add_ultra_key(self, key: str, expires_in_days: int = 30) -> None:
        """新增一個未使用的 Ultra 激活金鑰"""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "INSERT INTO ultra_keys (key, expires_in_days, created_at) VALUES (?, ?, ?)",
            (key, expires_in_days, now)
        )
        await self.db.commit()

    async def get_ultra_keys(self) -> list:
        """獲取所有未使用的 Ultra 金鑰"""
        async with self.db.execute("SELECT * FROM ultra_keys ORDER BY created_at DESC") as cursor:
            return await cursor.fetchall()

    async def get_used_ultra_keys(self) -> list:
        """獲取所有已使用的 Ultra 金鑰記錄"""
        async with self.db.execute("SELECT * FROM used_ultra_keys ORDER BY used_at DESC") as cursor:
            return await cursor.fetchall()

    async def use_ultra_key(self, key: str, guild_id: int, user_id: int) -> bool:
        """使用金鑰激活該伺服器的 Ultra 權限"""
        # 1. 檢查金鑰是否存在於未使用的列表中
        async with self.db.execute("SELECT expires_in_days FROM ultra_keys WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False
            expires_in_days = row[0]

        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        
        # 計算過期時間
        from datetime import timedelta
        expires_at = (now + timedelta(days=expires_in_days)).isoformat()

        # 2. 插入使用記錄
        await self.db.execute(
            "INSERT INTO used_ultra_keys (key, guild_id, user_id, used_at) VALUES (?, ?, ?, ?)",
            (key, guild_id, user_id, now_str)
        )

        # 3. 刪除未使用的金鑰
        await self.db.execute("DELETE FROM ultra_keys WHERE key = ?", (key,))

        # 4. 更新/插入伺服器 Ultra 狀態
        async with self.db.execute("SELECT expires_at FROM ultra_guilds WHERE guild_id = ?", (guild_id,)) as cursor:
            existing = await cursor.fetchone()
            if existing:
                try:
                    ext_expires = datetime.fromisoformat(existing[0])
                    if ext_expires.replace(tzinfo=timezone.utc) > now.replace(tzinfo=timezone.utc):
                        expires_at = (ext_expires.replace(tzinfo=timezone.utc) + timedelta(days=expires_in_days)).isoformat()
                except Exception:
                    pass

        await self.db.execute(
            "INSERT OR REPLACE INTO ultra_guilds (guild_id, activated_by, activated_at, expires_at) VALUES (?, ?, ?, ?)",
            (guild_id, user_id, now_str, expires_at)
        )

        await self.db.commit()
        return True

    async def activate_ultra_guild_direct(self, guild_id: int, user_id: int, expires_in_days: int = 30) -> None:
        """直接激活該伺服器的 Ultra 權限 (用於訂閱成功)"""
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        
        from datetime import timedelta
        expires_at = (now + timedelta(days=expires_in_days)).isoformat()

        # 如果已經是 Ultra 且未過期，則延長時間，否則從現在開始算
        async with self.db.execute("SELECT expires_at FROM ultra_guilds WHERE guild_id = ?", (guild_id,)) as cursor:
            existing = await cursor.fetchone()
            if existing:
                try:
                    ext_expires = datetime.fromisoformat(existing[0])
                    if ext_expires.replace(tzinfo=timezone.utc) > now.replace(tzinfo=timezone.utc):
                        expires_at = (ext_expires.replace(tzinfo=timezone.utc) + timedelta(days=expires_in_days)).isoformat()
                except Exception:
                    pass

        await self.db.execute(
            "INSERT OR REPLACE INTO ultra_guilds (guild_id, activated_by, activated_at, expires_at) VALUES (?, ?, ?, ?)",
            (guild_id, user_id, now_str, expires_at)
        )
        await self.db.commit()

    async def is_guild_ultra(self, guild_id: int) -> bool:
        """檢查該伺服器是否擁有有效的 Ultra 權限"""
        async with self.db.execute("SELECT expires_at FROM ultra_guilds WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False
            
            expires_at_str = row[0]
            try:
                expires_at = datetime.fromisoformat(expires_at_str).replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                return expires_at > now
            except Exception:
                return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 全域設定管理
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def get_global_setting(self, key: str, default: str = None) -> str | None:
        """取得全域設定值"""
        async with self.db.execute("SELECT value FROM global_settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

    async def set_global_setting(self, key: str, value: str) -> None:
        """設定全域設定值"""
        await self.db.execute(
            "INSERT OR REPLACE INTO global_settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        await self.db.commit()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # YouTube 訂閱通知系統
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def add_youtube_sub(self, channel_id: str, channel_name: str, guild_id: int, notification_channel_id: int) -> None:
        """新增/更新 YouTube 頻道訂閱"""
        await self.db.execute(
            "INSERT OR REPLACE INTO youtube_subscriptions (channel_id, channel_name, guild_id, notification_channel_id) VALUES (?, ?, ?, ?)",
            (channel_id, channel_name, guild_id, notification_channel_id),
        )
        await self.db.commit()

    async def remove_youtube_sub(self, channel_id: str, guild_id: int) -> bool:
        """移除 YouTube 頻道訂閱"""
        cursor = await self.db.execute(
            "DELETE FROM youtube_subscriptions WHERE channel_id = ? AND guild_id = ?",
            (channel_id, guild_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def get_youtube_subs(self, guild_id: int) -> list:
        """取得伺服器所有的 YouTube 訂閱"""
        async with self.db.execute(
            "SELECT * FROM youtube_subscriptions WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            return await cursor.fetchall()

    async def get_all_youtube_subs(self) -> list:
        """取得所有伺服器的所有 YouTube 訂閱"""
        async with self.db.execute("SELECT * FROM youtube_subscriptions") as cursor:
            return await cursor.fetchall()

    async def update_youtube_last_video(self, channel_id: str, guild_id: int, video_id: str, published: str) -> None:
        """更新已通知的最新影片 ID"""
        await self.db.execute(
            "UPDATE youtube_subscriptions SET last_video_id = ?, last_published = ? WHERE channel_id = ? AND guild_id = ?",
            (video_id, published, channel_id, guild_id),
        )
        await self.db.commit()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 金主排行榜系統
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def get_sponsor_settings(self, guild_id: int) -> dict | None:
        """取得伺服器排行榜頻道與訊息設定"""
        async with self.db.execute(
            "SELECT * FROM sponsor_settings WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def set_sponsor_settings(self, guild_id: int, channel_id: int, message_id: int) -> None:
        """儲存或更新排行榜設定"""
        await self.db.execute(
            "INSERT OR REPLACE INTO sponsor_settings (guild_id, channel_id, message_id) VALUES (?, ?, ?)",
            (guild_id, channel_id, message_id),
        )
        await self.db.commit()

    async def get_sponsors(self, guild_id: int) -> list:
        """取得伺服器所有金主列表（按排序位置升冪）"""
        async with self.db.execute(
            "SELECT * FROM sponsor_leaderboard WHERE guild_id = ? ORDER BY position ASC, rowid ASC",
            (guild_id,),
        ) as cursor:
            return await cursor.fetchall()

    async def add_sponsor(self, guild_id: int, user_id: int, note: str = "") -> None:
        """新增金主，預設排在最後一位"""
        # 獲取目前最大的位置值
        async with self.db.execute(
            "SELECT MAX(position) FROM sponsor_leaderboard WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            max_pos = row[0] if row and row[0] is not None else 0
            
        await self.db.execute(
            "INSERT OR REPLACE INTO sponsor_leaderboard (guild_id, user_id, position, note) VALUES (?, ?, ?, ?)",
            (guild_id, user_id, max_pos + 1, note),
        )
        await self.db.commit()

    async def remove_sponsor(self, guild_id: int, user_id: int) -> bool:
        """從排行榜中移除金主"""
        cursor = await self.db.execute(
            "DELETE FROM sponsor_leaderboard WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def update_sponsor_note(self, guild_id: int, user_id: int, note: str) -> bool:
        """修改金主的感謝留言"""
        cursor = await self.db.execute(
            "UPDATE sponsor_leaderboard SET note = ? WHERE guild_id = ? AND user_id = ?",
            (note, guild_id, user_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def update_sponsor_positions(self, guild_id: int, sponsor_order: list) -> None:
        """批次更新金主的排序位置"""
        for idx, uid in enumerate(sponsor_order, 1):
            await self.db.execute(
                "UPDATE sponsor_leaderboard SET position = ? WHERE guild_id = ? AND user_id = ?",
                (idx, guild_id, uid),
            )
        await self.db.commit()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 考試系統
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def add_exam_question(self, guild_id: int, question_text: str) -> int:
        """新增考試題目，回傳新題目的 ID"""
        async with self.db.execute(
            "INSERT INTO exam_questions (guild_id, question_text) VALUES (?, ?)",
            (guild_id, question_text)
        ) as cursor:
            await self.db.commit()
            return cursor.lastrowid

    async def delete_exam_question(self, guild_id: int, question_id: int) -> bool:
        """刪除特定考試題目"""
        async with self.db.execute(
            "DELETE FROM exam_questions WHERE id = ? AND guild_id = ?",
            (question_id, guild_id)
        ) as cursor:
            await self.db.commit()
            return cursor.rowcount > 0

    async def get_exam_questions(self, guild_id: int) -> list[dict]:
        """取得該伺服器所有考試題目"""
        async with self.db.execute(
            "SELECT * FROM exam_questions WHERE guild_id = ? ORDER BY id ASC",
            (guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def create_exam_session(self, thread_id: int, user_id: int, guild_id: int) -> None:
        """建立新的考試會話"""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "INSERT OR REPLACE INTO active_exams (thread_id, user_id, guild_id, current_question_index, answers, started_at) VALUES (?, ?, ?, 0, '{}', ?)",
            (thread_id, user_id, guild_id, now)
        )
        await self.db.commit()

    async def get_exam_session(self, thread_id: int) -> dict | None:
        """取得特定討論串的考試會話"""
        async with self.db.execute(
            "SELECT * FROM active_exams WHERE thread_id = ?",
            (thread_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_exam_session(self, thread_id: int, current_question_index: int, answers: dict) -> None:
        """更新考試會話的進度與答案"""
        answers_str = json.dumps(answers, ensure_ascii=False)
        await self.db.execute(
            "UPDATE active_exams SET current_question_index = ?, answers = ? WHERE thread_id = ?",
            (current_question_index, answers_str, thread_id)
        )
        await self.db.commit()

    async def delete_exam_session(self, thread_id: int) -> None:
        """刪除/完成考試會話"""
        await self.db.execute(
            "DELETE FROM active_exams WHERE thread_id = ?",
            (thread_id,)
        )
        await self.db.commit()

    async def is_feature_enabled(self, guild_id: int, feature_name: str, default: bool = True) -> bool:
        """檢查特定伺服器功能是否啟用"""
        if not self.db:
            return default
        try:
            async with self.db.execute(
                "SELECT enabled FROM guild_features WHERE guild_id = ? AND feature_name = ?",
                (guild_id, feature_name)
            ) as cursor:
                row = await cursor.fetchone()
                if row is not None:
                    return bool(row[0])
        except Exception:
            pass
        return default

    async def set_feature_enabled(self, guild_id: int, feature_name: str, enabled: bool):
        """設定伺服器功能啟用狀態"""
        if not self.db:
            return
        try:
            val = 1 if enabled else 0
            await self.db.execute(
                "INSERT OR REPLACE INTO guild_features (guild_id, feature_name, enabled) VALUES (?, ?, ?)",
                (guild_id, feature_name, val)
            )
            await self.db.commit()
        except Exception as e:
            print(f"Error setting guild feature {feature_name}: {e}")

    async def is_user_say_blocked(self, guild_id: int, user_id: int) -> bool:
        """檢查特定使用者在該伺服器是否被禁用 say 指令"""
        if not self.db:
            return False
        try:
            async with self.db.execute(
                "SELECT 1 FROM blocked_users_say WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            ) as cursor:
                row = await cursor.fetchone()
                return row is not None
        except Exception:
            return False

    async def set_user_say_blocked(self, guild_id: int, user_id: int, blocked: bool):
        """設定/解除禁用某個使用者使用 say 指令"""
        if not self.db:
            return
        try:
            if blocked:
                await self.db.execute(
                    "INSERT OR IGNORE INTO blocked_users_say (guild_id, user_id) VALUES (?, ?)",
                    (guild_id, user_id)
                )
            else:
                await self.db.execute(
                    "DELETE FROM blocked_users_say WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id)
                )
            await self.db.commit()
        except Exception as e:
            print(f"Error updating blocked_users_say: {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 競爭者/對手名單系統
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def get_competitor_settings(self, guild_id: int) -> dict | None:
        """取得伺服器競爭者名單頻道與訊息設定"""
        async with self.db.execute(
            "SELECT * FROM competitor_settings WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def set_competitor_settings(self, guild_id: int, channel_id: int, message_id: int) -> None:
        """儲存或更新競爭者名單頻道與訊息設定"""
        await self.db.execute(
            "INSERT OR REPLACE INTO competitor_settings (guild_id, channel_id, message_id) VALUES (?, ?, ?)",
            (guild_id, channel_id, message_id),
        )
        await self.db.commit()

    async def get_competitors(self, guild_id: int) -> list:
        """取得伺服器所有競爭者成員"""
        async with self.db.execute(
            "SELECT * FROM competitor_roster WHERE guild_id = ? ORDER BY created_at ASC",
            (guild_id,),
        ) as cursor:
            return await cursor.fetchall()

    async def add_competitor(self, guild_id: int, discord_id: int, roblox_id: str) -> None:
        """新增競爭者成員"""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "INSERT OR REPLACE INTO competitor_roster (guild_id, discord_id, roblox_id, created_at) VALUES (?, ?, ?, ?)",
            (guild_id, discord_id, roblox_id, now),
        )
        await self.db.commit()

    async def remove_competitor(self, guild_id: int, discord_id: int) -> bool:
        """移除競爭者成員"""
        cursor = await self.db.execute(
            "DELETE FROM competitor_roster WHERE guild_id = ? AND discord_id = ?",
            (guild_id, discord_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0
