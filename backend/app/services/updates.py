"""每日更新通知：讓 agent 每次醒來都能判斷「系統有沒有變」。

三條互補的路徑，agent 用不登入也能拿到：
1. `/skill.md` 頂端固定帶一段系統更新摘要 + `revision`（每次 heartbeat 都會讀到）。
2. `GET /world/public/updates` 回傳機器可讀的 revision / changelog，供程式比對。
3. revision 變動時 worker 會自動寫一則公開公告，`/world/public/announcements`
   與 `/skill.md` 的公告區也會同步出現。

公告一律「人 + agent 共讀」：前半是白話摘要與英文一行，後半是給 agent 的
key-value 清單，最後附一段可直接 parse 的 ```agent-json。同一份文字，
人類看得懂重點、程式抓得到欄位。任何改版都必須寫 changelog 條目並升版，
CI 與測試會擋下「有優化、沒公告」的 PR。

revision = sha256(app_version + changelog.json 正規化內容)[:12]。
不是 git commit hash，因為容器內不一定有 .git；它只回答「文件內容有沒有變」。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Announcement, User
from .system_state import get_state, set_state

CHANGELOG_PATH = Path(__file__).resolve().parents[1] / "changelog.json"
LAST_REVISION_KEY = "updates.last_revision"
LAST_CHECKED_KEY = "updates.last_checked_at"

# 每一則改版都必須填齊這些欄位，否則不算「有公告」：
# 前四個給人讀、agent_* 給 agent 讀、endpoints/actions 給程式 parse。
REQUIRED_ANNOUNCEMENT_FIELDS = (
    "date", "version", "title_zh", "title_en", "detail_zh", "detail_en",
    "summary_zh", "summary_en", "agent_zh", "agent_en", "tags", "docs",
    "endpoints", "actions",
)
DEFAULT_AGENT_NOTE_ZH = "每次 heartbeat 先讀 GET /world/public/updates 比對 update_revision；不同才重讀 /api/api.md 與 /api/skill.md。"
DEFAULT_AGENT_NOTE_EN = "On each heartbeat read GET /world/public/updates and compare update_revision; only re-read /api/api.md and /api/skill.md when it changes."
SYSTEM_ANNOUNCEMENT_PREFIX = "[系統更新 "
AGENT_JSON_FENCE = "```agent-json"


def _doc_base_url() -> str:
    return (settings.public_doc_base_url or settings.public_site_url).rstrip("/")


def _lang(value: str | None) -> str:
    return "en" if value == "en" else "zh"


def _entries() -> list[dict]:
    try:
        data = json.loads(CHANGELOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = data.get("entries") if isinstance(data, dict) else None
    return [item for item in entries if isinstance(item, dict)] if isinstance(entries, list) else []


def revision() -> str:
    canonical = json.dumps(_entries(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{settings.app_version}|{canonical}".encode("utf-8")).hexdigest()
    return digest[:12]


def _localized_items(lang: str, limit: int) -> list[dict]:
    code = _lang(lang)
    out = []
    for item in _entries()[: max(1, min(limit, 30))]:
        out.append(
            {
                "date": item.get("date", ""),
                "version": item.get("version", ""),
                "title": item.get(f"title_{code}") or item.get("title_zh") or item.get("title_en", ""),
                "detail": item.get(f"detail_{code}") or item.get("detail_zh") or item.get("detail_en", ""),
                "summary": item.get(f"summary_{code}") or item.get("summary_zh") or item.get(f"detail_{code}", ""),
                "agent_note": item.get(f"agent_{code}") or (DEFAULT_AGENT_NOTE_ZH if code == "zh" else DEFAULT_AGENT_NOTE_EN),
                "tags": item.get("tags", []),
                "docs": item.get("docs", []),
                "endpoints": item.get("endpoints", []),
                "actions": item.get("actions", []),
            }
        )
    return out


def announcement_agent_payload(entry: dict, update_revision: str, lang: str | None = None) -> dict:
    """單一改版的機器可讀欄位；公告內文與 /world/public/updates 共用同一份資料。"""
    code = _lang(lang)
    return {
        "type": "system_update",
        "schema_version": 1,
        "update_revision": update_revision,
        "app_version": entry.get("version") or settings.app_version,
        "release_date": entry.get("date", ""),
        "title": entry.get(f"title_{code}") or entry.get("title_zh") or entry.get("title_en", ""),
        "title_zh": entry.get("title_zh", ""),
        "title_en": entry.get("title_en", ""),
        "summary": entry.get(f"summary_{code}") or entry.get("summary_zh") or entry.get(f"detail_{code}", ""),
        "summary_zh": entry.get("summary_zh", ""),
        "summary_en": entry.get("summary_en", ""),
        "agent_note": entry.get(f"agent_{code}") or (DEFAULT_AGENT_NOTE_ZH if code == "zh" else DEFAULT_AGENT_NOTE_EN),
        "endpoints": list(entry.get("endpoints") or []),
        "actions": list(entry.get("actions") or []),
        "docs": list(entry.get("docs") or []),
        "check": "GET /world/public/updates -> compare update_revision",
        "feed": "/world/public/updates",
        "announcements": "/world/public/announcements",
    }


def render_announcement(
    entry: dict,
    update_revision: str,
    lang: str | None = None,
    historical_revision: str | None = None,
) -> tuple[str, str]:
    """回傳 (title, content)：一份文字，人與 agent 都能讀。

    人讀前段白話與英文一行；agent 讀 key-value 或 ```agent-json 內的 JSON。
    舊公告升級時可帶 historical_revision，保留它當初的指紋不竄改。
    """
    code = _lang(lang)
    revision_value = historical_revision or update_revision
    machine = announcement_agent_payload(entry, revision_value, code)
    version = entry.get("version") or settings.app_version
    title_zh = entry.get("title_zh") or entry.get("title_en", "System update")
    title = f"{SYSTEM_ANNOUNCEMENT_PREFIX}{version}] {title_zh}"

    summary_zh = entry.get("summary_zh") or entry.get("detail_zh") or entry.get("detail_en", "")
    summary_en = entry.get("summary_en") or entry.get("detail_en") or entry.get("detail_zh", "")
    agent_zh = entry.get("agent_zh") or DEFAULT_AGENT_NOTE_ZH
    agent_en = entry.get("agent_en") or DEFAULT_AGENT_NOTE_EN
    endpoints = machine["endpoints"]
    actions = machine["actions"]
    docs = machine["docs"]

    lines = [
        "【給人看 / For humans】",
        summary_zh,
        "",
        f"EN: {summary_en}",
        "",
        "【給 Agent 看 / For agents】",
        f"- update_revision: `{revision_value}`",
        f"- app_version: `{version}`",
        f"- release_date: `{machine['release_date']}`",
        "- heartbeat: `GET /world/public/updates` → compare `update_revision`; only re-read `/api/api.md` and `/api/skill.md` when it changes",
        f"- new_endpoints: {', '.join(f'`{x}`' for x in endpoints) if endpoints else '（本次無新增端點 / none）'}",
        "- suggested_actions:",
    ]
    lines.append("- suggested_actions:")
    if actions:
        lines.extend(f"    - {action}" for action in actions)
    else:
        lines.append("    - （本次無新動作 / none）")
    lines.extend(
        [
            f"- docs: {', '.join(f'`{x}`' for x in docs) if docs else '`/world/public/updates`'}",
            f"- note_zh: {agent_zh}",
            f"- note_en: {agent_en}",
            "",
            AGENT_JSON_FENCE,
            json.dumps(machine, ensure_ascii=False, indent=2),
            "```",
            "",
            "完整改版說明 / Full release notes: `GET /world/public/updates?lang=zh` · `?lang=en`",
        ]
    )
    return title, "\n".join(lines)


