"""每日發文包的短連結與點擊追蹤：讓「內容 → 觀眾席 → 分享」可以量化。

設計原則（沿用觀眾席／賽季的既有決策）：
- **不改 DB schema**：短碼、點擊數與待發紀錄全部存在 `system_state`，不改任何 agent 欄位。
- **零憑證**：不需要 X／Threads／小紅書 API；有 webhook 就推送，沒有就進待發佇列。
- **不破壞既有結構**：`current_post_package()` 原有欄位一個都不改，只新增
  `links` / `share_url` / `tracking_note`；通路專屬文案放在 `links[channel]` 裡。
- **安全**：重導目標只接受站內相對路徑白名單，避免變成 open redirect；
  短碼用不可逆雜湊，公開報表只有聚合數字，不含 IP、UA 或訪客識別。

點擊數是**粗略估計**：社群平台的 link preview bot 會預抓連結，所以用
User-Agent 另外記一組 `human_clicks`；報表以這組為主，並在文件明說不等同 GA。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import Session

from ..config import settings
from ..models import SystemState
from .system_state import get_state, set_state

DAY_PREFIX = "links.day."
CODE_PREFIX = "links.code."
OUTBOX_PREFIX = "outbox.day."
KEEP_DAYS = 30
MAX_RETRIES = 3
CODE_LENGTH = 8
HKT = timezone(timedelta(hours=8))

# (channel, 中文標籤, 英文標籤, 固定目標)；target=None 代表用當日發文包的主要 CTA。
CHANNEL_SPECS: tuple[tuple[str, str, str, str | None], ...] = (
    ("x", "X", "X", None),
    ("threads", "Threads", "Threads", None),
    ("xhs", "小紅書", "Xiaohongshu", None),
    ("webhook", "Webhook / n8n", "Webhook / n8n", None),
    ("audience", "觀眾席", "Audience", "/audience"),
    ("direct", "直接分享", "Direct", None),
)
CHANNELS = tuple(spec[0] for spec in CHANNEL_SPECS)

# 允許的站內目標前綴；其餘一概拒絕，避免短連結被拿去當開放重導器。
TARGET_PREFIXES = ("/chronicle", "/audience", "/season", "/battle", "/share")

BOT_UA_MARKERS = (
    "bot",
    "crawler",
    "spider",
    "preview",
    "facebookexternalhit",
    "slackbot",
    "twitterbot",
    "discordbot",
    "telegrambot",
    "linkedinbot",
    "whatsapp",
    "curl",
    "wget",
    "python-requests",
    "headless",
)


def hkt_date(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(HKT).date().isoformat()


def _day_key(date_str: str) -> str:
    return DAY_PREFIX + date_str


def _code_key(code: str) -> str:
    return CODE_PREFIX + code


def _outbox_key(date_str: str) -> str:
    return OUTBOX_PREFIX + date_str


def _site_base() -> str:
    return settings.public_site_url.rstrip("/")


def _site_url_pattern() -> re.Pattern[str]:
    # 每次即時 compile，避免測試或部署時改了 public_site_url 卻用到舊的 regex。
    return re.compile(re.escape(_site_base()) + r"/[^\s\]\)>\"'，。；、]*")


def short_url(code: str) -> str:
    return f"{_site_base()}/s/{code}"


def _code(date_str: str, channel: str, target: str) -> str:
    raw = f"{date_str}|{channel}|{target}|{settings.jwt_secret}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:CODE_LENGTH]


def _safe_target(target: str) -> bool:
    """只接受單一站內相對路徑；擋掉 //、scheme、反斜線與控制字元。"""
    if not isinstance(target, str) or not target or not target.startswith("/"):
        return False
    if target.startswith("//") or "\\" in target or "://" in target:
        return False
    if any(ord(ch) < 32 for ch in target):
        return False
    if target == "/":
        return True
    # 只接受白名單頁面本身、其子路徑或附 query，不接受任意站內路徑。
    return any(
        target == prefix or target.startswith(prefix + "/") or target.startswith(prefix + "?")
        for prefix in TARGET_PREFIXES
    )


def primary_target(package: dict[str, Any]) -> str:
    """從文案的主要 CTA 抓站內路徑；抓不到就回史記頁。"""
    for text in (package.get("caption", ""), package.get("caption_long", "")):
        match = _site_url_pattern().search(str(text))
        if not match:
            continue
        parsed = urlsplit(match.group(0))
        candidate = parsed.path or "/chronicle"
        if parsed.query:
            candidate = f"{candidate}?{parsed.query}"
        if _safe_target(candidate):
            return candidate
    return "/chronicle"


def _empty_day(date_str: str) -> dict[str, Any]:
    return {"date": date_str, "links": {}, "updated_at": ""}


def _load_day(db: Session, date_str: str) -> dict[str, Any]:
    raw = get_state(db, _day_key(date_str))
    try:
        data = json.loads(raw) if raw else _empty_day(date_str)
    except (json.JSONDecodeError, TypeError):
        data = _empty_day(date_str)
    if not isinstance(data, dict):
        return _empty_day(date_str)
    data.setdefault("date", date_str)
    links = data.setdefault("links", {})
    if not isinstance(links, dict):
        data["links"] = {}
    return data


