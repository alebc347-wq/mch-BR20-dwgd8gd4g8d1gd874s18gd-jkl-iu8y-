"""
全域設定 & 常數
Discord Bot 統一設計系統
"""

import os
from dotenv import load_dotenv

# 載入絕對路徑的 .env，並允許覆寫系統環境變數以防干擾
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=env_path, override=True)

# ─── Bot 基本設定 ───────────────────────────────────────────
BOT_TOKEN = os.getenv("DISCORD_TOKEN", "")
BOT_PREFIX = os.getenv("BOT_PREFIX", ".")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# ─── Lavalink 音樂設定 ──────────────────────────────────────
LAVALINK_HOST = os.getenv("LAVALINK_HOST", "lavalinkv4.serenetia.com")
LAVALINK_PORT = int(os.getenv("LAVALINK_PORT", "443"))
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "https://seretia.link/discord")

# ─── 品牌配色 (Hex → int) ───────────────────────────────────
class Colors:
    """統一的 Embed 色彩系統"""
    PRIMARY    = 0x5865F2   # Discord 藍紫 — 一般/資訊
    SUCCESS    = 0x57F287   # 翠綠 — 成功操作
    WARNING    = 0xFEE75C   # 琥珀黃 — 警告
    ERROR      = 0xED4245   # 猩紅 — 錯誤/封禁
    INFO       = 0x5865F2   # 藍紫 — 資訊
    MUSIC      = 0xB967FF   # 夢幻紫 — 音樂系統
    GAME       = 0x00D4AA   # 青色 — 遊戲系統
    GIVEAWAY   = 0xFF6B9D   # 粉紅 — 抽獎系統
    LOG_JOIN   = 0x57F287   # 綠色 — 成員加入
    LOG_LEAVE  = 0x99AAB5   # 灰色 — 成員離開
    LOG_EDIT   = 0x3498DB   # 藍色 — 訊息編輯
    LOG_DELETE = 0xE74C3C   # 紅色 — 訊息刪除
    LOG_ROLE   = 0xF1C40F   # 金色 — 角色變更
    LOG_VOICE  = 0x00CED1   # 青藍 — 語音動態
    LOG_CHAN   = 0x2ECC71   # 綠色 — 頻道變更
    KICK       = 0xFF9800   # 橘色 — 踢出
    BAN        = 0xB71C1C   # 深紅 — 封禁
    UNBAN      = 0x4CAF50   # 綠色 — 解封
    TIMEOUT    = 0x9C27B0   # 紫色 — 禁言
    WARN       = 0xFFC107   # 黃色 — 警告
    PURGE      = 0xFF5722   # 深橘 — 清除訊息
    AUTOMOD    = 0x2196F3   # 藍色 — 自動審核

# ─── Emoji 系統 ─────────────────────────────────────────────
class Emoji:
    """統一的 Emoji 常數"""
    # 狀態
    SUCCESS    = "✅"
    ERROR      = "❌"
    WARNING    = "⚠️"
    INFO       = "ℹ️"
    LOADING    = "⏳"
    
    # 管理
    KICK       = "🥾"
    BAN        = "🔨"
    UNBAN      = "🔓"
    TIMEOUT    = "🔇"
    WARN       = "⚠️"
    PURGE      = "🧹"
    LOCK       = "🔒"
    UNLOCK     = "🔓"
    SHIELD     = "🛡️"
    
    # 日誌
    JOIN       = "📥"
    LEAVE      = "📤"
    EDIT       = "✏️"
    DELETE     = "🗑️"
    ROLE       = "🎭"
    VOICE      = "🎙️"
    CHANNEL    = "#️⃣"
    TYPING     = "💬"
    MESSAGE    = "💬"
    
    # 音樂
    MUSIC      = "🎵"
    PLAY       = "▶️"
    PAUSE      = "⏸️"
    STOP       = "⏹️"
    SKIP       = "⏭️"
    PREV       = "⏮️"
    SHUFFLE    = "🔀"
    LOOP       = "🔁"
    LOOP_ONE   = "🔂"
    VOLUME     = "🔊"
    QUEUE      = "📋"
    SEARCH     = "🔍"
    
    # 娛樂
    GAME       = "🎮"
    DICE       = "🎲"
    CARDS      = "🃏"
    TROPHY     = "🏆"
    STAR       = "⭐"
    CROWN      = "👑"
    GIFT       = "🎁"
    PARTY      = "🎉"
    COIN       = "🪙"
    MAGIC      = "🔮"
    
    # 導航
    LEFT       = "◀️"
    RIGHT      = "▶️"
    FIRST      = "⏪"
    LAST       = "⏩"
    LINK       = "🔗"
    HOME       = "🏠"
    
    # 撲克
    SPADE      = "♠️"
    HEART      = "♥️"
    DIAMOND    = "♦️"
    CLUB       = "♣️"