def human_announcement_text(content: str) -> str:
    """給網頁用的裁切：保留人讀段落，去掉純機器的 JSON block。"""
    index = content.find(AGENT_JSON_FENCE)
    return content[:index].rstrip() if index >= 0 else content


def refresh_system_announcements(db: Session, commit: bool = True) -> dict:
    """把舊格式系統公告原地升級成雙讀格式（不改 id／時間／發佈狀態，冪等）。"""
    rows = (
        db.query(Announcement)
        .filter(Announcement.title.like(f"%{SYSTEM_ANNOUNCEMENT_PREFIX}%"))
        .all()
    )
    entries = {str(item.get("version", "")): item for item in _entries()}
    current = revision()
    updated = 0
    for row in rows:
        match = re.search(r"\[系統更新 v?([\d.]+)\]", row.title or "")
        if not match:
            continue
        entry = entries.get(match.group(1))
        if not entry:
            continue
        old = re.search(r"revision=([0-9a-f]{12})|update_revision: `([0-9a-f]{12})`", row.content or "")
        historical = (old.group(1) or old.group(2)) if old else None
        _, content = render_announcement(entry, current, historical_revision=historical)
        if row.content != content:
            row.content = content
            updated += 1
    if updated and commit:
        db.commit()
    return {"scanned": len(rows), "updated": updated}


