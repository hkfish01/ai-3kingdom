"""每日 08:00（HKT）史記圖卡發文包與推送。

X／Threads／小紅書沒有憑證時無法由後端直接發文，所以這條管線切成兩段：

1. **每天固定產出**（不需任何憑證）：確保當日史記已重算 → 產生圖卡網址、
   短文案（X／Threads）、長文案（小紅書）→ 存進 system_state，公開 API 可讀。
2. **可選推送**：設定 `CHRONICLE_CARD_WEBHOOK_URLS` 後，同一份發文包會 POST 出去，
   可直接接 n8n／Make／IFTTT 轉發到 X／Threads，或接 Discord webhook。

小紅書目前沒有公開發文 API，維持人工貼圖；文案與圖卡都由這條管線備好。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from .battle_replay import latest_public_battle
from .chronicle_card import build_post_package
from .daily_chronicle import build_story_from_db, generate_daily_chronicle, get_latest_story
from .system_state import get_state, set_state

LAST_DATE_KEY = "chronicle_card_last_date"
PACKAGE_KEY = "chronicle_card_post_latest"
RESULT_KEY = "chronicle_card_last_result"
ATTEMPTS_KEY = "chronicle_card_attempts"
SEASON_ANNOUNCEMENT_KEY = "season.announcement"

MAX_ATTEMPTS = 5
HKT = timezone(timedelta(hours=8))


def hkt_now(now: datetime | None = None) -> datetime:
    """香港時間固定 UTC+8，沒有 DST；worker 用 UTC 判斷後再換算。"""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(HKT)


def current_story(db: Session, lang: str = "zh") -> dict[str, Any]:
    """與公開 `/world/public/chronicle` 用同一份史記，避免圖卡和網頁內容不一致。"""
    story = get_latest_story(db)
    if story and story.get("lang") == lang:
        return story
    return build_story_from_db(db, lang=lang)


def current_post_package(db: Session, lang: str = "zh") -> dict[str, Any]:
    """優先回傳當天已產出的發文包；worker 尚未跑時即時算一份（不寫入）。

    舊快取包可能是在當日演武之前產出的（例如 08:00 先發文、部署後才有戰報）。
    這種情況即時把戰報補進回傳值，不必等隔天 08:00，也不改寫資料庫。
    """
    cached: dict[str, Any] | None = None
    raw = get_state(db, PACKAGE_KEY, default="")
    if raw:
        try:
            package = json.loads(raw)
            if package.get("lang") == lang:
                cached = package
        except json.JSONDecodeError:
            pass

    battle = latest_public_battle(db, lang)
    if cached and (battle is None or cached.get("battle")):
        package = cached
    else:
        story = get_latest_story(db)
        if not story or story.get("lang") != lang:
            story = build_story_from_db(db, lang=lang)
        package = build_post_package(story, battle=battle)
    return _with_audience_note(db, _with_season_notice(db, package, lang), lang)


def _insert_before_hashtags(text: str, addition: str) -> str:
    """公告要放在文案內文裡，不要擠到 hashtags 後面。"""
    rows = text.split("\n")
    at = next((i for i, row in enumerate(rows) if row.lstrip().startswith("#")), len(rows))
    for offset, line in enumerate(addition.split("\n")):
        rows.insert(at + offset, line)
    return "\n".join(rows)


def _with_season_notice(db: Session, package: dict[str, Any], lang: str) -> dict[str, Any]:
    """08:00 快取包可能比當日開季詔書／季末本紀更早產生。

    即時把公告補進回傳值（不寫入 DB、不改快取），當天的發文不必等隔天 08:00。
    這裡直接讀 `system_state` 的字串 key，避免與 season 服務互相 import。
    """
    raw = get_state(db, SEASON_ANNOUNCEMENT_KEY)
    if not raw:
        return package
    try:
        data = json.loads(raw)
        created = datetime.fromisoformat(str(data["created_at"]))
        if created.tzinfo:
            created = created.replace(tzinfo=None)
        if datetime.now(timezone.utc).replace(tzinfo=None) - created > timedelta(hours=26):
            return package
        lines = [str(x) for x in data.get("zh" if lang == "zh" else "en", [])][:2]
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return package
    if not lines:
        return package

    notice = "\n".join(lines)
    patched = dict(package)
    if lines[0] not in patched.get("caption", ""):
        patched["caption"] = _insert_before_hashtags(patched.get("caption", ""), lines[0])
    if notice not in patched.get("caption_long", ""):
        patched["caption_long"] = _insert_before_hashtags(patched.get("caption_long", ""), notice)
    patched["season_notice"] = notice
    return patched


def _with_audience_note(db: Session, package: dict[str, Any], lang: str) -> dict[str, Any]:
    """08:00 快取包可能比當日觀眾助威更早產生，即時回補（不寫入 DB）。

    讀的是「當日」bucket，對應當天 07:00 已結束的演武，不是下一場的票。
    """
    # audience 服務會 import 本模組的 hkt_now，這裡用 lazy import 避免循環。
    from .audience import audience_note

    note = audience_note(db, lang)
    if not note:
        return package
    patched = dict(package)
    if note not in patched.get("caption", ""):
        patched["caption"] = _insert_before_hashtags(patched.get("caption", ""), note)
    if note not in patched.get("caption_long", ""):
        patched["caption_long"] = _insert_before_hashtags(patched.get("caption_long", ""), note)
    patched["audience_note"] = note
    return patched


def _webhook_payload(package: dict[str, Any], kind: str) -> dict[str, Any]:
    if kind == "discord":
        return {
            "content": package["caption"],
            "embeds": [
                {
                    "title": package["headline"],
                    "url": package["link"],
                    "image": {"url": package["image_url"]},
                }
            ],
        }
    # generic：n8n / Make / IFTTT / 自建服務都能直接吃
    return {
        "type": "chronicle_card",
        "date": package["date"],
        "headline": package["headline"],
        "text": package["caption"],
        "caption_long": package["caption_long"],
        "hashtags": package["hashtags"],
        "image_url": package["image_url"],
        "link": package["link"],
        "battle": package.get("battle"),
        "battle_image_url": package.get("battle_image_url", ""),
        "package": package,
    }


def _next_attempt(db: Session, date_str: str) -> int:
    raw = get_state(db, ATTEMPTS_KEY, default="")
    count = 0
    if raw.startswith(f"{date_str}:"):
        try:
            count = int(raw.split(":", 1)[1])
        except ValueError:
            count = 0
    count += 1
    set_state(db, ATTEMPTS_KEY, f"{date_str}:{count}")
    return count


def publish_daily_post(
    db: Session,
    now: datetime | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """由 worker 每日觸發，或 admin 手動補發。回傳 status / package / deliveries。

    冪等：同一個 HKT 日期只會發一次（失敗時最多重試 MAX_ATTEMPTS 次）。
    """
    date_str = hkt_now(now).date().isoformat()
    if not force and get_state(db, LAST_DATE_KEY, default="") == date_str:
        return {
            "status": "skipped",
            "date": date_str,
            "reason": "already_published",
            "package": current_post_package(db),
        }

    # 08:00 HKT 時 worker 的 UTC 01:00 史記還沒跑；用 PR #9 的冪等 upsert 先補齊當日。
    # 校場演武排在這個時段之前，所以發文包會帶到當日戰報與回放連結。
    story = generate_daily_chronicle(db, lang="zh", force=True, date_str=date_str)
    package = build_post_package(story, battle=latest_public_battle(db, "zh"))
    set_state(db, PACKAGE_KEY, json.dumps(package, ensure_ascii=False))

    urls = [u.strip() for u in settings.chronicle_card_webhook_urls.split(",") if u.strip()]
    kind = settings.chronicle_card_webhook_type.strip().lower()
    deliveries: list[dict[str, Any]] = []
    if urls:
        payload = _webhook_payload(package, kind)
        for url in urls:
            try:
                response = httpx.post(url, json=payload, timeout=10.0)
                response.raise_for_status()
                deliveries.append({"ok": True, "status_code": response.status_code})
            except Exception as exc:  # 單一通路掛掉不影響其他通路
                deliveries.append({"ok": False, "error": str(exc)[:200]})

    failures = [d for d in deliveries if not d["ok"]]
    attempts = _next_attempt(db, date_str)
    if not urls:
        status = "prepared"
    elif failures and attempts < MAX_ATTEMPTS:
        status = "retrying"
    elif failures:
        status = "failed"
    else:
        status = "sent"

    # 成功／無需推送／重試用盡才標記當日完成，失敗時下一輪還能補發。
    if status != "retrying":
        set_state(db, LAST_DATE_KEY, date_str)
    set_state(
        db,
        RESULT_KEY,
        json.dumps(
            {
                "date": date_str,
                "status": status,
                "attempts": attempts,
                "webhooks": len(urls),
                "deliveries": deliveries,
                "channel": kind if urls else "manual",
            },
            ensure_ascii=False,
        ),
    )
    db.commit()
    return {
        "status": status,
        "date": date_str,
        "attempts": attempts,
        "channel": kind if urls else "manual",
        "deliveries": deliveries,
        "package": package,
    }


def publish_status(db: Session) -> dict[str, Any]:
    raw = get_state(db, RESULT_KEY, default="")
    result: dict[str, Any] = {}
    if raw:
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {}
    package = current_post_package(db)
    return {
        "enabled": settings.chronicle_card_enabled,
        "publish_hour_hkt": settings.chronicle_card_publish_hour_hkt,
        "webhook_configured": bool(settings.chronicle_card_webhook_urls.strip()),
        "webhook_type": settings.chronicle_card_webhook_type,
        "last_date": get_state(db, LAST_DATE_KEY, default=""),
        "last_result": result,
        "latest_package": package,
        "note": (
            "X / Threads need an API credential or an n8n/Make/IFTTT webhook bridge; "
            "Xiaohongshu is manual. The card and copy are prepared every day regardless."
        ),
    }
