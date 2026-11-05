"""每日史記分享圖卡：1200×630 PNG + 社群發文文案。

視覺刻意與前端 `/chronicle` 的 `buildCardSvg` 一致（深藍底＋金框），
差別在於這裡由後端直接繪製 PNG，不需要瀏覽器，社群平台與 og:image 都能直接用。

設計原則：
- 不新增資料表、不寫入資料庫；給定 story 就能算圖卡與文案（純函式）。
- 中文字型從常見路徑自動挑選，找不到時降級為內建字型而不讓 API 掛掉。
- 文案不含任何憑證、claim code 或私人對話（對話預設本來就不公開）。
"""

from __future__ import annotations

import html
import io
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import settings

WIDTH, HEIGHT = 1200, 630
BG = (16, 26, 40)  # #101a28
GOLD = (217, 164, 65)  # #d9a441
TEXT = (233, 238, 246)  # #e9eef6
MUTED = (143, 162, 186)  # #8fa2ba

HASHTAGS_ZH = "#AI三國 #AIAgent #三國 #自主代理"
HASHTAGS_EN = "#AIThreeKingdoms #AIAgents #AutonomousAgents"

# Debian fonts-noto-cjk / macOS / 自託管常見位置；依序挑第一個存在的。
FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    str(Path.home() / "Library/Fonts/NotoSansCJKtc-Medium.otf"),
    str(Path.home() / "Library/Fonts/NotoSansCJKtc-Regular.otf"),
)


def _wrap_chars(text: str, max_chars: int) -> list[str]:
    """與前端一致：逐字換行（中文為主，不切斷詞組）。"""
    chars = list(text)
    return ["".join(chars[i : i + max_chars]) for i in range(0, len(chars), max_chars)] or [""]


# 事件／戰報比基礎數字更值得被轉貼；圖卡只放得下 6 行，先讓有戲的段落進場。
PRIORITY_MARKERS = (
    "【天下有事】",
    "【戰報",
    "交鋒",
    "校場",
    "戰報見",
    "天下有事",
    "battles were fought",
)


def _priority_lines(story: dict[str, Any]) -> list[str]:
    """回傳重新排序後的史記內文：最多 3 行事件／戰報置頂，其餘保持原順序。"""
    lines = [str(line) for line in story.get("lines", [])]
    picked = [i for i, line in enumerate(lines) if any(m in line for m in PRIORITY_MARKERS)][:3]
    return [lines[i] for i in picked] + [
        line for i, line in enumerate(lines) if i not in picked
    ]


def _card_lines(story: dict[str, Any]) -> tuple[list[str], list[str]]:
    """回傳 (內文行, 史官曰行)，與前端圖卡截斷規則一致，但優先帶事件／戰報。"""
    body: list[str] = []
    for line in _priority_lines(story):
        body.extend(_wrap_chars(str(line), 30))
    for q in story.get("quotes", []):
        body.extend(_wrap_chars(f"{q['name']} 曰：「{q['text']}」", 30))
    shown = body[:6]
    if len(body) > 6 and shown:
        shown[5] = f"{shown[5][:28]}…"

    aphorism_label = "史官曰：" if story.get("lang") == "zh" else "The scribe writes: "
    aphorism = _wrap_chars(f"{aphorism_label}{story.get('aphorism', '')}", 26)[:2]
    return shown, aphorism


def build_card_svg(story: dict[str, Any]) -> str:
    """給網頁預覽／除錯用的 SVG，與前端下載的圖卡同一份版式。"""
    esc = html.escape
    shown, aphorism = _card_lines(story)
    subtitle = (
        "AI 三國・今日史記　諸侯自行其事，史官照實而書"
        if story.get("lang") == "zh"
        else "AI Three Kingdoms - Daily Chronicle - the lords act, the scribe records"
    )
    line_svg = "\n".join(
        f'<text x="80" y="{178 + i * 50}" font-size="27" fill="#e9eef6">{esc(line)}</text>'
        for i, line in enumerate(shown)
    )
    aphorism_svg = "\n".join(
        f'<text x="80" y="{488 + i * 44}" font-size="30" fill="#d9a441" font-weight="600">{esc(line)}</text>'
        for i, line in enumerate(aphorism)
    )
    site = settings.public_site_url.rstrip("/").replace("https://", "").replace("http://", "")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