def _save_day(db: Session, date_str: str, data: dict[str, Any]) -> None:
    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    set_state(db, _day_key(date_str), json.dumps(data, ensure_ascii=False))


def _prune(db: Session, date_str: str) -> None:
    """清掉超過 KEEP_DAYS 的每日 bucket、短碼索引與待發紀錄。"""
    cutoff = date.fromisoformat(date_str) - timedelta(days=KEEP_DAYS)
    cutoff_str = cutoff.isoformat()
    (
        db.query(SystemState)
        .filter(SystemState.key.like(DAY_PREFIX + "%"), SystemState.key < _day_key(cutoff_str))
        .delete(synchronize_session=False)
    )
    (
        db.query(SystemState)
        .filter(SystemState.key.like(OUTBOX_PREFIX + "%"), SystemState.key < _outbox_key(cutoff_str))
        .delete(synchronize_session=False)
    )
    stale = (
        db.query(SystemState)
        .filter(SystemState.key.like(CODE_PREFIX + "%"))
        .all()
    )
    for row in stale:
        try:
            meta = json.loads(row.value)
            old = str(meta.get("date", "")) < cutoff_str
        except (json.JSONDecodeError, TypeError, AttributeError):
            old = True
        if old:
            db.delete(row)


def ensure_links(
    db: Session,
    date_str: str,
    primary: str = "/chronicle",
    lang: str = "zh",
) -> dict[str, Any]:
    """冪等產生當日各通路短碼；已存在就只讀不寫，避免公開 GET 一直寫 DB。"""
    if not _safe_target(primary):
        primary = "/chronicle"
    day = _load_day(db, date_str)
    links = day["links"]
    dirty = False
    for channel, label_zh, label_en, fixed_target in CHANNEL_SPECS:
        target = fixed_target or primary
        code = _code(date_str, channel, target)
        key = _code_key(code)
        if get_state(db, key) == "":
            set_state(
                db,
                key,
                json.dumps(
                    {"date": date_str, "channel": channel, "target": target},
                    ensure_ascii=False,
                ),
            )
            dirty = True
        if code not in links:
            links[code] = {
                "code": code,
                "channel": channel,
                "label": label_zh if lang == "zh" else label_en,
                "target": target,
                "url": short_url(code),
                "clicks": 0,
                "human_clicks": 0,
            }
            dirty = True
        else:
            label = label_zh if lang == "zh" else label_en
            if links[code].get("label") != label:
                links[code]["label"] = label
                dirty = True
    if dirty:
        _save_day(db, date_str, day)
        _prune(db, date_str)
        db.commit()
    return links


def _with_channel_captions(
    links: dict[str, Any],
    package: dict[str, Any],
) -> dict[str, Any]:
    """為每個通路產生一份「已換成專屬短連結」的文案，原 package 欄位不動。"""
    result: dict[str, Any] = {}
    for code, meta in links.items():
        url = meta["url"]
        replace = lambda text: _site_url_pattern().sub(url, str(text))  # noqa: E731
        result[meta["channel"]] = {
            "code": code,
            "url": url,
            "label": meta["label"],
            "target": meta["target"],
            "clicks": meta.get("clicks", 0),
            "human_clicks": meta.get("human_clicks", 0),
            "caption": replace(package.get("caption", "")),
            "caption_long": replace(package.get("caption_long", "")),
        }
    return result


def tracked_package(
    db: Session,
    package: dict[str, Any],
    lang: str = "zh",
    now: datetime | None = None,
) -> dict[str, Any]:
    """在回傳值加上通路專屬短連結；不改快取、不改既有欄位。"""
    date_str = str(package.get("date") or hkt_date(now))
    link_rows = ensure_links(db, date_str, primary_target(package), lang)
    channels = _with_channel_captions(link_rows, package)
    patched = dict(package)
    patched["links"] = channels
    patched["share_url"] = channels.get("x", {}).get("url", "")
    patched["tracking_note"] = (
        "每個通路一組專屬短連結，點擊數為粗略估計（已排除常見爬蟲），不等同 GA。"
        if lang == "zh"
        else "Each channel has its own tracked short link. Clicks are approximate "
        "(common crawlers excluded), not a full analytics product."
    )
    return patched


