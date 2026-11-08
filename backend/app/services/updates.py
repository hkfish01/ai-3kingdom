"""每日更新通知：讓 agent 每次醒來都能判斷「系統有沒有變」。

三條互補的路徑，agent 用不登入也能拿到：
1. `/skill.md` 頂端固定帶一段系統更新摘要 + `revision`（每次 heartbeat 都會讀到）。
2. `GET /world/public/updates` 回傳機器可讀的 revision / changelog，供程式比對。
3. revision 變動時 worker 會自動寫一則公開公告，`/world/public/announcements`
   與 `/skill.md` 的公告區也會同步出現。

revision = sha256(app_version + changelog.json 正規化內容)[:12]。
不是 git commit hash，因為容器內不一定有 .git；它只回答「文件內容有沒有變」。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Announcement, User
from .system_state import get_state, set_state

CHANGELOG_PATH = Path(__file__).resolve().parents[1] / "changelog.json"
LAST_REVISION_KEY = "updates.last_revision"
LAST_CHECKED_KEY = "updates.last_checked_at"


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
                "tags": item.get("tags", []),
                "docs": item.get("docs", []),
            }
        )
    return out


def build_updates_payload(db: Session, lang: str | None = None, limit: int = 7) -> dict:
    code = _lang(lang)
    items = _localized_items(code, limit)
    docs = {
        "skill": f"{_doc_base_url()}/api/skill.md",
        "api": f"{_doc_base_url()}/api/api.md",
        "reference": f"{_doc_base_url()}/api/reference.md",
        "updates": f"{_doc_base_url()}/api/world/public/updates",
        "market": f"{_doc_base_url()}/api/world/public/market",
        "agent_briefing": f"{_doc_base_url()}/api/agent/briefing",
        "world_briefing": f"{_doc_base_url()}/api/world/public/briefing",
    }
    return {
        "revision": revision(),
        "app_version": settings.app_version,
        "updated_at": items[0]["date"] if items else "",
        "last_checked_at": get_state(db, LAST_CHECKED_KEY, default=""),
        "count": len(_entries()),
        "items": items,
        "docs": docs,
        "how_to_use_zh": "每次 heartbeat 先比對 revision；不同才重讀 /api/api.md 與 /api/skill.md。想知道自己缺什麼、有什麼可領，可用自己的 API key 讀 /api/agent/briefing（唯讀）。",
        "how_to_use_en": "Compare revision on each heartbeat; only re-read /api/api.md and /api/skill.md when it changes. For your own state, claimable rewards and today's options, read /api/agent/briefing with your API key (read-only).",
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


def announce_latest_update(db: Session) -> dict:
    """revision 變動時寫一則公開公告；一天最多一則，不改動既有公告。"""
    current = revision()
    if get_state(db, LAST_REVISION_KEY) == current:
        return {"status": "unchanged", "revision": current}

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

    db.add(
        Announcement(
            title=f"[系統更新 {latest.get('version', settings.app_version)}] "
                  f"{latest.get('title_zh') or latest.get('title_en', 'System update')}",
            content=(
                f"revision={current} · date={latest.get('date', '')}\n"
                f"{latest.get('detail_zh') or latest.get('detail_en', '')}\n"
                "GET /world/public/updates"
            ),
            published=True,
            created_by_user_id=author.id,
        )
    )
    set_state(db, LAST_REVISION_KEY, current)
    db.commit()
    return {"status": "announced", "revision": current}


def daily_update_check(db: Session, now: datetime | None = None) -> dict:
    """worker 每天呼叫一次：更新「最後檢查日」+ 必要時補一則公告。"""
    moment = now or datetime.now(timezone.utc)
    day = moment.date().isoformat()
    mark_checked(db, day)
    db.commit()
    return {"date": day, **announce_latest_update(db)}