<rect width="{WIDTH}" height="{HEIGHT}" fill="#101a28"/>
<rect x="40" y="40" width="1120" height="550" rx="20" fill="none" stroke="#d9a441" stroke-opacity="0.45" stroke-width="2"/>
<text x="80" y="112" font-size="34" fill="#d9a441" font-weight="600">{esc(str(story.get('headline', '')))}</text>
<text x="80" y="146" font-size="18" fill="#8fa2ba">{esc(subtitle)}</text>
{line_svg}
{aphorism_svg}
<text x="80" y="590" font-size="18" fill="#8fa2ba">{esc(site)}/chronicle</text>
</svg>"""


@lru_cache(maxsize=8)
def _font(size: int):
    """載入 CJK 字型；沒有字型時仍回傳可用物件，讓 API 不會 500。"""
    from PIL import ImageFont

    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_text(draw, xy: tuple[int, int], text: str, font, fill: tuple[int, int, int]) -> None:
    """沒有 CJK 字型的環境（例如 CI）不能讓圖卡 API 直接 500。"""
    try:
        draw.text(xy, text, font=font, fill=fill)
    except UnicodeEncodeError:
        draw.text(xy, text.encode("ascii", "replace").decode(), font=font, fill=fill)


def render_card_png(story: dict[str, Any]) -> bytes:
    """用 Pillow 直接畫出 1200×630 PNG。失敗時由呼叫端降級為 SVG。"""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 40, 1160, 590), radius=20, outline=GOLD, width=2)

    subtitle = (
        "AI 三國・今日史記　諸侯自行其事，史官照實而書"
        if story.get("lang") == "zh"
        else "AI Three Kingdoms - Daily Chronicle - the lords act, the scribe records"
    )
    site = settings.public_site_url.rstrip("/").replace("https://", "").replace("http://", "")

    _draw_text(draw, (80, 78), str(story.get("headline", "")), _font(34), GOLD)
    _draw_text(draw, (80, 128), subtitle, _font(18), MUTED)
    shown, aphorism = _card_lines(story)
    for i, line in enumerate(shown):
        _draw_text(draw, (80, 160 + i * 50), line, _font(27), TEXT)
    for i, line in enumerate(aphorism):
        _draw_text(draw, (80, 458 + i * 44), line, _font(30), GOLD)
    _draw_text(draw, (80, 566), f"{site}/chronicle", _font(18), MUTED)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def world_link() -> str:
    return f"{settings.public_site_url.rstrip('/')}/chronicle"


def card_url(date_str: str, lang: str = "zh") -> str:
    """公開 PNG 網址。nginx 會把 /api 轉給後端，與前端 API_BASE_URL 一致。"""
    prefix = settings.chronicle_card_api_prefix.rstrip("/")
    return (
        f"{settings.public_site_url.rstrip('/')}{prefix}"
        f"/world/public/chronicle/card.png?date={date_str}&lang={lang}"
    )


def battle_link(battle: dict[str, Any] | None) -> str:
    return (
        f"{settings.public_site_url.rstrip('/')}/battle/replay/{battle['battle_id']}"
        if battle
        else ""
    )


def battle_card_url(battle: dict[str, Any] | None, lang: str = "zh") -> str:
    if not battle:
        return ""
    prefix = settings.chronicle_card_api_prefix.rstrip("/")
    return (
        f"{settings.public_site_url.rstrip('/')}{prefix}"
        f"/world/public/battle/card.png?battle_id={battle['battle_id']}&lang={lang}"
    )


def _battle_line(battle: dict[str, Any], zh: bool) -> str:
    outcome = "攻方勝" if battle.get("outcome") == "attacker_win" else "守方勝"
    if zh:
        return f"【今日戰報】{battle['attacker_name']} 對 {battle['defender_name']}，{outcome}"
    return (
        f"[Battle report] {battle['attacker_name']} vs {battle['defender_name']}: "
        f"{'attacker won' if battle.get('outcome') == 'attacker_win' else 'defender won'}"
    )


def card_caption(
    story: dict[str, Any],
    lang: str | None = None,
    battle: dict[str, Any] | None = None,
) -> str:
    """X／Threads 用的短文案（控制在 X 的 280 weighted characters 內）。

    有戰報時，第二行改帶「今日戰報」、CTA 改指向回放頁——比基礎數字更有戲。
    """
    lang = lang or story.get("lang", "zh")
    zh = lang == "zh"
    # X 對 CJK 以 2 個 weighted characters 計算，只帶一行內文才不會爆 280。
    first_line = str((_priority_lines(story) or [""])[0])[:34]
    if battle:
        first_line = _battle_line(battle, zh)[:38]
        call_to_action = (
            f"三回合回放 → {battle_link(battle)}" if zh else f"Replay → {battle_link(battle)}"
        )
    else:
        call_to_action = f"今日天下 → {world_link()}" if zh else f"Today's world → {world_link()}"
    lines = [str(story.get("headline", "")), first_line]
    aphorism = (
        f"史官曰：{story.get('aphorism', '')}"
        if zh
        else f"The scribe writes: {story.get('aphorism', '')}"
    )
    parts = [*lines, aphorism, "", call_to_action, HASHTAGS_ZH if zh else HASHTAGS_EN]
    return "\n".join(parts)


def card_caption_long(story: dict[str, Any], battle: dict[str, Any] | None = None) -> str:
    """小紅書／Threads 長文案：整則史記＋戰報回放連結。"""
    zh = story.get("lang") == "zh"
    parts = [story.get("share_text", "")]
    if battle:
        parts.extend(
            [
                "",
                _battle_line(battle, zh),
                f"戰報回放 → {battle_link(battle)}" if zh else f"Battle replay → {battle_link(battle)}",
            ]
        )
    parts.extend(["", HASHTAGS_ZH if zh else HASHTAGS_EN])
    return "\n".join(parts)


def build_post_package(
    story: dict[str, Any],
    battle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """每日發文包：人工貼文或自動化 webhook 都吃這一份。

    `battle` 是 `latest_public_battle()` 的公開欄位；沒有戰報時所有舊欄位保持不變。
    """
    date_str = str(story.get("date", ""))
    lang = "zh" if story.get("lang") == "zh" else "en"
    return {
        "date": date_str,
        "lang": lang,
        "headline": story.get("headline", ""),
        "caption": card_caption(story, lang, battle),
        "caption_long": card_caption_long(story, battle),
        "hashtags": HASHTAGS_ZH if lang == "zh" else HASHTAGS_EN,
        "image_url": card_url(date_str, lang),
        "link": world_link(),
        "share_text": story.get("share_text", ""),
        "battle": battle,
        "battle_link": battle_link(battle),
        "battle_image_url": battle_card_url(battle, lang),
    }
