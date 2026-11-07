"""尋訪（尋寶／尋人才）：agent 花金幣與體力出城，帶回人才、物資或空手而歸。

設計重點：
1. **不改 DB schema**：每日次數與尋訪動態都存在 `system_state`（一天一個 key，量極小）。
2. **可決策、不可作弊**：agent 自選 focus / budget；結果由
   `sha256(jwt_secret | agent_id | date | attempt | focus | budget)` 決定，
   外部無法預知（jwt_secret 是伺服器秘密），也無法指定想要的人才。
3. **先檢查再扣款**：row lock 重讀 agent，確認體力、金幣、當日次數都通過，
   才一次性扣款 → 發獎。任何一個不過就什麼都不改。
4. **冪等**：走既有 `AgentActionEvent` 佇列；已完成事件重播直接回原結果，
   不會重複扣款，也不會重複累加當日次數。
5. **是金幣出口，不是印鈔機**：物資回報永遠低於禮金，人才回報是聲望與能力，
   榜首數萬金的諸侯才有理由把錢花在這裡，而不是繼續囤積。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..config import settings
from ..errors import AppError
from ..models import Agent
from ..rules import (
    SCOUT_ABILITY_CAP,
    SCOUT_ABILITY_NAMES,
    SCOUT_BUDGETS,
    SCOUT_DAILY_LIMIT,
    SCOUT_ENERGY_COST,
    SCOUT_FOCUS,
    SCOUT_FOCUS_BONUS,
    SCOUT_TALENT_TITLES,
)
from .system_state import append_to_list, get_list, get_state, set_state


def _utc_day(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).date().isoformat()


def _lang(value: str | None) -> str:
    return "en" if value == "en" else "zh"


def validate_request(focus: object, budget: object) -> dict:
    """正規化尋訪參數；欄位已在路由層做過白名單檢查，這裡再防禦一次。"""
    resolved_focus = "balanced" if focus is None else focus
    resolved_budget = 100 if budget is None else budget
    if not isinstance(resolved_focus, str) or resolved_focus.strip().lower() not in SCOUT_FOCUS:
        raise AppError(
            "INVALID_SCOUT_FOCUS",
            f"focus must be one of {', '.join(SCOUT_FOCUS)}.",
            status_code=422,
        )
    if (
        isinstance(resolved_budget, bool)
        or not isinstance(resolved_budget, int)
        or resolved_budget not in SCOUT_BUDGETS
    ):
        raise AppError(
            "INVALID_SCOUT_BUDGET",
            f"budget must be one of {sorted(SCOUT_BUDGETS)} gold.",
            status_code=422,
        )
    return {"focus": resolved_focus.strip().lower(), "budget": resolved_budget}


def _rolls(agent_id: int, day: str, attempt: int, focus: str, budget: int) -> list[float]:
    raw = f"{settings.jwt_secret}|{agent_id}|{day}|{attempt}|{focus}|{budget}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return [int(digest[i : i + 8], 16) / 0xFFFFFFFF for i in (0, 8, 16, 24)]


def _pick_outcome(focus: str, budget: int, roll: float) -> str:
    cfg = SCOUT_BUDGETS[budget]
    talent_p = cfg["talent_chance"] + (SCOUT_FOCUS_BONUS if focus == "talent" else 0)
    supply_p = cfg["supply_chance"] + (SCOUT_FOCUS_BONUS if focus == "supply" else 0)
    if focus == "supply":
        talent_p -= SCOUT_FOCUS_BONUS / 2
    if focus == "talent":
        supply_p -= SCOUT_FOCUS_BONUS / 2
    # 至少保留 2% 空手率，重金禮聘也不是必中。
    cap = 0.98
    if roll < min(talent_p, cap):
        return "talent"
    if roll < min(talent_p + supply_p, cap):
        return "supply"
    return "nothing"


def _range_value(bounds: tuple[int, int], roll: float) -> int:
    low, high = bounds
    return int(low + roll * (high - low))


def _summarize(outcome: str, reward: dict, focus: str, budget: int) -> tuple[str, str]:
    if outcome == "talent":
        title_zh, title_en = SCOUT_TALENT_TITLES[reward["ability"]]
        ability_zh, ability_en = SCOUT_ABILITY_NAMES[reward["ability"]]
        return (
            f"禮金 {budget} 金訪得{title_zh}：{ability_zh} +{reward['ability_gain']}、聲望 +{reward['reputation_gain']}。",
            f"Spent {budget} gold and found {title_en}: {ability_en} +{reward['ability_gain']}, "
            f"reputation +{reward['reputation_gain']}.",
        )
    if outcome == "supply":
        if reward["gold_gained"]:
            return (
                f"禮金 {budget} 金尋得商路，收回 {reward['gold_gained']} 金（仍淨支出 {budget - reward['gold_gained']} 金）。",
                f"Spent {budget} gold and recovered {reward['gold_gained']} gold from a trade route "
                f"(net {budget - reward['gold_gained']} gold spent).",
            )
        return (
            f"禮金 {budget} 金尋得 {reward['food_gained']} 糧。",
            f"Spent {budget} gold and found {reward['food_gained']} food.",
        )
    return (
        f"禮金 {budget} 金，無功而返。",
        f"Spent {budget} gold and returned empty-handed.",
    )


def run_scout(db: Session, agent: Agent, payload: dict, *, now: datetime | None = None) -> dict:
    """在同一個交易內檢查 → 扣款 → 發獎；呼叫者負責 commit / rollback。"""
    deal = validate_request(payload.get("focus"), payload.get("budget"))
    focus, budget = deal["focus"], deal["budget"]
    day = _utc_day(now)

    locked = db.query(Agent).filter(Agent.id == agent.id).with_for_update().first()
    if locked is None:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)

    state_key = f"scout.{locked.id}.{day}"
    try:
        used = int(get_state(db, state_key, default="0") or 0)
    except ValueError:
        used = 0
    if used >= SCOUT_DAILY_LIMIT:
        raise AppError(
            "SCOUT_DAILY_LIMIT_REACHED",
            f"Scouting limit reached ({SCOUT_DAILY_LIMIT} per UTC day).",
            status_code=429,
        )
    if locked.energy < SCOUT_ENERGY_COST:
        raise AppError("INSUFFICIENT_ENERGY", "Not enough energy for this action.", status_code=422)
    if locked.gold < budget:
        raise AppError(
            "INSUFFICIENT_RESOURCES",
            f"Not enough gold: need {budget}, have {locked.gold}.",
            status_code=422,
        )

    attempt = used + 1
    rolls = _rolls(locked.id, day, attempt, focus, budget)
    outcome = _pick_outcome(focus, budget, rolls[0])
    cfg = SCOUT_BUDGETS[budget]
    reward: dict = {
        "food_gained": 0,
        "gold_gained": 0,
        "reputation_gain": 0,
        "ability": None,
        "ability_gain": 0,
        "talent_title_zh": "",
        "talent_title_en": "",
    }

    if outcome == "talent":
        ability = list(SCOUT_ABILITY_NAMES)[min(3, int(rolls[1] * 4))]
        before = getattr(locked, ability)
        after = min(SCOUT_ABILITY_CAP, before + cfg["ability_gain"])
        gain = after - before
        setattr(locked, ability, after)
        rep = _range_value(cfg["reputation"], rolls[2])
        if gain == 0:
            rep *= 2  # 能力已滿時，人才改以雙倍聲望回報，尋訪仍有意義。
        locked.reputation += rep
        title_zh, title_en = SCOUT_TALENT_TITLES[ability]
        reward.update(
            {
                "ability": ability,
                "ability_gain": gain,
                "reputation_gain": rep,
                "talent_title_zh": title_zh,
                "talent_title_en": title_en,
                "ability_before": before,
                "ability_after": after,
            }
        )
    elif outcome == "supply":
        if rolls[1] < 0.5:
            back = min(_range_value(cfg["gold_back"], rolls[2]), budget - 1)
            reward["gold_gained"] = back
            locked.gold += back
        else:
            food = _range_value(cfg["food"], rolls[2])
            reward["food_gained"] = food
            locked.food += food

    locked.gold -= budget
    locked.energy -= SCOUT_ENERGY_COST
    db.add(locked)

    summary_zh, summary_en = _summarize(outcome, reward, focus, budget)
    set_state(db, state_key, str(attempt))
    append_to_list(
        db,
        f"scout.recent.{day}",
        json.dumps(
            {
                "agent_id": locked.id,
                "agent_name": locked.name,
                "date": day,
                "focus": focus,
                "budget": budget,
                "outcome": outcome,
                "summary_zh": summary_zh,
                "summary_en": summary_en,
            },
            ensure_ascii=False,
        ),
        max_size=30,
    )

    return {
        "action_type": "scout",
        "focus": focus,
        "budget": budget,
        "attempt": attempt,
        "attempts_left": SCOUT_DAILY_LIMIT - attempt,
        "daily_limit": SCOUT_DAILY_LIMIT,
        "energy_cost": SCOUT_ENERGY_COST,
        "gold_spent": budget,
        "outcome": outcome,
        "reward": reward,
        "summary_zh": summary_zh,
        "summary_en": summary_en,
        "new_gold": locked.gold,
        "new_food": locked.food,
        "new_energy": locked.energy,
        "new_reputation": locked.reputation,
    }


def catalog_payload(db: Session, lang: str | None = None, *, now: datetime | None = None) -> dict:
    """公開規則 + 當日尋訪動態：免登入，給 agent 決策與人類觀戰。"""
    code = _lang(lang)
    day = _utc_day(now)
    recent: list[dict] = []
    for raw in get_list(db, f"scout.recent.{day}")[:12]:
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            recent.append(row)
    return {
        "lang": code,
        "daily_limit": SCOUT_DAILY_LIMIT,
        "energy_cost": SCOUT_ENERGY_COST,
        "focus_options": list(SCOUT_FOCUS),
        "focus_bonus": SCOUT_FOCUS_BONUS,
        "budgets": [
            {
                "gold": gold,
                "talent_chance": cfg["talent_chance"],
                "supply_chance": cfg["supply_chance"],
                "ability_gain": cfg["ability_gain"],
            }
            for gold, cfg in sorted(SCOUT_BUDGETS.items())
        ],
        "how_to_scout": {
            "method": "POST",
            "path": "/action/work",
            "auth": "X-API-Key (the same key issued at bootstrap)",
            "body": {"action_type": "scout", "payload": {"focus": "talent", "budget": 500}},
        },
        "recent": recent,
        "recent_date": day,
        "note_zh": "尋訪由諸侯自行決定；結果由伺服器決定，不能指定，也不能重試到滿意為止。物資回報永遠低於禮金，商城 buy 才是穩定取得糧食的方式。",
        "note_en": "Only agents decide whether to scout; outcomes are server-decided and cannot be re-rolled. Supply returns are always below the gold spent — the market buy action is the reliable way to get food.",
    }
