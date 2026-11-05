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
from .chronicle_card import build_post_package
from .daily_chronicle import build_story_from_db, generate_daily_chronicle, get_latest_story
from .system_state import get_state, set_state

LAST_DATE_KEY = "chronicle_card_last_date"
PACKAGE_KEY = "chronicle_card_post_latest"
RESULT_KEY = "chronicle_card_last_result"
ATTEMPTS_KEY = "chronicle_card_attempts"

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
    """優先回傳當天已產出的發文包；worker 尚未跑時即時算一份（不寫入）。"""
    raw = get_state(db, PACKAGE_KEY, default="")
    if raw:
        try:
            package = json.loads(raw)
            if package.get("lang") == lang:
                return package
        except json.JSONDecodeError:
            pass
    return build_post_package(build_story_from_db(db, lang=lang))


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
    story = generate_daily_chronicle(db, lang="zh", force=True)
    package = build_post_package(story)
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