# ─── 徽章圖片 URL ───────────────────────────────────────────
# 注意：這些 URL 需要在部署時更新為實際的圖片 URL
# 你可以上傳到 imgur、Discord CDN、或你自己的伺服器
# 暫時使用本地路徑，部署時替換為 HTTPS URL
class BadgeImages:
    """
    徽章圖片 URL 映射表
    部署時將這些替換為實際的圖片 URL
    暫時使用本地路徑
    """
    # 日誌系統
    ROLE_CHANGE    = "https://files.catbox.moe/bzho1v.png"  # 角色變更
    MSG_DELETED    = "https://files.catbox.moe/g8keho.png"  # 訊息被刪
    TYPING         = "https://files.catbox.moe/bp14e4.png"       # 正在輸入
    NEW_MESSAGE    = "https://files.catbox.moe/hf7tva.png"  # 有新訊息
    MEMBER_JOIN    = "https://files.catbox.moe/qirmkp.png"  # 成員加入
    MEMBER_LEAVE   = "https://files.catbox.moe/dq3lcp.png" # 成員離開
    MSG_EDIT       = "https://files.catbox.moe/l394h8.png"     # 訊息編輯
    VOICE_ACTIVITY = "https://files.catbox.moe/1oenc5.png"        # 語音動態
    CHANNEL_CHANGE = "https://files.catbox.moe/hf7tva.png"  # 頻道變更
    STATUS_CHANGE  = "https://files.catbox.moe/7qnz0n.png"  # 狀態改變
    RESTART        = "https://files.catbox.moe/2oet1b.png"  # 系統重啟
    
    # 管理系統
    KICK           = "https://files.catbox.moe/qpe030.png"         # 踢出用戶
    BAN            = "https://files.catbox.moe/rvn2mg.png"          # 封禁用戶
    UNBAN          = "https://files.catbox.moe/gmr5kr.png"        # 解除封禁
    TIMEOUT        = "https://files.catbox.moe/yle9dg.png"      # 禁言處罰
    WARN           = "https://files.catbox.moe/67gol6.png"         # 警告處分
    PURGE          = "https://files.catbox.moe/21x7z0.png"        # 清除訊息
    AUTOMOD        = "https://files.catbox.moe/67gol6.png"         # 自動審核
    
    # 娛樂 & 音樂
    MUSIC          = "https://files.catbox.moe/60d0si.png"        # 正在播放
    GAME           = "https://files.catbox.moe/4bfko7.png"         # 迷你遊戲
    GIVEAWAY       = "https://files.catbox.moe/0ei1bi.png"     # 抽獎活動
    SPONSOR        = "https://files.catbox.moe/1yt0v1.png"     # 金主排行榜
    
    # 通用
    SUCCESS        = "https://files.catbox.moe/4bfko7.png"         # 操作成功
    ERROR          = "https://files.catbox.moe/pn6md9.png"          # 操作失敗


# ─── 自動審核預設詞彙 ───────────────────────────────────────
DEFAULT_BAD_WORDS = [
    # 在這裡添加你的伺服器需要過濾的詞彙
    # 例如: "spam", "垃圾"
]

# ─── 警告系統預設設定 ────────────────────────────────────────
DEFAULT_WARN_ACTIONS = {
    3: "timeout_1h",    # 3 次警告 → 禁言 1 小時
    5: "timeout_1d",    # 5 次警告 → 禁言 1 天
    7: "kick",          # 7 次警告 → 踢出
    10: "ban",          # 10 次警告 → 封禁
}

# ─── 時間格式解析 ───────────────────────────────────────────
import re
from datetime import timedelta

def parse_time(time_str: str) -> timedelta | None:
    """
    解析時間字串為 timedelta
    支援格式: 5s, 10min, 2h, 7d, 3w, 2m, 1y (未填單位預設為 min)
    """
    time_str = time_str.strip().lower()
    if time_str.isdigit():
        return timedelta(minutes=int(time_str))
        
    patterns = {
        r"^(\d+)s$": "seconds",
        r"^(\d+)min$": "minutes",
        r"^(\d+)h$": "hours",
        r"^(\d+)d$": "days",
        r"^(\d+)w$": "weeks",
    }
    
    for pattern, unit in patterns.items():
        match = re.match(pattern, time_str)
        if match:
            value = int(match.group(1))
            return timedelta(**{unit: value})
            
    # 特殊處理月和年 (timedelta 不原生支援，需轉換為天數)
    match_m = re.match(r"^(\d+)m$", time_str)
    if match_m:
        return timedelta(days=int(match_m.group(1)) * 30)
        
    match_y = re.match(r"^(\d+)y$", time_str)
    if match_y:
        return timedelta(days=int(match_y.group(1)) * 365)
    
    return None

def format_timedelta(td: timedelta) -> str:
    """將 timedelta 格式化為人類可讀的中文字串"""
    total_seconds = int(td.total_seconds())
    
    if total_seconds < 60:
        return f"{total_seconds} 秒"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        return f"{minutes} 分鐘"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        return f"{hours} 小時"
        
    days = total_seconds // 86400
    if days >= 365:
        years = days // 365
        rem_days = days % 365
        if rem_days == 0:
            return f"{years} 年"
        return f"{years} 年 {rem_days} 天"
    elif days >= 30:
        months = days // 30
        rem_days = days % 30
        if rem_days == 0:
            return f"{months} 個月"
        return f"{months} 個月 {rem_days} 天"
    else:
        return f"{days} 天"

def format_relative_time(seconds_ago: float) -> str:
    """將秒數格式化為相對時間"""
    if seconds_ago < 60:
        return f"{int(seconds_ago)} 秒前"
    elif seconds_ago < 3600:
        return f"{int(seconds_ago // 60)} 分鐘前"
    elif seconds_ago < 86400:
        return f"{int(seconds_ago // 3600)} 小時前"
    else:
        return f"{int(seconds_ago // 86400)} 天前"