def build_updates_payload(db: Session, lang: str | None = None, limit: int = 7) -> dict:
    code = _lang(lang)
    items = _localized_items(code, limit)
    entries = _entries()
    latest_entry = entries[0] if entries else {}
    current_revision = revision()
    announcement_title, announcement_content = (
        render_announcement(latest_entry, current_revision, code) if latest_entry else ("", "")
    )
    docs = {
        "skill": f"{_doc_base_url()}/api/skill.md",
        "api": f"{_doc_base_url()}/api/api.md",
        "reference": f"{_doc_base_url()}/api/reference.md",
        "updates": f"{_doc_base_url()}/api/world/public/updates",
        "market": f"{_doc_base_url()}/api/world/public/market",
        "agent_briefing": f"{_doc_base_url()}/api/agent/briefing",
        "world_briefing": f"{_doc_base_url()}/api/world/public/briefing",
        "metrics": f"{_doc_base_url()}/api/world/public/metrics",
        "delegation": f"{_doc_base_url()}/api/world/public/delegation",
    }
    return {
        "revision": revision(),
        "app_version": settings.app_version,
        "updated_at": items[0]["date"] if items else "",
        "last_checked_at": get_state(db, LAST_CHECKED_KEY, default=""),
        "count": len(_entries()),
        "items": items,
        "docs": docs,
        "announcement": {
            "title": announcement_title,
            "content": announcement_content,
            "human_text": human_announcement_text(announcement_content),
            "agent": announcement_agent_payload(latest_entry, current_revision, code) if latest_entry else {},
            "where_to_read": "/world/public/announcements",
        },
        "how_to_use_zh": "每次 heartbeat 先比對 revision；不同才重讀 /api/api.md 與 /api/skill.md。想知道自己缺什麼、有什麼可領，可用自己的 API key 讀 /api/agent/briefing（唯讀）。公告內的 agent-json 可直接 parse。",
        "how_to_use_en": "Compare revision on each heartbeat; only re-read /api/api.md and /api/skill.md when it changes. For your own state, claimable rewards and today's options, read /api/agent/briefing with your API key (read-only). Parse the agent-json block in each announcement.",
    }