def record_click(db: Session, code: str, user_agent: str = "") -> str | None:
    """驗證短碼 → 記一次點擊 → 回傳站內目標。找不到或不合法回 None。"""
    if not re.fullmatch(r"[0-9a-f]{%d}" % CODE_LENGTH, code or ""):
        return None
    raw = get_state(db, _code_key(code))
    if not raw:
        return None
    try:
        meta = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    target = str(meta.get("target", ""))
    date_str = str(meta.get("date", ""))
    if not _safe_target(target) or not date_str:
        return None

    ua = (user_agent or "").lower()
    is_human = not any(marker in ua for marker in BOT_UA_MARKERS)
    for _attempt in range(MAX_RETRIES):
        try:
            row = (
                db.query(SystemState)
                .filter(SystemState.key == _day_key(date_str))
                .with_for_update()
                .first()
            )
            if row is None:
                return target  # index 存在但 bucket 被清掉：仍給重導，只是不記數
            day = json.loads(row.value)
            entry = day.get("links", {}).get(code)
            if entry is None:
                return target
            entry["clicks"] = int(entry.get("clicks", 0)) + 1
            if is_human:
                entry["human_clicks"] = int(entry.get("human_clicks", 0)) + 1
            day["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            row.value = json.dumps(day, ensure_ascii=False)
            db.commit()
            break
        except sa_exc.IntegrityError:
            db.rollback()
        except (json.JSONDecodeError, TypeError, AttributeError):
            db.rollback()
            break
    return target


def stats(db: Session, days: int = 7, now: datetime | None = None) -> dict[str, Any]:
    """近 N 個 HKT 日的聚合點擊數；不含任何訪客識別或原始 UA。"""
    days = max(1, min(days, KEEP_DAYS))
    today = date.fromisoformat(hkt_date(now))
    per_day: list[dict[str, Any]] = []
    by_channel: dict[str, int] = {}
    total = 0
    human_total = 0
    for offset in range(days - 1, -1, -1):
        day_str = (today - timedelta(days=offset)).isoformat()
        day = _load_day(db, day_str)
        rows: dict[str, int] = {}
        clicks = 0
        human = 0
        for meta in day.get("links", {}).values():
            channel = str(meta.get("channel", ""))
            c = int(meta.get("clicks", 0))
            h = int(meta.get("human_clicks", 0))
            rows[channel] = rows.get(channel, 0) + h
            by_channel[channel] = by_channel.get(channel, 0) + h
            clicks += c
            human += h
        total += clicks
        human_total += human
        per_day.append({"date": day_str, "clicks": clicks, "human_clicks": human, "by_channel": rows})
    return {
        "days": days,
        "total_clicks": total,
        "total_human_clicks": human_total,
        "by_channel": by_channel,
        "per_day": per_day,
        "note": (
            "點擊數已排除常見 link-preview 爬蟲，但仍可能被快取或預覽重複計算；"
            "這是用來比較通路相對成效的粗略指標，不是嚴謹分析。"
        ),
    }


def write_outbox(
    db: Session,
    date_str: str,
    package: dict[str, Any],
    status: str,
    channel: str,
) -> None:
    """每日一筆待發紀錄；只存公開可見的內容，不存 webhook URL 或錯誤細節。"""
    record = {
        "date": date_str,
        "status": status,
        "channel": channel,
        "headline": package.get("headline", ""),
        "caption": package.get("caption", ""),
        "caption_long": package.get("caption_long", ""),
        "image_url": package.get("image_url", ""),
        "share_url": package.get("share_url", ""),
        "links": package.get("links", {}),
    }
    set_state(db, _outbox_key(date_str), json.dumps(record, ensure_ascii=False))
    db.commit()


def recent_outbox(db: Session, days: int = 7, now: datetime | None = None) -> dict[str, Any]:
    days = max(1, min(days, KEEP_DAYS))
    today = date.fromisoformat(hkt_date(now))
    items: list[dict[str, Any]] = []
    for offset in range(days - 1, -1, -1):
        day_str = (today - timedelta(days=offset)).isoformat()
        raw = get_state(db, _outbox_key(day_str))
        if not raw:
            if offset == 0:
                # 部署當天 08:00 已跑過、還沒有 outbox 紀錄：即時補一筆（不寫 DB），
                # 讓 /share 一上線就有東西可貼，不必等隔天。
                from .chronicle_publish import current_post_package

                package = current_post_package(db)
                items.append(
                    {
                        "date": day_str,
                        "status": "prepared",
                        "provisional": True,
                        "channel": "manual",
                        "headline": package.get("headline", ""),
                        "caption": package.get("caption", ""),
                        "caption_long": package.get("caption_long", ""),
                        "image_url": package.get("image_url", ""),
                        "share_url": package.get("share_url", ""),
                        "links": package.get("links", {}),
                    }
                )
            else:
                items.append({"date": day_str, "status": "missing", "headline": ""})
            continue
        try:
            item = json.loads(raw)
            if isinstance(item, dict):
                items.append(item)
        except (json.JSONDecodeError, TypeError):
            items.append({"date": day_str, "status": "missing", "headline": ""})
    items.reverse()  # 最新在前
    return {"days": days, "items": items, "count": sum(1 for i in items if i.get("status") != "missing")}


def link_status(db: Session) -> dict[str, Any]:
    return {
        "keep_days": KEEP_DAYS,
        "channels": list(CHANNELS),
        "code_length": CODE_LENGTH,
        "short_url_prefix": f"{_site_base()}/s/",
        "redirect_endpoint": f"{_site_base()}/world/public/s/{{code}}",
        "stats": stats(db, days=KEEP_DAYS),
        "note": "Clicks are approximate: link-preview crawlers are excluded by User-Agent.",
    }
