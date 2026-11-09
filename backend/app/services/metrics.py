"""匿名成效量測：功能一直加，總得知道有沒有人真的用。

為什麼這樣設計
--------------
- **純觀察**：唯一的寫入是「某個 agent 在某天讀過一次簡報、當時被建議了哪些動作」，
  不發獎、不扣款、不改 agent 任何數值，也不碰既有動作／任務／商城的交易。
- **不改既有寫入路徑**：動作是否成功、任務是否領取，直接讀既有的
  `AgentActionEvent`（status=completed）與 `AgentDailyQuest` / `AgentWeeklyQuest`。
  這樣採納率不會因為重播事件而灌水（事件表本身就是冪等紀錄）。
- **對外零個資**：公開端點只回聚合計數與比率；agent_id 只存在資料庫內部，
  不輸出名字、email、API key 或任何單一列資料。
- **口徑寫在回傳裡**：`definitions` / `machine` 讓人與 agent 都看得到
  「採納率」「首次動作」「次日回訪」是怎麼算的，避免數字被過度解讀。

時間一律用 UTC 日切（與 quests / briefing 一致），`timezone` 欄位會明講。
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    Agent,
    AgentActionEvent,
    AgentDailyQuest,
    AgentWeeklyQuest,
    BriefingView,
)

logger = logging.getLogger(__name__)

DEFAULT_DAYS = 14
MAX_DAYS = 30


def _lang(value: str | None) -> str:
    return "en" if value == "en" else "zh"


def _naive(value: datetime) -> datetime:
    """SQLite 的 DateTime 會把 aware UTC 存成 naive；統一去掉 tzinfo 再比較。"""
    return value.replace(tzinfo=None) if value.tzinfo else value


def _day_of(value: datetime | None) -> str:
    return _naive(value).date().isoformat() if value else ""


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _week_start(day: str) -> str:
    d = date.fromisoformat(day)
    return (d - timedelta(days=d.weekday())).isoformat()


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 3) if denominator else 0.0


def normalize_suggestions(next_actions: Iterable[dict[str, Any]]) -> list[str]:
    """把 `next_actions` 轉成可比對的動作 key（去重、保序）。

    `body.action_type`（buy/farm/scout/trade…）直接用；領獎建議記為 `claim`；
    `GET /world/public/updates` 只是版本比對提示，不是可採納的遊戲動作，排除。
    """
    keys: list[str] = []
    for row in next_actions or []:
        if not isinstance(row, dict):
            continue
        body = row.get("body") if isinstance(row.get("body"), dict) else {}
        action_type = str(body.get("action_type") or "").strip().lower()
        path = str(row.get("path") or "")
        if action_type:
            key = action_type
        elif "/claim" in path:
            key = "claim"
        else:
            continue
        if key not in keys:
            keys.append(key)
    return keys


def _parse_keys(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [str(x) for x in value if isinstance(x, str)] if isinstance(value, list) else []


def record_briefing_view(
    db: Session,
    agent_id: int,
    next_actions: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> None:
    """Best-effort：量測失敗絕不能讓 agent 讀不到簡報。

    刻意與主請求共用同一個 session（不另開連線，避免 SQLite 鎖競爭），
    並把整段包在 try/except：即使新表尚未建立或寫入衝突，簡照樣回傳。
    """
    try:
        stamp = _naive(now or datetime.now(timezone.utc))
        keys = normalize_suggestions(next_actions)
        db.add(
            BriefingView(
                agent_id=int(agent_id),
                day=stamp.date().isoformat(),
                suggested_json=json.dumps(keys),
                created_at=stamp,
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001 - 觀察層不能影響遊戲請求
        db.rollback()
        logger.warning("metrics: failed to record briefing view", exc_info=True)


def _empty_day(day: str) -> dict[str, Any]:
    return {
        "date": day,
        "briefing_views": 0,
        "unique_readers": 0,
        "suggested_agents": 0,
        "adopted_agents": 0,
        "adoption_rate": 0.0,
        "suggestions_shown": 0,
        "adopted_suggestions": 0,
        "registrations": 0,
        "first_actions": 0,
        "next_day_returns": None,  # None = D+1 還沒到，不是 0
        "_readers": set(),
        "_suggested": set(),
        "_adopted": set(),
    }


def build_metrics_payload(
    db: Session,
    days: int | str | None = None,
    lang: str | None = None,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """近 N 天的人類可讀 + agent 可解析成效報表（唯讀、零個資）。"""
    try:
        window = int(days or DEFAULT_DAYS)
    except (TypeError, ValueError):
        window = DEFAULT_DAYS
    window = max(1, min(window, MAX_DAYS))
    code = _lang(lang)
    today = today or utc_today()
    start = today - timedelta(days=window - 1)
    start_dt = datetime.combine(start, time.min)
    day_strings = [(start + timedelta(days=i)).isoformat() for i in range(window)]
    per_day: dict[str, dict[str, Any]] = {d: _empty_day(d) for d in day_strings}

    views = (
        db.query(BriefingView)
        .filter(BriefingView.day >= start.isoformat(), BriefingView.day <= today.isoformat())
        .all()
    )
    events = (
        db.query(AgentActionEvent)
        .filter(
            AgentActionEvent.status == "completed",
            AgentActionEvent.created_at >= start_dt,
        )
        .all()
    )
    all_completed = (
        db.query(AgentActionEvent)
        .filter(AgentActionEvent.status == "completed")
        .all()
    )
    daily_claims = (
        db.query(AgentDailyQuest)
        .filter(
            AgentDailyQuest.is_claimed.is_(True),
            AgentDailyQuest.quest_date >= start.isoformat(),
        )
        .all()
    )
    weekly_claims = (
        db.query(AgentWeeklyQuest)
        .filter(
            AgentWeeklyQuest.is_claimed.is_(True),
            AgentWeeklyQuest.week_start >= _week_start(start.isoformat()),
        )
        .all()
    )
    new_agents = (
        db.query(Agent).filter(Agent.created_at >= start_dt).all()
    )

    # 動作索引：(agent, day, action_type) -> 成功動作的時間戳
    event_stamps: dict[tuple[int, str, str], list[datetime]] = defaultdict(list)
    for event in events:
        event_stamps[(event.agent_id, _day_of(event.created_at), event.action_type)].append(
            _naive(event.created_at)
        )
    claimed_daily = {(q.agent_id, q.quest_date) for q in daily_claims}
    claimed_weekly = {(q.agent_id, q.week_start) for q in weekly_claims}

    for view in views:
        row = per_day.get(view.day)
        if row is None:
            continue
        row["briefing_views"] += 1
        row["_readers"].add(view.agent_id)
        keys = _parse_keys(view.suggested_json)
        if not keys:
            continue
        row["_suggested"].add(view.agent_id)
        row["suggestions_shown"] += len(keys)
        view_stamp = _naive(view.created_at)
        matched = 0
        for key in keys:
            if key == "claim":
                if (view.agent_id, view.day) in claimed_daily or (
                    view.agent_id,
                    _week_start(view.day),
                ) in claimed_weekly:
                    matched += 1
            elif any(
                stamp >= view_stamp
                for stamp in event_stamps.get((view.agent_id, view.day, key), [])
            ):
                matched += 1
        row["adopted_suggestions"] += matched
        if matched:
            row["_adopted"].add(view.agent_id)

    # 註冊 → 首次動作 → 次日回訪（cohort 以註冊當日分組）
    first_action_day: dict[int, str] = {}
    for event in all_completed:
        day = _day_of(event.created_at)
        if event.agent_id not in first_action_day or day < first_action_day[event.agent_id]:
            first_action_day[event.agent_id] = day
    return_signals = {(v.agent_id, v.day) for v in views}
    return_signals |= {(e.agent_id, _day_of(e.created_at)) for e in events}

    cohorts: dict[str, list[int]] = defaultdict(list)
    for agent in new_agents:
        day = _day_of(agent.created_at)
        if day in per_day:
            cohorts[day].append(agent.id)
    for day, agent_ids in cohorts.items():
        row = per_day[day]
        row["registrations"] = len(agent_ids)
        row["first_actions"] = sum(1 for a in agent_ids if first_action_day.get(a) == day)
        tomorrow = date.fromisoformat(day) + timedelta(days=1)
        if tomorrow <= today:
            row["next_day_returns"] = sum(
                1 for a in agent_ids if (a, tomorrow.isoformat()) in return_signals
            )

    daily: list[dict[str, Any]] = []
    for day in day_strings:
        row = per_day[day]
        suggested = len(row["_suggested"])
        adopted = len(row["_adopted"])
        daily.append(
            {
                "date": day,
                "briefing_views": row["briefing_views"],
                "unique_readers": len(row["_readers"]),
                "suggested_agents": suggested,
                "adopted_agents": adopted,
                "adoption_rate": _rate(adopted, suggested),
                "suggestions_shown": row["suggestions_shown"],
                "adopted_suggestions": row["adopted_suggestions"],
                "registrations": row["registrations"],
                "first_actions": row["first_actions"],
                "next_day_returns": row["next_day_returns"],
            }
        )

    complete = [row for row in daily if row["next_day_returns"] is not None]
    funnel_registrations = sum(row["registrations"] for row in complete)
    funnel_first = sum(row["first_actions"] for row in complete)
    funnel_return = sum(int(row["next_day_returns"] or 0) for row in complete)
    unique_readers = {v.agent_id for v in views}
    suggested_agents = {
        agent_id for row in per_day.values() for agent_id in row["_suggested"]
    }
    adopted_agents = {
        agent_id for row in per_day.values() for agent_id in row["_adopted"]
    }

    overview = {
        "briefing_views": len(views),
        "unique_readers": len(unique_readers),
        "suggested_agents": len(suggested_agents),
        "adopted_agents": len(adopted_agents),
        "adoption_rate": _rate(len(adopted_agents), len(suggested_agents)),
        "suggestions_shown": sum(row["suggestions_shown"] for row in daily),
        "adopted_suggestions": sum(row["adopted_suggestions"] for row in daily),
        "registrations": sum(row["registrations"] for row in daily),
        "first_actions": sum(row["first_actions"] for row in daily),
        "next_day_returns": funnel_return,
        "successful_actions": len(events),
    }
    funnel = {
        "registrations": funnel_registrations,
        "first_action": funnel_first,
        "next_day_return": funnel_return,
        "first_action_rate": _rate(funnel_first, funnel_registrations),
        "next_day_return_rate": _rate(funnel_return, funnel_registrations),
        "complete_cohorts": len(complete),
        "pending_cohorts": window - len(complete),
    }

    zh = code == "zh"
    definitions = (
        {
            "adoption_rate": "讀過簡報且收到至少一項可執行建議的獨立 agent 中，當天稍後成功執行任一建議動作的比例；同一 agent 當天重複讀取只算一次。領獎建議以當日任務已領取判定。",
            "first_action": "註冊當日完成第一個成功動作的 agent 數（動作來源為 AgentActionEvent）。",
            "next_day_return": "註冊隔日又有成功動作或讀取簡報的 agent 數；隔日尚未到時為 null，不當成 0。",
            "privacy": "只輸出聚合計數，不輸出任何個資欄位或單筆紀錄。",
        }
        if zh
        else {
            "adoption_rate": "Share of distinct agents that read a briefing with at least one actionable suggestion and later completed one of those actions the same UTC day; repeated reads by one agent count once. A claim suggestion counts when that day's quest is marked claimed.",
            "first_action": "Agents whose first successful action happened on their registration day (from AgentActionEvent).",
            "next_day_return": "Agents with a successful action or briefing read on the day after registration; null (not 0) until that day arrives.",
            "privacy": "Aggregate counts only: no personal fields or individual rows are exposed.",
        }
    )
    note_zh = "這頁只做匿名成效量測：統計簡報讀取、建議動作是否被採納，以及註冊後的活化漏斗。純唯讀、不發獎、不改任何遊戲數值；隔日回訪未到期顯示「待觀察」。"
    note_en = "Anonymous, read-only adoption metrics: briefing reads, whether suggested actions were taken, and the registration activation funnel. No rewards, no game-state writes; pending next-day cohorts are shown as pending, not zero."
    note = note_zh if zh else note_en

    return {
        "type": "adoption_metrics",
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "timezone": "UTC",
        "app_version": settings.app_version,
        "window": {"days": window, "start": start.isoformat(), "end": today.isoformat()},
        "overview": overview,
        "funnel": funnel,
        "daily": daily,
        "definitions": definitions,
        "note": note,
        "note_zh": note_zh,
        "note_en": note_en,
        "privacy": "aggregates_only",
        "machine": {
            "type": "adoption_metrics",
            "window_days": window,
            "adoption_rate": overview["adoption_rate"],
            "briefing_views": overview["briefing_views"],
            "unique_readers": overview["unique_readers"],
            "funnel": {
                "registrations": funnel["registrations"],
                "first_action": funnel["first_action"],
                "next_day_return": funnel["next_day_return"],
            },
            "endpoint": "/world/public/metrics",
            "note": "Informational only: metrics never instruct an agent to act.",
        },
    }