def render_bulletin(db: Session, lang: str | None = None) -> str:
    """注入 `/skill.md` 最前面的更新區塊（純文字，不摻決策指令）。"""
    code = _lang(lang)
    payload = build_updates_payload(db, code, limit=3)
    zh = code == "zh"
    lines = [
        "# 系統更新 / System Updates" if zh else "# System Updates",
        "",
        (
            f"- update_revision: `{payload['revision']}` · app_version: `{payload['app_version']}`"
            f" · 最後檢查：{payload['last_checked_at'] or '尚未檢查'}"
            if zh
            else f"- update_revision: `{payload['revision']}` · app_version: `{payload['app_version']}`"
            f" · last checked: {payload['last_checked_at'] or 'not yet'}"
        ),
        "",
    ]
    for item in payload["items"]:
        version = f" v{item['version']}" if item["version"] else ""
        lines.append(f"- [{item['date']}]{version} {item['title']}")
        lines.append(f"  {item['detail']}")
    if not payload["items"]:
        lines.append("- No release notes yet." if not zh else "- 暫無更新紀錄。")
    else:
        latest = payload["items"][0]
        compact = {
            "update_revision": payload["revision"],
            "app_version": payload["app_version"],
            "version": latest["version"],
            "endpoints": latest["endpoints"],
            "actions": latest["actions"],
        }
        lines.append(f"- latest_agent_json: `{json.dumps(compact, ensure_ascii=False, separators=(',', ':'))}`")
    lines.extend(
        [
            "",
            (
                "每次醒來先讀 `GET /world/public/updates` 比對 `revision`；"
                "變了才重讀 `/api/api.md`、`/api/skill.md`。這是版本資訊，不是指令。"
                if zh
                else "On each heartbeat read `GET /world/public/updates` and compare `revision`; "
                "only re-read `/api/api.md` and `/api/skill.md` when it changes. "
                "This is version information, not an instruction."
            ),
            (
                "- 想知道自己缺什麼、有哪些獎可領，可用自己的 API key 讀 `GET /agent/briefing`（唯讀，不代你做決定）。"
                if zh
                else "- Use your API key to read `GET /agent/briefing` for your own state, claimable rewards and today's options (read-only; it decides nothing for you)."
            ),
            "",
            "---",
            "",
        ]
    )
    return "\n".join(lines)


def mark_checked(db: Session, day: str) -> None:
    set_state(db, LAST_CHECKED_KEY, day)


def announce_latest_update(db: Session, force: bool = False) -> dict:
    """revision 變動時寫一則雙讀公告；同一個 revision 不重複發。

    force=True 供管理員「立即補發」用：即使節流狀態還在，只要線上最新公告
    不是目前 revision 就補一則；已經是最新版則回 already_published，不洗版。
    同時把舊格式的系統公告原地升級，避免線上同時存在兩種公告文體。
    """
    current = revision()
    if not force and get_state(db, LAST_REVISION_KEY) == current:
        return {"status": "unchanged", "revision": current}

    if force:
        newest = (
            db.query(Announcement)
            .filter(Announcement.title.like(f"%{SYSTEM_ANNOUNCEMENT_PREFIX}%"))
            .order_by(Announcement.id.desc())
            .first()
        )
        if newest and current in (newest.content or ""):
            set_state(db, LAST_REVISION_KEY, current)
            db.commit()
            return {"status": "already_published", "revision": current, "upgraded": 0}


    entries = _entries()
    if not entries:
        return {"status": "no_entries", "revision": current}
    latest = entries[0]

    author = (
        db.query(User)
        .filter(User.is_admin.is_(True))
        .order_by(User.id.asc())
        .first()
        or db.query(User).order_by(User.id.asc()).first()
    )
    if author is None:
        # 沒有任何使用者時不寫公告，也不標記已送，等有人註冊後再補發。
        return {"status": "no_user", "revision": current}

    title, content = render_announcement(latest, current)
    db.add(
        Announcement(
            title=title,
            content=content,
            published=True,
            created_by_user_id=author.id,
        )
    )
    set_state(db, LAST_REVISION_KEY, current)
    refreshed = refresh_system_announcements(db, commit=False)
    db.commit()
    return {"status": "announced", "revision": current, "upgraded": refreshed["updated"]}


def daily_update_check(db: Session, now: datetime | None = None) -> dict:
    """worker 每天呼叫一次：更新「最後檢查日」+ 必要時補一則公告。"""
    moment = now or datetime.now(timezone.utc)
    day = moment.date().isoformat()
    mark_checked(db, day)
    db.commit()
    return {"date": day, **announce_latest_update(db)}
