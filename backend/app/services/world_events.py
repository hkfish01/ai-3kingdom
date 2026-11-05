"""世界事件引擎：稀缺 + 期限 + 不可逆。

設計原則（與 daily_chronicle.py 一致）：
- **不新增資料表**：事件狀態存 system_state（JSON），效果寫回既有 Agent / City 欄位，
  過程寫入 append-only 的 chronicles。既有部署不需要 migration。
- **可關閉**：settings.world_events_enabled = False 時，本模組完全不讀不寫，
  既有 API 回傳與既有測試維持原樣。
- **不可逆**：每個事件只能 pending -> active -> resolved/expired 單向轉移；
  一旦結案就不再回寫，且當下已寫入公開史記（史記表本身全專案只有 INSERT）。

三個計時事件：
  famine        洛陽糧盡：城倉見底，限期補糧；逾期城牆受損。
  chancellor    丞相唯一席：全城只一席，限期有人升任；逾期國庫空耗。
  three_powers  三城分立：限期出現三個各有二員以上的勢力；逾期城牆受損。
一條常設規則：
  pact          盟約可結可背；背盟者扣聲望，且被公開史記記載。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..config import settings
from ..errors import AppError
from ..models import Agent, City, Faction
from .chronicle import write_chronicle
from .system_state import append_to_list, get_list, get_state, set_state

EVENT_STATE_KEY = "world.event.state"
EVENT_HISTORY_KEY = "world.event.history"
EVENT_LAST_EVAL_KEY = "world.event.last_eval"

EVENT_TYPE = "world_event"
BETRAYAL_EVENT_TYPE = "world_event_betrayal"

CHANCELLOR_ROLES = ("丞相", "相國")
CHANCELLOR_GOLD_PENALTY = 500
THREE_POWERS_WALL_PENALTY = 30
THREE_POWERS_MIN_MEMBERS = 2
THREE_POWERS_TARGET_FACTIONS = 3

EVENT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "famine": {
        "title_zh": "洛陽糧盡",
        "title_en": "The Granary Runs Empty",
        "scarcity_zh": "城倉糧草須補足，諸侯須自掏存糧",
        "scarcity_en": "The city granary must be refilled from the lords' own stores",
        "timed": True,
    },
    "chancellor": {
        "title_zh": "丞相唯一席",
        "title_en": "Only One Chancellor",
        "scarcity_zh": "丞相之席全城僅一，先到者得",
        "scarcity_en": "Exactly one Chancellor seat exists in the whole city",
        "timed": True,
    },
    "three_powers": {
        "title_zh": "三城分立",
        "title_en": "Three Powers Must Stand",
        "scarcity_zh": "須有三個勢力各擁二員以上",
        "scarcity_en": "Three factions must each field at least two members",
        "timed": True,
    },
    "pact": {
        "title_zh": "盟約與背刺",
        "title_en": "Oaths and Betrayals",
        "scarcity_zh": "每位諸侯同時只能有一個盟約；背盟者扣聲望並載入史記",
        "scarcity_en": "One oath at a time; breaking one costs reputation and is recorded publicly",
        "timed": False,
    },
}


# ---------------------------------------------------------------------------
# 狀態讀寫
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _empty_state() -> dict[str, Any]:
    return {"revision": 0, "events": {}, "pacts": [], "betrayals": []}


def load_state(db: Session) -> dict[str, Any]:
    raw = get_state(db, EVENT_STATE_KEY)
    if not raw:
        return _empty_state()
    try:
        state = json.loads(raw)
    except json.JSONDecodeError:
        return _empty_state()
    if not isinstance(state, dict):
        return _empty_state()
    for key, default in _empty_state().items():
        if key not in state or not isinstance(state[key], type(default)):
            state[key] = default
    return state


def save_state(db: Session, state: dict[str, Any]) -> None:
    """只 set_state，不 commit；由呼叫端在同一個 transaction 內連同效果一起 commit。"""
    state["revision"] = int(state.get("revision", 0)) + 1
    set_state(db, EVENT_STATE_KEY, json.dumps(state, ensure_ascii=False))


def _record_history(db: Session, changes: list[str]) -> None:
    """一次寫入歷史。

    同一個 transaction 內重複呼叫 append_to_list 會對同一個 key 產生多筆
    pending INSERT，flush 時撞 system_state.key 的 UNIQUE 約束。
    """
    items = get_list(db, EVENT_HISTORY_KEY)
    stamp = _iso(_now())
    for change in changes:
        items.insert(0, f"{stamp} {change}")
    set_state(db, EVENT_HISTORY_KEY, json.dumps(items[:30], ensure_ascii=False))


def _local_city(db: Session) -> City | None:
    city = db.query(City).filter(City.name == settings.city_name).first()
    if city:
        return city
    return db.query(City).first()


def _chancellor_count(db: Session) -> int:
    return (
        db.query(func.count(Agent.id))
        .filter(or_(*[Agent.role == r for r in CHANCELLOR_ROLES]))
        .scalar()
        or 0
    )


def _strong_faction_count(db: Session) -> int:
    rows = (
        db.query(Agent.faction_id, func.count(Agent.id))
        .filter(Agent.faction_id.isnot(None))
        .group_by(Agent.faction_id)
        .all()
    )
    return sum(1 for _, count in rows if count >= THREE_POWERS_MIN_MEMBERS)


def _faction_count(db: Session) -> int:
    return db.query(func.count(Faction.id)).scalar() or 0


# ---------------------------------------------------------------------------
# 事件判定（唯讀）
# ---------------------------------------------------------------------------

def _should_open(db: Session, event_id: str) -> bool:
    if event_id == "famine":
        city = _local_city(db)
        return bool(city and city.treasury_food <= settings.world_events_famine_threshold)
    return True


def _is_resolved(db: Session, event_id: str) -> bool:
    if event_id == "famine":
        city = _local_city(db)
        return bool(city and city.treasury_food >= settings.world_events_famine_relief_target)
    if event_id == "chancellor":
        return _chancellor_count(db) >= 1
    if event_id == "three_powers":
        return _strong_faction_count(db) >= THREE_POWERS_TARGET_FACTIONS
    return False


def _progress(db: Session, event_id: str, lang: str) -> str:
    zh = lang == "zh"
    if event_id == "famine":
        city = _local_city(db)
        food = city.treasury_food if city else 0
        target = settings.world_events_famine_relief_target
        return f"城倉 {food} / {target} 糧" if zh else f"Granary {food} / {target} food"
    if event_id == "chancellor":
        n = _chancellor_count(db)
        return f"丞相席 1，已佔 {n}" if zh else f"Chancellor seats 1, filled {n}"
    if event_id == "three_powers":
        n = _strong_faction_count(db)
        return (
            f"已成 {n} / {THREE_POWERS_TARGET_FACTIONS} 強勢力（現有 {_faction_count(db)} 個勢力）"
            if zh
            else f"{n} / {THREE_POWERS_TARGET_FACTIONS} strong factions ({_faction_count(db)} total)"
        )
    return ""


def _apply_expiry(db: Session, event_id: str) -> str:
    """逾期後果：寫回既有欄位，回傳一段可進史記的文字。不可逆。"""
    city = _local_city(db)
    if event_id == "famine":
        penalty = settings.world_events_famine_wall_penalty
        if city:
            city.city_wall = max(0, city.city_wall - penalty)
            db.add(city)
        return f"糧盡而城未救，城牆損 {penalty}。"
    if event_id == "chancellor":
        if city:
            city.treasury_gold = max(0, city.treasury_gold - CHANCELLOR_GOLD_PENALTY)
            db.add(city)
        return f"丞相久懸，朝政空轉，國庫耗金 {CHANCELLOR_GOLD_PENALTY}。"
    if event_id == "three_powers":
        if city:
            city.city_wall = max(0, city.city_wall - THREE_POWERS_WALL_PENALTY)
            db.add(city)
        return f"天下未分，諸侯各自觀望，城牆損 {THREE_POWERS_WALL_PENALTY}。"
    return "期限已至。"


# ---------------------------------------------------------------------------
# 狀態機推進
# ---------------------------------------------------------------------------

def evaluate_world_events(db: Session, now: datetime | None = None, commit: bool = True) -> dict[str, Any]:
    """每日推進一次。worker 會先跑這個再跑史記，讓當日事件被寫進史記。

    單向轉移：pending -> active -> resolved / expired，之後永不回寫。
    """
    if not settings.world_events_enabled:
        return {"enabled": False, "changes": []}

    now = now or _now()
    state = load_state(db)
    changes: list[str] = []

    for event_id, meta in EVENT_DEFINITIONS.items():
        if not meta["timed"]:
            continue
        record = state["events"].get(event_id)

        if record is None:
            if not _should_open(db, event_id):
                continue
            record = {
                "status": "active",
                "opened_at": _iso(now),
                "deadline_utc": _iso(now + timedelta(hours=settings.world_events_deadline_hours)),
                "irreversible": True,
                "outcome": None,
            }
            state["events"][event_id] = record
            changes.append(f"{event_id}:opened")
            write_chronicle(
                db,
                event_type=EVENT_TYPE,
                title=f"【天下有事】{meta['title_zh']}",
                content=(
                    f"{meta['title_zh']}：{meta['scarcity_zh']}。"
                    f"限 {record['deadline_utc']} 前定奪；過期後果不可逆，史官將如實記下。"
                ),
            )
            continue

        # 已結案的事件永不再動 —— 這就是「不可逆」。
        if record.get("status") in ("resolved", "expired"):
            continue

        if _is_resolved(db, event_id):
            record["status"] = "resolved"
            record["outcome"] = "resolved"
            record["resolved_at"] = _iso(now)
            changes.append(f"{event_id}:resolved")
            write_chronicle(
                db,
                event_type=EVENT_TYPE,
                title=f"【天下已定】{meta['title_zh']}",
                content=f"{meta['title_zh']}已解。{_progress(db, event_id, 'zh')}。此事已入史，不可逆。",
            )
        elif _parse_iso(str(record.get("deadline_utc", ""))) <= now:
            effect = _apply_expiry(db, event_id)
            record["status"] = "expired"
            record["outcome"] = "expired"
            record["resolved_at"] = _iso(now)
            changes.append(f"{event_id}:expired")
            write_chronicle(
                db,
                event_type=EVENT_TYPE,
                title=f"【天下已定】{meta['title_zh']}・逾期",
                content=f"期限已過，{effect}此事已入史，不可逆。",
            )

    if changes:
        save_state(db, state)
        _record_history(db, changes)
        if commit:
            db.commit()
    return {"enabled": True, "changes": changes}


# ---------------------------------------------------------------------------
# 對外呈現（公開免登入 + 餵進史記）
# ---------------------------------------------------------------------------

def public_events(db: Session, lang: str = "zh") -> list[dict[str, Any]]:
    zh = lang == "zh"
    state = load_state(db)
    active_pacts = [p for p in state["pacts"] if p.get("status") == "active"]
    out: list[dict[str, Any]] = []

    for event_id, meta in EVENT_DEFINITIONS.items():
        record = state["events"].get(event_id) if meta["timed"] else None
        status = record.get("status", "pending") if record else "standing"
        item: dict[str, Any] = {
            "id": event_id,
            "title": meta["title_zh"] if zh else meta["title_en"],
            "description": meta["scarcity_zh"] if zh else meta["scarcity_en"],
            "status": status,
            "irreversible": True,
            "timed": meta["timed"],
            "progress": _progress(db, event_id, lang) if settings.world_events_enabled and meta["timed"] else "",
        }
        if record:
            item["deadline_utc"] = record.get("deadline_utc")
            item["opened_at"] = record.get("opened_at")
            item["outcome"] = record.get("outcome")
        if event_id == "pact":
            item["active_pacts"] = len(active_pacts)
            item["betrayals"] = len(state["betrayals"])
        out.append(item)
    return out


def event_lines(db: Session, lang: str = "zh") -> list[str]:
    """史記要用的局勢句子。最多 3 行，避免擠掉原本的數據敘事。"""
    if not settings.world_events_enabled:
        return []
    zh = lang == "zh"
    state = load_state(db)
    lines: list[str] = []

    for event_id, meta in EVENT_DEFINITIONS.items():
        if not meta["timed"]:
            continue
        record = state["events"].get(event_id)
        if not record or record.get("status") != "active":
            continue
        deadline = str(record.get("deadline_utc", ""))[:10]
        progress = _progress(db, event_id, lang)
        if zh:
            lines.append(f"【天下有事】{meta['title_zh']}：{progress}；限 {deadline} 前定奪，過期不可逆。")
        else:
            lines.append(f"[Open crisis] {meta['title_en']}: {progress}; deadline {deadline}, irreversible.")

    betrayals = state.get("betrayals", [])
    if betrayals:
        last = betrayals[-1]
        if zh:
            lines.append(
                f"【背盟】{last.get('breaker_name', '某人')} 負 {last.get('victim_name', '故友')}，"
                f"聲望損 {last.get('penalty', 0)}，史官已書。"
            )
        else:
            lines.append(
                f"[Betrayal] {last.get('breaker_name', 'Someone')} broke faith with "
                f"{last.get('victim_name', 'an ally')}; reputation -{last.get('penalty', 0)}."
            )
    return lines[:3]


def enrich_facts_with_events(db: Session, facts: dict[str, Any]) -> dict[str, Any]:
    """純加法：關閉時原樣回傳，既有 20 個 facts key 一個都不動。"""
    if not settings.world_events_enabled:
        return facts
    enriched = dict(facts)
    enriched["events"] = public_events(db, "zh")
    enriched["event_lines_zh"] = event_lines(db, "zh")
    enriched["event_lines_en"] = event_lines(db, "en")
    enriched["active_events"] = sum(
        1 for e in enriched["events"] if e.get("status") == "active"
    )
    return enriched


# ---------------------------------------------------------------------------
# 可執行的玩法動作
# ---------------------------------------------------------------------------

def _require_enabled() -> None:
    if not settings.world_events_enabled:
        raise AppError("EVENTS_DISABLED", "世界事件引擎目前未啟用。", status_code=403)


def _active_pact_for(state: dict[str, Any], agent_id: int) -> dict[str, Any] | None:
    for pact in state["pacts"]:
        if pact.get("status") != "active":
            continue
        if agent_id in (pact.get("a_id"), pact.get("b_id")):
            return pact
    return None


def _apply_betrayal(
    db: Session,
    state: dict[str, Any],
    breaker: Agent,
    victim: Agent | None,
    pact: dict[str, Any],
) -> dict[str, Any]:
    penalty = settings.world_events_betrayal_penalty
    before = breaker.reputation or 0
    breaker.reputation = max(0, before - penalty)
    db.add(breaker)
    pact["status"] = "broken"
    pact["broken_at"] = _iso(_now())

    victim_name = victim.name if victim else str(pact.get("b_name") or pact.get("a_name") or "故友")
    record = {
        "at": _iso(_now()),
        "pact_id": pact.get("id"),
        "breaker_id": breaker.id,
        "breaker_name": breaker.name,
        "victim_id": victim.id if victim else None,
        "victim_name": victim_name,
        "penalty": before - breaker.reputation,
    }
    state["betrayals"].append(record)
    write_chronicle(
        db,
        event_type=BETRAYAL_EVENT_TYPE,
        title=f"【背盟】{breaker.name} 負 {victim_name}",
        content=(
            f"{breaker.name} 毀棄與 {victim_name} 之盟，聲望自 {before} 降為 {breaker.reputation}。"
            "此事不可逆，已載入公開史記，天下共見。"
        ),
    )
    return record


def contribute_food(db: Session, agent: Agent, amount: int) -> dict[str, Any]:
    """諸侯捐糧救城。這是 famine 唯一的可行動解法。"""
    _require_enabled()
    if amount <= 0:
        raise AppError("INVALID_REQUEST", "捐糧數量必須為正整數。")
    if amount > (agent.food or 0):
        raise AppError("INSUFFICIENT_RESOURCES", "存糧不足。")

    state = load_state(db)
    record = state["events"].get("famine")
    if not record or record.get("status") != "active":
        raise AppError("EVENT_NOT_ACTIVE", "洛陽糧盡事件目前未在進行中。", status_code=409)

    city = _local_city(db)
    if not city:
        raise AppError("CITY_NOT_FOUND", "找不到本地城池。")

    agent.food = (agent.food or 0) - amount
    city.treasury_food = (city.treasury_food or 0) + amount
    db.add(agent)
    db.add(city)
    write_chronicle(
        db,
        event_type=EVENT_TYPE,
        title=f"【輸糧】{agent.name} 捐糧 {amount}",
        content=f"{agent.name} 自倉中撥糧 {amount} 入城倉，現存 {city.treasury_food} 糧。",
    )

    resolved = False
    if city.treasury_food >= settings.world_events_famine_relief_target:
        record["status"] = "resolved"
        record["outcome"] = "relieved"
        record["resolved_at"] = _iso(_now())
        resolved = True
        write_chronicle(
            db,
            event_type=EVENT_TYPE,
            title="【天下已定】洛陽糧盡・已解",
            content=f"城倉補足 {city.treasury_food} 糧，糧盡之危已解。此事已入史，不可逆。",
        )

    save_state(db, state)
    append_to_list(db, EVENT_HISTORY_KEY, f"{_iso(_now())} famine:contributed:{agent.name}:{amount}")
    db.commit()
    return {
        "donated": amount,
        "agent_food": agent.food,
        "city_food": city.treasury_food,
        "relief_target": settings.world_events_famine_relief_target,
        "resolved": resolved,
    }


def form_pact(db: Session, agent: Agent, target: Agent) -> dict[str, Any]:
    """締結盟約。若自己已有盟約，改結新盟即構成背刺（扣聲望 + 公開記載）。"""
    _require_enabled()
    if target.id == agent.id:
        raise AppError("INVALID_REQUEST", "不能與自己結盟。")

    state = load_state(db)
    old = _active_pact_for(state, agent.id)
    betrayal = None
    if old:
        other_id = old["b_id"] if old["a_id"] == agent.id else old["a_id"]
        victim = db.get(Agent, other_id)
        if other_id == target.id:
            raise AppError("EVENT_PACT_EXISTS", "你們已有盟約。", status_code=409)
        betrayal = _apply_betrayal(db, state, agent, victim, old)

    if _active_pact_for(state, target.id):
        raise AppError("EVENT_PACT_EXISTS", "對方已有盟約在身。", status_code=409)

    pact_id = f"pact-{len(state['pacts']) + 1}"
    pact = {
        "id": pact_id,
        "a_id": agent.id,
        "a_name": agent.name,
        "b_id": target.id,
        "b_name": target.name,
        "status": "active",
        "created_at": _iso(_now()),
    }
    state["pacts"].append(pact)
    write_chronicle(
        db,
        event_type=EVENT_TYPE,
        title=f"【締盟】{agent.name} 與 {target.name}",
        content=f"{agent.name} 與 {target.name} 立盟。盟可背，背則聲望損、史官書之。",
    )
    save_state(db, state)
    append_to_list(db, EVENT_HISTORY_KEY, f"{_iso(_now())} pact:formed:{pact_id}")
    db.commit()
    return {"pact": pact, "betrayal": betrayal}


def break_pact(db: Session, agent: Agent) -> dict[str, Any]:
    _require_enabled()
    state = load_state(db)
    pact = _active_pact_for(state, agent.id)
    if not pact:
        raise AppError("EVENT_NO_PACT", "你目前沒有進行中的盟約。", status_code=404)
    other_id = pact["b_id"] if pact["a_id"] == agent.id else pact["a_id"]
    victim = db.get(Agent, other_id)
    record = _apply_betrayal(db, state, agent, victim, pact)
    save_state(db, state)
    append_to_list(db, EVENT_HISTORY_KEY, f"{_iso(_now())} pact:broken:{pact['id']}")
    db.commit()
    return {"betrayal": record}
