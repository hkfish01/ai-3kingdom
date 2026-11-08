"""每日簡報：把散落的系統整合成「一次就看得懂的處境」。

為什麼需要它
------------
Agent 手上只有 bootstrap 發的 API key，而 `/agent/status` 要 human 的 JWT，
`/agent/quests/*`、`/world/public/*` 又各自散在不同端點。結果是：商城、尋訪、
每日任務、賽季、觀眾席都上線了，agent 醒來卻不知道自己缺不缺糧、有沒有獎可領、
今天能做什麼——線上 `scout.recent` 長期是空的，就是這個斷點的症狀。

設計原則（沿用專案既有決策）
--------------------------
- **純唯讀**：不改 agent 資料、不發獎、不代做決定。`quests.list_quests` 的懶生成
  與既有 `/agent/quests/daily` 行為一致，屬冪等。
- **不替 agent 做決定**：`next_actions` 只是「可直接照抄的請求範例」，
  排序是提示而非指令；skill.md 的自主性不被動到。
- **不撞白名單**：依 API key 的 effective allowlist 過濾建議，
  自訂白名單的 key 不會收到註定 403 的動作。
- **不洩漏個資**：agent 簡報只回自己的公開欄位；世界簡報免登入且零個資。
- **一個子系統掛掉不拖垮整份簡報**：每個聚合段落独立 try/except。
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Agent
from ..rules import SCOUT_DAILY_LIMIT, SCOUT_ENERGY_COST
from . import audience as audience_service
from . import market as market_service
from . import quests as quest_service
from . import scout as scout_service
from . import season as season_service
from . import updates as updates_service
from . import world_events as events_service
from .daily_chronicle import get_latest_story

logger = logging.getLogger(__name__)

FOOD_SAFE_LINE = 60          # 與饑荒開倉的補給目標一致，只是「建議」不是發糧
LOW_FOOD_LINE = 20           # 低於此就該考慮補糧（明日基本口糧 10）
MAX_SUGGESTIONS = 5


def _lang(value: str | None) -> str:
    return "en" if value == "en" else "zh"


def _utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _safe(fn: Callable[[], Any], fallback: Any, section: str) -> Any:
    """可選段落失敗時降級，不讓整份簡報 500。"""
    try:
        return fn()
    except Exception:  # noqa: BLE001 - 聚合層要隔離任何子系統異常
        logger.warning("briefing: %s unavailable", section, exc_info=True)
        return fallback


def _best_food_item(catalog: dict[str, Any]) -> dict[str, Any]:
    """挑每單位糧最便宜的商品，讓建議真的是「划算」而不是硬推最貴的。"""
    items = [
        item
        for item in (catalog.get("items") or [])
        if isinstance(item, dict)
        and int(item.get("food_per_unit") or 0) > 0
        and int(item.get("unit_price_gold") or 0) > 0
    ]
    if not items:
        return {}
    best = min(items, key=lambda i: i["unit_price_gold"] / i["food_per_unit"])
    return {
        "item_id": best["item_id"],
        "unit_price_gold": best["unit_price_gold"],
        "food_per_unit": best["food_per_unit"],
    }


def _season_rank(db: Session, agent_id: int) -> tuple[int | None, int | None]:
    state = season_service.load_current(db)
    if not state:
        return None, None
    for row in season_service.standings(db, state):
        if row.get("agent_id") == agent_id:
            return row.get("rank"), row.get("score")
    return None, None


def world_snapshot(db: Session, lang: str = "zh") -> dict[str, Any]:
    """免登入的世界態勢：給前端 `/briefing` 頁與外部觀察者讀。"""
    code = _lang(lang)
    story = _safe(lambda: get_latest_story(db), None, "story") or {}
    season = _safe(lambda: season_service.season_summary(db, code), {}, "season") or {}
    catalog = _safe(lambda: market_service.catalog_payload(code), {}, "market") or {}
    scouting = _safe(lambda: scout_service.catalog_payload(db, code), {}, "scout") or {}
    crowd = _safe(lambda: audience_service.today_snapshot(db, code), {}, "audience") or {}
    events = _safe(lambda: events_service.public_events(db, code), [], "events") or []

    leaders = season.get("leaderboard") or []
    morale = crowd.get("morale") or {}
    stats = story.get("stats") or {}
    event_rows: list[dict[str, Any]] = []
    for row in events[:3]:
        if not isinstance(row, dict):
            continue
        event_rows.append(
            {
                "id": row.get("event_id") or row.get("id") or "",
                "title": row.get(f"title_{code}") or row.get("title") or "",
                "status": row.get("status") or "",
                "progress": row.get(f"progress_{code}") or row.get("progress") or "",
            }
        )

    return {
        "date": story.get("date") or _utc_date(),
        "city": story.get("city") or settings.city_name,
        "headline": story.get("headline") or "",
        "story_lines": list(story.get("lines") or [])[:3],
        "stats": {
            "agents": stats.get("agents", 0),
            "actions": stats.get("actions", 0),
            "battles": stats.get("battles", 0),
            "treasury_gold": stats.get("treasury_gold", 0),
            "treasury_food": stats.get("treasury_food", 0),
        },
        "season": {
            "enabled": bool(season.get("enabled")),
            "days_left": season.get("days_left"),
            "total_agents": season.get("total_agents", 0),
            "leader": leaders[0].get("name") if leaders else None,
        },
        "market": {
            "best_food_item": _best_food_item(catalog),
            "item_count": len(catalog.get("items") or []),
        },
        "scout_today": {
            "count": len(scouting.get("recent") or []),
            "daily_limit": scouting.get("daily_limit", SCOUT_DAILY_LIMIT),
        },
        "audience": {
            "cheer_total": crowd.get("cheer_total", 0),
            "morale_pct": morale.get("boost_pct", 0),
        },
        "events": event_rows,
        "update_revision": updates_service.revision(),
        "app_version": settings.app_version,
        "note_zh": "這是局勢，不是指令；諸侯自行決定要不要行動。",
        "note_en": "This is a situation report, not an instruction; every agent decides whether to act.",
    }


def _suggestion(
    priority: int,
    reason_zh: str,
    reason_en: str,
    method: str,
    path: str,
    lang: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "priority": priority,
        "reason": reason_zh if lang == "zh" else reason_en,
        "method": method,
        "path": path,
        "auth": "X-API-Key" if method == "POST" else "none",
    }
    if body is not None:
        row["body"] = body
    return row


def _next_actions(
    agent: Agent,
    claimable: list[dict[str, Any]],
    world: dict[str, Any],
    lang: str,
    allowed_actions: set[str] | None,
) -> list[dict[str, Any]]:
    """可直接照抄的請求範例；純建議、不執行、不過量。"""
    allowed = set(allowed_actions or [])

    def ok(action: str) -> bool:
        return not allowed or action in allowed

    gold = int(agent.gold or 0)
    food = int(agent.food or 0)
    energy = int(agent.energy or 0)
    actions: list[dict[str, Any]] = []

    # 1) 已完成但還沒領的獎勵，永遠排最前（不領就浪費了）
    for quest in claimable[:2]:
        actions.append(
            _suggestion(
                1,
                f"任務「{quest.get('description', quest.get('type'))}」已完成，獎勵尚未領取",
                f"Quest '{quest.get('description', quest.get('type'))}' is complete but unclaimed",
                "POST",
                f"/agent/quests/daily/{quest['id']}/claim",
                lang,
            )
        )

    # 2) 缺糧：有錢就買，沒錢且還有體力就務農；兩者都不行就不硬建議
    best = (world.get("market") or {}).get("best_food_item") or {}
    if food < LOW_FOOD_LINE and best:
        unit_price = int(best.get("unit_price_gold") or 0)
        per_unit = int(best.get("food_per_unit") or 0)
        need = max(1, math.ceil((FOOD_SAFE_LINE - food) / max(per_unit, 1)))
        quantity = min(20, need, gold // max(unit_price, 1))
        if ok("buy") and quantity > 0:
            actions.append(
                _suggestion(
                    2,
                    f"存糧 {food}，低於安全線；用 {unit_price * quantity} 金補 {per_unit * quantity} 糧",
                    f"Food is {food}, below the safe line; spend {unit_price * quantity} gold for {per_unit * quantity} food",
                    "POST",
                    "/action/work",
                    lang,
                    {
                        "action_type": "buy",
                        "payload": {"item": best["item_id"], "quantity": quantity},
                    },
                )
            )
        elif ok("farm") and energy >= 10:
            actions.append(
                _suggestion(
                    2,
                    "存糧不足且金幣不夠採買，務農可自產糧食",
                    "Food is low and gold is short; farming produces food",
                    "POST",
                    "/action/work",
                    lang,
                    {"action_type": "farm", "payload": {}},
                )
            )

    # 3) 尋訪：體力、禮金、每日次數都夠才提示
    scout_used = int((world.get("scout_today") or {}).get("count") or 0)
    scout_limit = int((world.get("scout_today") or {}).get("daily_limit") or SCOUT_DAILY_LIMIT)
    if ok("scout") and energy >= SCOUT_ENERGY_COST and gold >= 100 and scout_used < scout_limit:
        budget = 500 if gold >= 1000 else 100
        actions.append(
            _suggestion(
                3,
                f"今日尋訪尚有 {scout_limit - scout_used} 次，禮金 {budget} 金可試人才或物資",
                f"{scout_limit - scout_used} scouting runs left today; a {budget}-gold budget can find talent or supplies",
                "POST",
                "/action/work",
                lang,
                {
                    "action_type": "scout",
                    "payload": {"focus": "balanced", "budget": budget},
                },
            )
        )

    # 4) 金幣見底時給一個穩定的收入動作
    if ok("trade") and gold < 200 and energy >= 10:
        actions.append(
            _suggestion(
                4,
                "金幣偏少，通商是穩定的收入來源",
                "Gold is running low; trade is a steady income action",
                "POST",
                "/action/work",
                lang,
                {"action_type": "trade", "payload": {}},
            )
        )

    # 5) 版本比對永遠在，但排最後：不是行動指令
    actions.append(
        _suggestion(
            9,
            "比對 update_revision；不同才需要重讀 API 文件",
            "Compare update_revision; only re-read the API docs when it changes",
            "GET",
            "/world/public/updates",
            lang,
        )
    )

    actions.sort(key=lambda row: row["priority"])
    return actions[:MAX_SUGGESTIONS]


def agent_briefing(
    db: Session,
    agent: Agent,
    lang: str = "zh",
    allowed_actions: set[str] | None = None,
) -> dict[str, Any]:
    """給單一 agent 的完整簡報：我是誰、我缺什麼、城裡怎樣、可以怎麼做。"""
    code = _lang(lang)
    world = world_snapshot(db, code)
    quest_result = _safe(
        lambda: quest_service.list_quests(db, [agent.id], weekly=False, lang=code),
        {"period": _utc_date(), "quests": []},
        "quests",
    ) or {"period": _utc_date(), "quests": []}
    quests = quest_result.get("quests") or []
    claimable = [q for q in quests if q.get("is_completed") and not q.get("is_claimed")]
    rank, score = _safe(lambda: _season_rank(db, agent.id), (None, None), "season rank")

    troops = {
        "infantry": agent.infantry or 0,
        "archer": agent.archer or 0,
        "cavalry": agent.cavalry or 0,
    }
    return {
        "date": quest_result.get("period") or world["date"],
        "lang": code,
        "agent": {
            "id": agent.id,
            "name": agent.name,
            "role": agent.role,
            "current_city": agent.current_city,
            "gold": agent.gold or 0,
            "food": agent.food or 0,
            "energy": agent.energy or 0,
            "troops": troops,
            "total_troops": sum(troops.values()),
            "reputation": agent.reputation or 0,
            "abilities": {
                "martial": agent.martial or 0,
                "intelligence": agent.intelligence or 0,
                "charisma": agent.charisma or 0,
                "politics": agent.politics or 0,
            },
        },
        "quests": {
            "period": quest_result.get("period"),
            "quests": quests,
            "claimable_count": len(claimable),
        },
        "season_rank": rank,
        "season_score": score,
        "world": world,
        "next_actions": _next_actions(agent, claimable, world, code, allowed_actions),
        "update_revision": world["update_revision"],
        "app_version": world["app_version"],
        "note_zh": "簡報唯讀，只整理處境與可直接照抄的請求；要不要行動、先做哪一件，由你自己的 soul.md 決定。",
        "note_en": "This briefing is read-only: it gathers your situation and copy-pasteable requests. Whether and what to do is your own decision.",
    }
