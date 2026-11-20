"""
倉鼠勇者 3.0 — 程式化圖片渲染引擎 (Visual Card Engine)
採用深石板 × 暖琥珀 / Pro 金箔編輯風視覺語言：
- 純記憶體 PNG 輸出 (io.BytesIO)，零磁碟寫入
- 所有渲染透過 asyncio.to_thread 背景執行，不阻塞 Discord 事件迴圈
- 字型物件 LRU 快取，單張卡片渲染時間約 15~40 ms
"""

import asyncio
import functools
import io
import os
from typing import Sequence
from PIL import Image, ImageDraw, ImageFont

# ─── 3.0 品牌調色盤（節制高對比：2 主中性色 + 1 品牌琥珀色 + 語意狀態色）───
BG_BASE       = (17, 19, 24)      # #111318 深石板底色
BG_SURFACE    = (25, 29, 38)      # #191D26 卡片內層區塊
BG_ELEVATED   = (32, 37, 49)      # #202531 強調數據區塊
BORDER_SUBTLE = (46, 53, 68)      # #2E3544 細邊框
BORDER_PRO    = (232, 185, 49)    # #E8B931 Pro 金箔邊框

ACCENT_AMBER  = (245, 166, 35)    # #F5A623 倉鼠暖琥珀主強調色
ACCENT_PRO    = (232, 185, 49)    # #E8B931 Pro 疾速金
ACCENT_OK     = (46, 204, 113)    # #2ECC71 健康 / 正常
ACCENT_WARN   = (243, 156, 18)    # #F39C12 警告
ACCENT_ERR    = (224, 90, 71)     # #E05A47 異常

