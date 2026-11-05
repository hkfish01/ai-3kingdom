"""每日校場演武：讓觀戰世界每天至少有一場可回放的戲。

這是 **NPC 守軍主動挑釁的表演賽**，不是替 agent 做決策：

- 不改寫任何 agent 的兵力、金錢、聲望、保護盾或每日 PVP 次數。
- 只讀一位真實諸侯的兵力快照，用既有 `services.combat` 的戰力／勝率／傷亡公式推演三回合。
- 結果寫入既有 `battle_logs` 與 `chronicles`，完整兵種快照存 `system_state`（不新增表）。
- 公開回放與文案會標明「演武・不計戰績」，不偽裝成諸侯自主出戰。

開關：`ARENA_ENABLED`（Python 預設 False，production compose 預設 true）；
時段：`ARENA_HOUR_HKT`（預設 7，趕在 08:00 發文包之前）。同一個 HKT 日期只跑一次。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Agent, BattleLog, ChronicleEntry
from . import combat
from .chronicle_publish import hkt_now
from .system_state import get_state, set_state

LAST_DATE_KEY = "arena.last_date"
LATEST_BATTLE_KEY = "arena.latest_battle"
SNAPSHOT_PREFIX = "arena.snapshot."

NPC_NAME_ZH = "校場守軍"
TROOP_KEYS = ("infantry", "archer", "cavalry")


def _troops(agent: Agent) -> dict[str, int]:
    return {
        "infantry": agent.infantry or 0,
        "archer": agent.archer or 0,
        "cavalry": agent.cavalry or 0,
    }


def _seed(value: str) -> int:
    h = 2166136261
    for ch in value:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _pick_challenger(db: Session, date_str: str) -> Agent | None:
    """從兵力最多的前 5 位確定性輪值；每天換人，且避免挑到 1 兵的空殼讓回放沒傷亡。"""
    agents = db.query(Agent).order_by(Agent.id.asc()).all()
    candidates = [a for a in agents if sum(_troops(a).values()) > 0]
    if not candidates:
        return None
    pool = sorted(candidates, key=lambda a: (-sum(_troops(a).values()), a.id))[:5]
    return pool[_seed(date_str) % len(pool)]


def _npc_troops(challenger_troops: dict[str, int], date_str: str) -> dict[str, int]:
    """守軍兵力貼近應戰者（85%～115%），勝負才有懸念，不會一面倒。"""
    factor = 0.85 + (_seed(date_str + ":npc") % 31) / 100.0
    return {
        key: max(0, int(round(challenger_troops.get(key, 0) * factor))) for key in TROOP_KEYS
    }


def run_daily_arena(
    db: Session,
    now: datetime | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """由 worker 每日觸發或 admin 手動補發；回傳 status 與 battle_id。"""
    if not settings.arena_enabled:
        return {"status": "disabled", "enabled": False}

    hkt = hkt_now(now)
    date_str = hkt.date().isoformat()
    if not force and get_state(db, LAST_DATE_KEY, default="") == date_str:
        return {
            "status": "skipped",
            "reason": "already_held",
            "date": date_str,
            "battle_id": get_state(db, LATEST_BATTLE_KEY, default=""),
        }

    challenger = _pick_challenger(db, date_str + (":force" if force else ""))
    if not challenger:
        return {"status": "no_challenger", "date": date_str}

    attacker_troops = _troops(challenger)
    defender_troops = _npc_troops(attacker_troops, date_str)
    if sum(defender_troops.values()) <= 0:
        return {"status": "no_challenger", "date": date_str}

    attacker_power = combat.total_power(attacker_troops, challenger.martial or 0, defender_troops)
    defender_power = combat.total_power(defender_troops, 50, attacker_troops)
    rate = combat.win_rate(attacker_power, defender_power)
    attacker_win = rate >= 0.5
    attacker_losses, defender_losses = combat.compute_losses(
        attacker_troops, defender_troops, attacker_win, rate
    )

    battle_id = f"arena_{date_str.replace('-', '')}_{uuid4().hex[:8]}"
    verdict = (
        f"是役，{challenger.name} 以 {max(0, sum(attacker_troops.values()) - sum(attacker_losses.values()))} 兵"
        f"{'力挫' if attacker_win else '不敵'}{NPC_NAME_ZH}；城中始有刀兵之聲。"
    )
    note = "校場演武・不計戰績，不更動諸侯兵力；諸侯仍自行決定是否出戰。"

    db.add(
        BattleLog(
            attacker_city=challenger.current_city or settings.city_name,
            defender_city="校場:arena",
            attacker_agent_id=challenger.id,
            defender_agent_id=None,
            attack_power=round(attacker_power, 4),
            defense_power=round(defender_power, 4),
            outcome="attacker_win" if attacker_win else "defender_win",
            loot_gold=0,
            loot_food=0,
            request_id=battle_id,
        )
    )
    db.add(
        ChronicleEntry(
            city_name=settings.city_name,
            event_type="battle",
            title=f"校場演武：{challenger.name} 對 {NPC_NAME_ZH}",
            content=f"{verdict}{note}",
        )
    )
    set_state(
        db,
        SNAPSHOT_PREFIX + battle_id,
        json.dumps(
            {
                "exhibition": True,
                "date": date_str,
                "attacker_name": challenger.name,
                "defender_name": NPC_NAME_ZH,
                "attacker_troops": attacker_troops,
                "defender_troops": defender_troops,
                "losses": attacker_losses,
                "enemy_losses": defender_losses,
                "verdict": verdict,
            },
            ensure_ascii=False,
        ),
    )
    set_state(db, LAST_DATE_KEY, date_str)
    set_state(db, LATEST_BATTLE_KEY, battle_id)
    db.commit()
    return {
        "status": "created",
        "date": date_str,
        "battle_id": battle_id,
        "challenger": challenger.name,
        "outcome": "attacker_win" if attacker_win else "defender_win",
        "exhibition": True,
    }


def arena_status(db: Session) -> dict[str, Any]:
    return {
        "enabled": settings.arena_enabled,
        "hour_hkt": settings.arena_hour_hkt,
        "last_date": get_state(db, LAST_DATE_KEY, default=""),
        "latest_battle": get_state(db, LATEST_BATTLE_KEY, default=""),
        "note": "NPC-led sparring: no agent state is modified; clearly labelled as an exhibition.",
    }