TEXT_PRIMARY  = (243, 245, 248)   # #F3F5F8 主文字
TEXT_SECONDARY= (169, 178, 194)   # #A9B2C2 次文字
TEXT_MUTED    = (114, 124, 144)   # #727C90 標籤文字
TEXT_DARK     = (17, 19, 24)      # 亮色徽章上的深色字

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@functools.lru_cache(maxsize=4)
def _find_font_path(bold: bool = True) -> str | None:
    """自動尋找系統支援繁體中文的字型（Windows / Linux 容器相容）"""
    candidates = [
        # Windows 繁體中文微軟正黑體
        "C:/Windows/Fonts/msjhbd.ttc" if bold else "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/mingliu.ttc",
        # Linux / Docker 常見 CJK 字型
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        # 專案內建字型
        os.path.join(_ROOT_DIR, "assets", "arialbd.ttf"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


@functools.lru_cache(maxsize=64)
def _get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _find_font_path(bold=bold)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _truncate(text: str, max_len: int) -> str:
    text = str(text or "")
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _to_png_bytes(img: Image.Image) -> io.BytesIO:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    bg_color: tuple[int, int, int],
    text_color: tuple[int, int, int],
    font_size: int = 15,
    pad_x: int = 14,
    pad_y: int = 6,
) -> int:
    """繪製單一語意狀態徽章，回傳右邊界 X 座標"""
    font = _get_font(font_size, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    w = tw + pad_x * 2
    h = th + pad_y * 2
    draw.rounded_rectangle([x, y, x + w, y + h], radius=6, fill=bg_color)
    draw.text((x + pad_x, y + pad_y - bbox[1]), text, font=font, fill=text_color)
    return x + w


def _draw_card_frame(width: int, height: int, accent: tuple[int, int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """建立 3.0 統一基底畫布：深石板底 + 左側結構強調條 + 細邊框"""
    img = Image.new("RGB", (width, height), BG_BASE)
    draw = ImageDraw.Draw(img)
    # 外框細線
    draw.rounded_rectangle([1, 1, width - 2, height - 2], radius=14, outline=BORDER_SUBTLE, width=2)
    # 頂部結構強調細條 (4px)
    draw.rectangle([16, 0, width - 16, 4], fill=accent)
    return img, draw


def _paste_rounded_avatar(base: Image.Image, avatar_bytes: bytes | None, box: tuple[int, int, int], fallback_text: str = "H") -> None:
    """將頭像裁切為圓角方塊並貼到卡片上；若無圖片則繪製字母縮寫方塊"""
    x, y, size = box
    if avatar_bytes:
        try:
            av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, size, size], radius=18, fill=255)
            base.paste(av, (x, y), mask)
            return
        except Exception:
            pass

    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle([x, y, x + size, y + size], radius=18, fill=BG_ELEVATED, outline=BORDER_SUBTLE, width=2)
    ch = (fallback_text[:1] or "H").upper()
    font = _get_font(int(size * 0.45), bold=True)
    bbox = draw.textbbox((0, 0), ch, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x + (size - tw) // 2, y + (size - th) // 2 - bbox[1]), ch, font=font, fill=ACCENT_AMBER)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 3.0 幫助中樞主視覺卡
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _render_help_banner_sync(is_pro: bool, guild_count: int, cog_count: int, ws_ms: float) -> io.BytesIO:
    W, H = 920, 340
    accent = ACCENT_PRO if is_pro else ACCENT_AMBER
    img, draw = _draw_card_frame(W, H, accent)

    # 左側品牌與版本標頭
    _draw_pill(draw, 36, 32, "HAMSTER HERO 3.0", accent, TEXT_DARK, font_size=14)
    tier_label = "PRO 疾速通道" if is_pro else "FREE 標準方案"
    _draw_pill(draw, 220, 32, tier_label, BG_ELEVATED, accent, font_size=14)

    draw.text((36, 76), "倉鼠勇者 3.0 指令中樞", font=_get_font(36, bold=True), fill=TEXT_PRIMARY)
    draw.text((36, 126), "去蕪存菁・零洗版干擾・全程式化高速視覺卡片", font=_get_font(17, bold=False), fill=TEXT_SECONDARY)

    # 下方非對稱數據列 (左寬主卡 + 右 3 組實時指標)
    draw.rounded_rectangle([36, 174, 420, 304], radius=10, fill=BG_SURFACE, outline=BORDER_SUBTLE, width=1)
    draw.text((56, 190), "目前通道速度", font=_get_font(14, bold=False), fill=TEXT_MUTED)
    speed_main = "0 秒極速連發" if is_pro else "3.0 秒標準節流"
    draw.text((56, 214), speed_main, font=_get_font(26, bold=True), fill=accent)
    sub_hint = "已解鎖 Pro 全速指令與 24/7 音樂" if is_pro else "使用 /plan 查看升級 Pro 疾速方案"
    draw.text((56, 260), sub_hint, font=_get_font(14, bold=False), fill=TEXT_SECONDARY)

    metrics = [
        ("即時延遲", f"{ws_ms:.0f} ms", ACCENT_OK if ws_ms < 120 else ACCENT_WARN),
        ("核心模組", f"{cog_count} 個", TEXT_PRIMARY),
        ("服務群組", f"{guild_count} 個", TEXT_PRIMARY),
    ]
    mx = 444
    mw = 140
    for label, val, val_col in metrics:
        draw.rounded_rectangle([mx, 174, mx + mw, 304], radius=10, fill=BG_SURFACE, outline=BORDER_SUBTLE, width=1)
        draw.text((mx + 18, 194), label, font=_get_font(14, bold=False), fill=TEXT_MUTED)
        draw.text((mx + 18, 228), val, font=_get_font(26, bold=True), fill=val_col)
        mx += mw + 16

    return _to_png_bytes(img)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 3.0 雙方案對比圖卡 (Free vs Pro)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _render_plan_card_sync(guild_name: str, is_pro: bool, expires_at: str = "") -> io.BytesIO:
    W, H = 960, 440
    accent = ACCENT_PRO if is_pro else ACCENT_AMBER
    img, draw = _draw_card_frame(W, H, accent)

    draw.text((36, 28), "倉鼠勇者 3.0 雙方案架構", font=_get_font(32, bold=True), fill=TEXT_PRIMARY)
    status_txt = f"伺服器：{_truncate(guild_name, 26)}  •  目前方案：{'PRO 疾速版' if is_pro else 'FREE 免費版'}"
    draw.text((36, 72), status_txt, font=_get_font(16, bold=False), fill=TEXT_SECONDARY)

    # 左欄：FREE 免費方案
    left_box = [36, 114, 464, 404]
    draw.rounded_rectangle(left_box, radius=12, fill=BG_SURFACE, outline=ACCENT_AMBER if not is_pro else BORDER_SUBTLE, width=2 if not is_pro else 1)
    draw.text((60, 134), "FREE 免費方案", font=_get_font(24, bold=True), fill=TEXT_PRIMARY)
    if not is_pro:
        _draw_pill(draw, 330, 134, "使用中", BG_ELEVATED, ACCENT_AMBER, font_size=13)
    draw.line([(60, 176), (440, 176)], fill=BORDER_SUBTLE, width=1)

    free_items = [
        ("指令速率", "3.0 秒標準節流"),
        ("核心功能", "管理、娛樂、經濟、天災速報"),
        ("視覺圖卡", "標準 3.0 程式圖片卡片"),
        ("音樂系統", "單曲播放與 5 首內歌單"),
        ("日誌防洗版", "自動過濾高頻垃圾事件"),
    ]
    fy = 194
    for k, v in free_items:
        draw.text((60, fy), k, font=_get_font(15, bold=True), fill=TEXT_MUTED)
        draw.text((168, fy), v, font=_get_font(15, bold=False), fill=TEXT_SECONDARY)
        fy += 38

    # 右欄：PRO 疾速方案（主角強調，金箔邊框）
    right_box = [496, 114, 924, 404]
    draw.rounded_rectangle(right_box, radius=12, fill=BG_ELEVATED, outline=BORDER_PRO, width=2)
    draw.text((520, 134), "PRO 疾速方案", font=_get_font(24, bold=True), fill=ACCENT_PRO)
    badge_txt = "已啟用" if is_pro else "極速推薦"
    _draw_pill(draw, 804, 134, badge_txt, ACCENT_PRO, TEXT_DARK, font_size=13)
    draw.line([(520, 176), (900, 176)], fill=(70, 62, 40), width=1)

    pro_items = [
        ("指令速率", "0 秒無冷卻疾速通道"),
        ("執行優先權", "快取直通・最高處理優先級"),
        ("視覺圖卡", "Pro 金箔專屬卡片與高優先渲染"),
        ("音樂系統", "24/7 不斷線 + 無限歌單解析"),
        ("到期資訊", _truncate(expires_at, 20) if (is_pro and expires_at) else "輸入金鑰即時開通"),
    ]
    py = 194
    for k, v in pro_items:
        draw.text((520, py), k, font=_get_font(15, bold=True), fill=ACCENT_PRO)
        draw.text((628, py), v, font=_get_font(15, bold=False), fill=TEXT_PRIMARY)
        py += 38

    return _to_png_bytes(img)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 3.0 極速測速圖卡 (/ping)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _render_ping_card_sync(ws_ms: float, db_ms: float, is_pro: bool) -> io.BytesIO:
    W, H = 760, 260
    accent = ACCENT_PRO if is_pro else ACCENT_AMBER
    img, draw = _draw_card_frame(W, H, accent)

    _draw_pill(draw, 32, 28, "SPEED TEST 3.0", accent, TEXT_DARK, font_size=13)
    tier_tag = "PRO 疾速通道 (0s)" if is_pro else "FREE 標準通道 (3.0s)"
    _draw_pill(draw, 190, 28, tier_tag, BG_ELEVATED, accent, font_size=13)

    # 左側 WS 延遲主數字
    ws_col = ACCENT_OK if ws_ms < 120 else (ACCENT_WARN if ws_ms < 220 else ACCENT_ERR)
    draw.text((32, 74), "Discord 閘道延遲", font=_get_font(15, bold=False), fill=TEXT_MUTED)
    draw.text((32, 98), f"{ws_ms:.1f} ms", font=_get_font(44, bold=True), fill=ws_col)

    # 右側 SQLite 延遲
    db_col = ACCENT_OK if db_ms < 10 else ACCENT_WARN
    draw.text((400, 74), "SQLite 資料庫探針", font=_get_font(15, bold=False), fill=TEXT_MUTED)
    draw.text((400, 98), f"{db_ms:.2f} ms", font=_get_font(44, bold=True), fill=db_col)

    # 底部延遲進度刻度條
    bar_x, bar_y, bar_w, bar_h = 32, 186, 696, 16
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=8, fill=BG_ELEVATED)
    ratio = min(max(ws_ms / 300.0, 0.04), 1.0)
    fill_w = int(bar_w * ratio)
    draw.rounded_rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=8, fill=ws_col)

    grade = "極速響應" if ws_ms < 100 else ("連線順暢" if ws_ms < 180 else "網路延遲偏高")
    draw.text((32, 214), f"狀態判定：{grade}", font=_get_font(15, bold=False), fill=TEXT_SECONDARY)
    draw.text((535, 214), "倉鼠勇者 3.0 引擎", font=_get_font(15, bold=False), fill=TEXT_MUTED)

    return _to_png_bytes(img)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 3.0 系統健康儀表板圖卡 (/health)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _render_health_card_sync(
    ws_ms: float,
    db_ms: float,
    db_ok: bool,
    node_label: str,
    is_active: bool,
    is_resting: bool,
    lavalink_label: str,
    cog_count: int,
    uptime_str: str,
    guild_count: int,
) -> io.BytesIO:
    W, H = 920, 420
    overall_ok = is_active and db_ok and not is_resting
    accent = ACCENT_OK if overall_ok else ACCENT_WARN
    img, draw = _draw_card_frame(W, H, accent)

    draw.text((36, 28), "倉鼠勇者 3.0 系統健康儀表板", font=_get_font(30, bold=True), fill=TEXT_PRIMARY)
    badge = "ALL SYSTEMS NOMINAL" if overall_ok else "STANDBY / ATTENTION"
    _draw_pill(draw, 640, 32, badge, accent, TEXT_DARK, font_size=13)

    # 上排 3 個核心數據格
    top_cards = [
        ("DISCORD WS", f"{ws_ms:.1f} ms", ACCENT_OK if ws_ms < 120 else ACCENT_WARN),
        ("SQLITE DB", f"{db_ms:.2f} ms" if db_ok else "OFFLINE", ACCENT_OK if db_ok else ACCENT_ERR),
        ("主備節點", _truncate(node_label, 14), ACCENT_OK if is_active else ACCENT_WARN),
    ]
    cx = 36
    cw = 272
    for title, val, col in top_cards:
        draw.rounded_rectangle([cx, 92, cx + cw, 210], radius=10, fill=BG_SURFACE, outline=BORDER_SUBTLE, width=1)
        draw.text((cx + 20, 110), title, font=_get_font(13, bold=True), fill=TEXT_MUTED)
        draw.text((cx + 20, 140), val, font=_get_font(28, bold=True), fill=col)
        cx += cw + 16

    # 下排 2 欄結構化詳情（非對稱：左寬右窄）
    draw.rounded_rectangle([36, 230, 580, 386], radius=10, fill=BG_SURFACE, outline=BORDER_SUBTLE, width=1)
    details = [
        ("運行模式", "低耗電休息中" if is_resting else "正常全速運行"),
        ("Lavalink 音樂池", lavalink_label),
        ("連續運行時間", uptime_str),
    ]
    dy = 250
    for k, v in details:
        draw.text((58, dy), k, font=_get_font(15, bold=True), fill=TEXT_MUTED)
        draw.text((220, dy), _truncate(v, 28), font=_get_font(16, bold=False), fill=TEXT_PRIMARY)
        dy += 42

    draw.rounded_rectangle([596, 230, 884, 386], radius=10, fill=BG_ELEVATED, outline=BORDER_SUBTLE, width=1)
    draw.text((618, 250), "已載入模組", font=_get_font(14, bold=False), fill=TEXT_MUTED)
    draw.text((618, 274), f"{cog_count} Cogs", font=_get_font(26, bold=True), fill=ACCENT_AMBER)
    draw.text((618, 322), f"服務伺服器：{guild_count} 個", font=_get_font(15, bold=False), fill=TEXT_SECONDARY)

    return _to_png_bytes(img)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 3.0 成員檔案視覺卡 (/userinfo)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _render_profile_card_sync(
    display_name: str,
    username: str,
    user_id: int,
    is_pro: bool,
    roles: Sequence[str],
    joined_str: str,
    created_str: str,
    avatar_bytes: bytes | None,
) -> io.BytesIO:
    W, H = 880, 320
    accent = ACCENT_PRO if is_pro else ACCENT_AMBER
    img, draw = _draw_card_frame(W, H, accent)

    _paste_rounded_avatar(img, avatar_bytes, (36, 48, 128), fallback_text=display_name)

    draw.text((190, 44), _truncate(display_name, 22), font=_get_font(32, bold=True), fill=TEXT_PRIMARY)
    draw.text((190, 88), f"@{_truncate(username, 24)}  •  ID {user_id}", font=_get_font(15, bold=False), fill=TEXT_MUTED)

    if is_pro:
        _draw_pill(draw, 190, 120, "PRO 伺服器成員", ACCENT_PRO, TEXT_DARK, font_size=13)
    else:
        _draw_pill(draw, 190, 120, "倉鼠勇者 3.0", BG_ELEVATED, ACCENT_AMBER, font_size=13)

    # 下方資訊格
    draw.rounded_rectangle([36, 200, 430, 286], radius=10, fill=BG_SURFACE, outline=BORDER_SUBTLE, width=1)
    draw.text((56, 214), "帳號建立", font=_get_font(13, bold=False), fill=TEXT_MUTED)
    draw.text((56, 238), created_str, font=_get_font(20, bold=True), fill=TEXT_PRIMARY)

    draw.rounded_rectangle([448, 200, 844, 286], radius=10, fill=BG_SURFACE, outline=BORDER_SUBTLE, width=1)
    draw.text((468, 214), "加入伺服器", font=_get_font(13, bold=False), fill=TEXT_MUTED)
    draw.text((468, 238), joined_str, font=_get_font(20, bold=True), fill=TEXT_PRIMARY)

    # 右上身分組標籤（最多 3 個）
    rx = 340
    for rname in list(roles)[:3]:
        label = _truncate(rname, 12)
        if rx > 740:
            break
        rx = _draw_pill(draw, rx, 120, label, BG_SURFACE, TEXT_SECONDARY, font_size=13, pad_x=10, pad_y=5) + 8

    return _to_png_bytes(img)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. 3.0 伺服器總覽視覺卡 (/serverinfo)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _render_server_card_sync(
    guild_name: str,
    guild_id: int,
    is_pro: bool,
    member_count: int,
    online_count: int,
    text_count: int,
    voice_count: int,
    role_count: int,
    boost_tier: int,
    icon_bytes: bytes | None,
) -> io.BytesIO:
    W, H = 900, 340
    accent = ACCENT_PRO if is_pro else ACCENT_AMBER
    img, draw = _draw_card_frame(W, H, accent)

    _paste_rounded_avatar(img, icon_bytes, (36, 44, 112), fallback_text=guild_name)

    draw.text((172, 42), _truncate(guild_name, 22), font=_get_font(32, bold=True), fill=TEXT_PRIMARY)
    draw.text((172, 86), f"SERVER ID {guild_id}", font=_get_font(14, bold=False), fill=TEXT_MUTED)
    plan_txt = "PRO 疾速版已啟用" if is_pro else "FREE 標準方案"
    _draw_pill(draw, 172, 114, plan_txt, ACCENT_PRO if is_pro else BG_ELEVATED, TEXT_DARK if is_pro else ACCENT_AMBER, font_size=13)

    # 4 組統計方塊
    stats = [
        ("總成員數", f"{member_count:,}", TEXT_PRIMARY),
        ("在線人數", f"{online_count:,}", ACCENT_OK),
        ("文字 / 語音", f"{text_count} / {voice_count}", TEXT_PRIMARY),
        ("身分組 / 加成", f"{role_count} / Lv.{boost_tier}", ACCENT_AMBER),
    ]
    sx = 36
    sw = 198
    for label, val, col in stats:
        draw.rounded_rectangle([sx, 186, sx + sw, 304], radius=10, fill=BG_SURFACE, outline=BORDER_SUBTLE, width=1)
        draw.text((sx + 18, 204), label, font=_get_font(14, bold=False), fill=TEXT_MUTED)
        draw.text((sx + 18, 236), val, font=_get_font(26, bold=True), fill=col)
        sx += sw + 12

    return _to_png_bytes(img)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. 3.0 版本發佈視覺卡 (/version)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _render_version_card_sync(version: str, is_pro: bool) -> io.BytesIO:
    W, H = 900, 340
    accent = ACCENT_PRO if is_pro else ACCENT_AMBER
    img, draw = _draw_card_frame(W, H, accent)

    _draw_pill(draw, 36, 32, f"RELEASE v{version}", accent, TEXT_DARK, font_size=14)
    draw.text((36, 76), "倉鼠勇者 3.0 極速視覺版", font=_get_font(36, bold=True), fill=TEXT_PRIMARY)
    draw.text((36, 126), "全面移除洗版與假延遲・雙方案高速分流・程式化圖片卡片", font=_get_font(16, bold=False), fill=TEXT_SECONDARY)

    highlights = [
        ("01 極速引擎", "Pro 記憶體直通快取，0 秒極速連發"),
        ("02 零洗版淨化", "移除打字/新訊/狀態洗版與聊天誤觸"),
        ("03 3.0 視覺卡", "高對比深石板圖卡，記憶體即時渲染"),
    ]
    hx = 36
    hw = 266
    for title, desc in highlights:
        draw.rounded_rectangle([hx, 178, hx + hw, 304], radius=10, fill=BG_SURFACE, outline=BORDER_SUBTLE, width=1)
        draw.text((hx + 18, 196), title, font=_get_font(18, bold=True), fill=accent)
        # 手動簡單換行
        line1 = desc[:14]
        line2 = desc[14:]
        draw.text((hx + 18, 232), line1, font=_get_font(14, bold=False), fill=TEXT_SECONDARY)
        if line2:
            draw.text((hx + 18, 256), line2, font=_get_font(14, bold=False), fill=TEXT_SECONDARY)
        hx += hw + 15

    return _to_png_bytes(img)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 非同步封裝 API（在背景執行緒渲染，不阻塞 Discord Gateway）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def render_help_banner(is_pro: bool, guild_count: int, cog_count: int, ws_ms: float) -> io.BytesIO:
    return await asyncio.to_thread(_render_help_banner_sync, is_pro, guild_count, cog_count, ws_ms)

async def render_plan_card(guild_name: str, is_pro: bool, expires_at: str = "") -> io.BytesIO:
    return await asyncio.to_thread(_render_plan_card_sync, guild_name, is_pro, expires_at)

async def render_ping_card(ws_ms: float, db_ms: float, is_pro: bool) -> io.BytesIO:
    return await asyncio.to_thread(_render_ping_card_sync, ws_ms, db_ms, is_pro)

async def render_health_card(
    ws_ms: float,
    db_ms: float,
    db_ok: bool,
    node_label: str,
    is_active: bool,
    is_resting: bool,
    lavalink_label: str,
    cog_count: int,
    uptime_str: str,
    guild_count: int,
) -> io.BytesIO:
    return await asyncio.to_thread(
        _render_health_card_sync,
        ws_ms, db_ms, db_ok, node_label, is_active, is_resting,
        lavalink_label, cog_count, uptime_str, guild_count,
    )

async def render_profile_card(
    display_name: str,
    username: str,
    user_id: int,
    is_pro: bool,
    roles: Sequence[str],
    joined_str: str,
    created_str: str,
    avatar_bytes: bytes | None = None,
) -> io.BytesIO:
    return await asyncio.to_thread(
        _render_profile_card_sync,
        display_name, username, user_id, is_pro, roles, joined_str, created_str, avatar_bytes,
    )

async def render_server_card(
    guild_name: str,
    guild_id: int,
    is_pro: bool,
    member_count: int,
    online_count: int,
    text_count: int,
    voice_count: int,
    role_count: int,
    boost_tier: int,
    icon_bytes: bytes | None = None,
) -> io.BytesIO:
    return await asyncio.to_thread(
        _render_server_card_sync,
        guild_name, guild_id, is_pro, member_count, online_count,
        text_count, voice_count, role_count, boost_tier, icon_bytes,
    )

async def render_version_card(version: str, is_pro: bool) -> io.BytesIO:
    return await asyncio.to_thread(_render_version_card_sync, version, is_pro)
