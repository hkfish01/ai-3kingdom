import json
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..api.deps import get_current_user
from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import ActionLog, Agent, AgentProtection, BattleLog, DungeonClear, PvpChallengeDaily, User
from ..schemas import PveChallengeRequest, PvpChallengeRequest
from ..services import combat
from ..services.chronicle import write_chronicle

router = APIRouter(tags=["combat"])
PVP_DAILY_LIMIT = 5
PVP_PROTECTION_HOURS = 2
MATCHMAKING_TARGET_MIN_WIN_RATE = 0.4
MATCHMAKING_TARGET_MAX_WIN_RATE = 0.6


def _get_owned_agent(db: Session, user_id: int, agent_id: int) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)
    if agent.owner_user_id != user_id:
        raise AppError("FORBIDDEN", "You do not own this agent.", status_code=403)
    return agent


def _troops_from_request(troops) -> dict:
    return combat.clamp_troops(troops.model_dump())


def _assert_troops_available(agent: Agent, troops: dict) -> None:
    if not combat.is_valid_troops(troops):
        raise AppError("INVALID_REQUEST", "Troop selection cannot be empty.", status_code=422)
    if troops["infantry"] > agent.infantry:
        raise AppError("INSUFFICIENT_TROOPS", "Not enough infantry.", status_code=422)
    if troops["archer"] > agent.archer:
        raise AppError("INSUFFICIENT_TROOPS", "Not enough archer.", status_code=422)
    if troops["cavalry"] > agent.cavalry:
        raise AppError("INSUFFICIENT_TROOPS", "Not enough cavalry.", status_code=422)


def _normalize_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _agent_troops(agent: Agent) -> dict:
    return combat.troop_summary({"infantry": agent.infantry, "archer": agent.archer, "cavalry": agent.cavalry})


def _agent_power(agent: Agent) -> float:
    return combat.raw_power(_agent_troops(agent), agent.martial)


def _split_losses(losses: dict[str, int], rounds: int = 3) -> list[dict[str, int]]:
    weights = [0.5, 0.3, 0.2][: max(1, rounds)]
    if len(weights) < rounds:
        weights.extend([0.0] * (rounds - len(weights)))
    out = [{t: 0 for t in ("infantry", "archer", "cavalry")} for _ in range(rounds)]
    for troop in ("infantry", "archer", "cavalry"):
        total = int(losses.get(troop, 0))
        assigned = 0
        for idx, weight in enumerate(weights):
            amount = int(round(total * weight))
            out[idx][troop] += amount
            assigned += amount
        remain = max(0, total - assigned)
        idx = 0
        while remain > 0 and idx < rounds:
            out[idx][troop] += 1
            remain -= 1
            idx = (idx + 1) % rounds
    return out


def _dominant_label(troops: dict[str, int]) -> str:
    mapping = {"infantry": "infantry_push", "archer": "archer_volley", "cavalry": "cavalry_charge"}
    top_type = "infantry"
    top_value = -1
    for troop in ("infantry", "archer", "cavalry"):
        value = troops.get(troop, 0)
        if value > top_value:
            top_type = troop
            top_value = value
    return mapping[top_type]


def _parse_json_field(raw: str, fallback: dict | None = None) -> dict:
    if not raw:
        return fallback or {}
    try:
        value = json.loads(raw)
        if isinstance(value, dict):
            return value
    except Exception:
        return fallback or {}
    return fallback or {}


def _extract_action_result_by_battle_id(db: Session, battle_id: str) -> tuple[ActionLog | None, dict]:
    candidates = (
        db.query(ActionLog)
        .filter(ActionLog.action_type.in_(["pve_challenge", "pvp_challenge"]))
        .order_by(ActionLog.id.desc())
        .limit(1000)
        .all()
    )
    for log in candidates:
        payload = _parse_json_field(log.result_json)
        if payload.get("battle_id") == battle_id:
            return log, payload
    return None, {}


def _rank_map(db: Session) -> dict[int, int]:
    rows = db.query(Agent).all()
    ranked = sorted(rows, key=lambda a: (-_agent_power(a), a.id))
    return {agent.id: idx + 1 for idx, agent in enumerate(ranked)}


def _utc_day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _get_or_create_daily_counter(db: Session, agent_id: int, day: str) -> PvpChallengeDaily:
    row = (
        db.query(PvpChallengeDaily)
        .filter(PvpChallengeDaily.agent_id == agent_id, PvpChallengeDaily.day == day)
        .order_by(PvpChallengeDaily.id.desc())
        .first()
    )
    if row:
        return row
    row = PvpChallengeDaily(agent_id=agent_id, day=day, count=0)
    db.add(row)
    db.flush()
    return row


def _is_agent_protected(db: Session, agent_id: int, now: datetime) -> bool:
    row = db.query(AgentProtection).filter(AgentProtection.agent_id == agent_id).first()
    if not row:
        return False
    return _normalize_utc(row.protected_until) > now


def _apply_protection(db: Session, agent_id: int, now: datetime) -> None:
    row = db.query(AgentProtection).filter(AgentProtection.agent_id == agent_id).first()
    protected_until = now + timedelta(hours=PVP_PROTECTION_HOURS)
    if row:
        row.protected_until = protected_until
        row.reason = "pvp_loss"
    else:
        row = AgentProtection(agent_id=agent_id, protected_until=protected_until, reason="pvp_loss")
    db.add(row)


@router.get("/pve/dungeons")
def list_pve_dungeons(current_user: User = Depends(get_current_user)):
    _ = current_user
    return {
        "success": True,
        "data": {
            "items": [
                {
                    "id": d.id,
                    "name": d.name,
                    "difficulty": d.difficulty,
                    "power_requirement": d.power_requirement,
                    "rewards": {
                        "gold": {"min": d.reward_gold[0], "max": d.reward_gold[1]},
                        "food": {"min": d.reward_food[0], "max": d.reward_food[1]},
                        "exp": d.reward_exp,
                    },
                    "first_clear_reward": {"gold": d.first_clear_gold} if d.first_clear_gold else None,
                }
                for d in combat.list_dungeons()
            ]
        },
    }


@router.post("/pve/challenge")
def pve_challenge(
    payload: PveChallengeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attacker = _get_owned_agent(db, current_user.id, payload.agent_id)
    dungeon = combat.get_dungeon(payload.dungeon_id)
    if not dungeon:
        raise AppError("INVALID_DUNGEON", "Dungeon does not exist.", status_code=404)

    attacker_troops = _troops_from_request(payload.troops)
    _assert_troops_available(attacker, attacker_troops)
    attacker_raw_power = combat.raw_power(attacker_troops, attacker.martial)
    if attacker_raw_power < dungeon.power_requirement:
        raise AppError("PVE_POWER_TOO_LOW", "Agent power is below dungeon requirement.", status_code=422)

    defender_troops = combat.clamp_troops(dungeon.enemy_troops)
    attacker_power = combat.total_power(attacker_troops, attacker.martial, defender_troops)
    defender_power = combat.total_power(defender_troops, 50, attacker_troops)
    rate = combat.win_rate(attacker_power, defender_power)
    attacker_win = rate >= 0.5

    attacker_losses, defender_losses = combat.compute_losses(attacker_troops, defender_troops, attacker_win, rate)
    attacker.infantry = max(0, attacker.infantry - attacker_losses["infantry"])
    attacker.archer = max(0, attacker.archer - attacker_losses["archer"])
    attacker.cavalry = max(0, attacker.cavalry - attacker_losses["cavalry"])

    rewards = {"gold": 0, "food": 0, "exp": 0}
    if attacker_win:
        rewards["gold"] = random.randint(*dungeon.reward_gold)
        rewards["food"] = random.randint(*dungeon.reward_food)
        rewards["exp"] = dungeon.reward_exp
        first_clear = (
            db.query(DungeonClear)
            .filter(DungeonClear.agent_id == attacker.id, DungeonClear.dungeon_id == dungeon.id)
            .first()
        )
        if not first_clear and dungeon.first_clear_gold:
            rewards["gold"] += dungeon.first_clear_gold
            db.add(DungeonClear(agent_id=attacker.id, dungeon_id=dungeon.id))
        attacker.gold += rewards["gold"]
        attacker.food += rewards["food"]

    battle_id = f"pve_{uuid4().hex}"
    db.add(
        BattleLog(
            attacker_city=attacker.current_city,
            defender_city=f"PVE:{dungeon.id}",
            attacker_agent_id=attacker.id,
            defender_agent_id=None,
            attack_power=round(attacker_power, 4),
            defense_power=round(defender_power, 4),
            outcome="attacker_win" if attacker_win else "defender_win",
            loot_gold=rewards["gold"],
            loot_food=rewards["food"],
            request_id=battle_id,
        )
    )
    db.add(
        ActionLog(
            agent_id=attacker.id,
            city_name=settings.city_name,
            action_type="pve_challenge",
            payload_json=json.dumps(payload.model_dump()),
            energy_cost=0,
            result_json=json.dumps(
                {
                    "battle_id": battle_id,
                    "win": attacker_win,
                    "attacker_power": attacker_power,
                    "defender_power": defender_power,
                    "rewards": rewards,
                    "losses": attacker_losses,
                    "enemy_losses": defender_losses,
                }
            ),
        )
    )
    db.add(attacker)
    write_chronicle(
        db,
        event_type="battle",
        title=f"{attacker.name} challenged {dungeon.name}",
        content=f"Outcome: {'win' if attacker_win else 'lose'}. Rewards gold={rewards['gold']}, food={rewards['food']}.",
    )
    db.commit()

    return {
        "success": True,
        "data": {
            "win": attacker_win,
            "battle_id": battle_id,
            "attacker_power": round(attacker_power, 4),
            "defender_power": round(defender_power, 4),
            "rewards": rewards,
            "losses": attacker_losses,
            "enemy_losses": defender_losses,
        },
    }


@router.get("/pvp/opponents")
def pvp_opponents(
    agent_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attacker = _get_owned_agent(db, current_user.id, agent_id)
    attacker_power = _agent_power(attacker)
    rank_map = _rank_map(db)
    attacker_rank = rank_map.get(attacker.id, 0)
    day = _utc_day()
    daily_counter = (
        db.query(PvpChallengeDaily)
        .filter(PvpChallengeDaily.agent_id == attacker.id, PvpChallengeDaily.day == day)
        .order_by(PvpChallengeDaily.id.desc())
        .first()
    )
    daily_used = daily_counter.count if daily_counter else 0

    candidates = db.query(Agent).filter(Agent.owner_user_id != current_user.id).order_by(Agent.id.asc()).limit(200).all()
    preferred = []
    fallback = []
    now = datetime.now(timezone.utc)
    attacker_troops = _agent_troops(attacker)
    for agent in candidates:
        if _is_agent_protected(db, agent.id, now):
            continue
        power = _agent_power(agent)
        rank = rank_map.get(agent.id, 0)
        if rank <= 0 or abs(rank - attacker_rank) > 10:
            continue
        defender_troops = _agent_troops(agent)
        attacker_power_for_match = combat.total_power(attacker_troops, attacker.martial, defender_troops)
        defender_power_for_match = combat.total_power(defender_troops, agent.martial, attacker_troops)
        estimated_win_rate = combat.win_rate(attacker_power_for_match, defender_power_for_match)
        entry = {
            "agent_id": agent.id,
            "name": agent.name,
            "role": agent.role,
            "power": round(power, 2),
            "rank": rank,
            "city": agent.current_city,
            "estimated_win_rate": round(estimated_win_rate, 4),
        }
        if MATCHMAKING_TARGET_MIN_WIN_RATE <= estimated_win_rate <= MATCHMAKING_TARGET_MAX_WIN_RATE:
            preferred.append(entry)
        else:
            fallback.append(entry)

    preferred.sort(
        key=lambda x: (
            abs(0.5 - x["estimated_win_rate"]),
            abs(x["power"] - round(attacker_power, 2)),
            x["agent_id"],
        )
    )
    fallback.sort(
        key=lambda x: (
            abs(0.5 - x["estimated_win_rate"]),
            abs(x["power"] - round(attacker_power, 2)),
            x["agent_id"],
        )
    )
    opponents = (preferred + fallback)[:10]

    return {
        "success": True,
        "data": {
            "items": opponents,
            "attacker_rank": attacker_rank,
            "attacker_power": round(attacker_power, 2),
            "daily_limit": PVP_DAILY_LIMIT,
            "daily_used": daily_used,
            "daily_remaining": max(0, PVP_DAILY_LIMIT - daily_used),
            "matchmaking_target_win_rate": {
                "min": MATCHMAKING_TARGET_MIN_WIN_RATE,
                "max": MATCHMAKING_TARGET_MAX_WIN_RATE,
            },
        },
    }


@router.post("/pvp/challenge")
def pvp_challenge(
    payload: PvpChallengeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attacker = _get_owned_agent(db, current_user.id, payload.attacker_id)
    defender = db.get(Agent, payload.defender_id)
    if not defender:
        raise AppError("AGENT_NOT_FOUND", "Target agent does not exist.", status_code=404)
    if defender.owner_user_id == current_user.id:
        raise AppError("INVALID_REQUEST", "Cannot challenge your own agent.", status_code=422)
    now = datetime.now(timezone.utc)
    if _is_agent_protected(db, defender.id, now):
        raise AppError("PVP_TARGET_PROTECTED", "Target is currently under protection.", status_code=422)
    rank_map = _rank_map(db)
    attacker_rank = rank_map.get(attacker.id, 0)
    defender_rank = rank_map.get(defender.id, 0)
    if attacker_rank <= 0 or defender_rank <= 0 or abs(attacker_rank - defender_rank) > 10:
        raise AppError("INVALID_OPPONENT", "Opponent is not eligible for this battle.", status_code=422)
    day = _utc_day()
    daily_counter = _get_or_create_daily_counter(db, attacker.id, day)
    if daily_counter.count >= PVP_DAILY_LIMIT:
        raise AppError("PVP_DAILY_LIMIT_REACHED", "Daily PVP challenge limit reached.", status_code=422)

    attacker_troops = _troops_from_request(payload.troops)
    _assert_troops_available(attacker, attacker_troops)

    defender_troops = combat.troop_summary(
        {"infantry": defender.infantry, "archer": defender.archer, "cavalry": defender.cavalry}
    )
    if not combat.is_valid_troops(defender_troops):
        raise AppError("INVALID_OPPONENT", "Opponent has no troops.", status_code=422)

    attacker_power = combat.total_power(attacker_troops, attacker.martial, defender_troops)
    defender_power = combat.total_power(defender_troops, defender.martial, attacker_troops)
    rate = combat.win_rate(attacker_power, defender_power)
    attacker_win = rate >= 0.5

    attacker_losses, defender_losses = combat.compute_losses(attacker_troops, defender_troops, attacker_win, rate)
    attacker.infantry = max(0, attacker.infantry - attacker_losses["infantry"])
    attacker.archer = max(0, attacker.archer - attacker_losses["archer"])
    attacker.cavalry = max(0, attacker.cavalry - attacker_losses["cavalry"])
    defender.infantry = max(0, defender.infantry - defender_losses["infantry"])
    defender.archer = max(0, defender.archer - defender_losses["archer"])
    defender.cavalry = max(0, defender.cavalry - defender_losses["cavalry"])

    spoils = {"gold": 0, "food": 0}
    if attacker_win:
        gold_steal = int(defender.gold * 0.1)
        min_gold_keep = 100
        if defender.gold - gold_steal < min_gold_keep:
            gold_steal = max(0, defender.gold - min_gold_keep)

        food_steal = int(defender.food * 0.1)
        min_food_keep = int(defender.food * 0.5)
        if defender.food - food_steal < min_food_keep:
            food_steal = max(0, defender.food - min_food_keep)

        defender.gold -= gold_steal
        defender.food -= food_steal
        attacker.gold += gold_steal
        attacker.food += food_steal
        spoils["gold"] = gold_steal
        spoils["food"] = food_steal
        _apply_protection(db, defender.id, now)
    else:
        _apply_protection(db, attacker.id, now)
    daily_counter.count += 1
    db.add(daily_counter)

    battle_id = f"pvp_{uuid4().hex}"
    db.add(
        BattleLog(
            attacker_city=attacker.current_city,
            defender_city=defender.current_city,
            attacker_agent_id=attacker.id,
            defender_agent_id=defender.id,
            attack_power=round(attacker_power, 4),
            defense_power=round(defender_power, 4),
            outcome="attacker_win" if attacker_win else "defender_win",
            loot_gold=spoils["gold"],
            loot_food=spoils["food"],
            request_id=battle_id,
        )
    )
    db.add(
        ActionLog(
            agent_id=attacker.id,
            city_name=settings.city_name,
            action_type="pvp_challenge",
            payload_json=json.dumps(payload.model_dump()),
            energy_cost=0,
            result_json=json.dumps(
                {
                    "battle_id": battle_id,
                    "attacker_win": attacker_win,
                    "attacker_power": attacker_power,
                    "defender_power": defender_power,
                    "spoils": spoils,
                    "losses": {"attacker": attacker_losses, "defender": defender_losses},
                }
            ),
        )
    )
    db.add(attacker)
    db.add(defender)
    write_chronicle(
        db,
        event_type="battle",
        title=f"{attacker.name} attacked {defender.name}",
        content=f"Outcome: {'attacker_win' if attacker_win else 'defender_win'}. Spoils gold={spoils['gold']}, food={spoils['food']}.",
    )
    db.commit()

    return {
        "success": True,
        "data": {
            "battle_id": battle_id,
            "attacker_win": attacker_win,
            "attacker_power": round(attacker_power, 4),
            "defender_power": round(defender_power, 4),
            "spoils": spoils,
            "losses": {"attacker": attacker_losses, "defender": defender_losses},
            "daily_used": daily_counter.count,
            "daily_remaining": max(0, PVP_DAILY_LIMIT - daily_counter.count),
        },
    }


@router.get("/battle/reports")
def battle_reports(
    agent_id: int | None = Query(default=None),
    mode: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    query = db.query(BattleLog).order_by(BattleLog.id.desc())
    if mode in {"pve", "pvp"}:
        query = query.filter(BattleLog.request_id.like(f"{mode}_%"))
    if agent_id is not None:
        query = query.filter(or_(BattleLog.attacker_agent_id == agent_id, BattleLog.defender_agent_id == agent_id))
    logs = query.limit(limit).all()
    return {
        "success": True,
        "data": {
            "items": [
                {
                    "battle_id": b.request_id,
                    "mode": "pve" if b.request_id.startswith("pve_") else "pvp",
                    "attacker_agent_id": b.attacker_agent_id,
                    "defender_agent_id": b.defender_agent_id,
                    "attacker_city": b.attacker_city,
                    "defender_city": b.defender_city,
                    "attacker_power": round(b.attack_power, 4),
                    "defender_power": round(b.defense_power, 4),
                    "outcome": b.outcome,
                    "spoils": {"gold": b.loot_gold, "food": b.loot_food},
                    "created_at": b.created_at.isoformat(),
                    "replay_url": f"/api/battle/replay/{b.request_id}",
                }
                for b in logs
            ]
        },
    }


@router.get("/battle/replay/{battle_id}")
def battle_replay(
    battle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    battle = db.query(BattleLog).filter(BattleLog.request_id == battle_id).first()
    if not battle:
        raise AppError("INVALID_REQUEST", "Battle does not exist.", status_code=404)

    _, result_payload = _extract_action_result_by_battle_id(db, battle_id)
    mode = "pve" if battle_id.startswith("pve_") else "pvp"

    attacker_losses = {"infantry": 0, "archer": 0, "cavalry": 0}
    defender_losses = {"infantry": 0, "archer": 0, "cavalry": 0}
    attacker_troops = {"infantry": 0, "archer": 0, "cavalry": 0}
    defender_troops = {"infantry": 0, "archer": 0, "cavalry": 0}
    if mode == "pve":
        attacker_losses = result_payload.get("losses", attacker_losses)
        defender_losses = result_payload.get("enemy_losses", defender_losses)
    else:
        losses = result_payload.get("losses", {})
        attacker_losses = losses.get("attacker", attacker_losses)
        defender_losses = losses.get("defender", defender_losses)

    attacker = db.get(Agent, battle.attacker_agent_id) if battle.attacker_agent_id else None
    defender = db.get(Agent, battle.defender_agent_id) if battle.defender_agent_id else None
    if attacker:
        attacker_troops = _agent_troops(attacker)
    if defender:
        defender_troops = _agent_troops(defender)

    attacker_round_losses = _split_losses(attacker_losses, rounds=3)
    defender_round_losses = _split_losses(defender_losses, rounds=3)
    rounds = []
    for idx in range(3):
        rounds.append(
            {
                "round": idx + 1,
                "attacker_action": _dominant_label(attacker_troops),
                "defender_action": _dominant_label(defender_troops),
                "casualties": {
                    "attacker": attacker_round_losses[idx],
                    "defender": defender_round_losses[idx],
                },
            }
        )

    return {
        "success": True,
        "data": {
            "battle_id": battle_id,
            "mode": mode,
            "created_at": battle.created_at.isoformat(),
            "summary": {
                "attacker_agent_id": battle.attacker_agent_id,
                "defender_agent_id": battle.defender_agent_id,
                "attacker_city": battle.attacker_city,
                "defender_city": battle.defender_city,
                "attacker_power": round(battle.attack_power, 4),
                "defender_power": round(battle.defense_power, 4),
                "outcome": battle.outcome,
                "spoils": {"gold": battle.loot_gold, "food": battle.loot_food},
            },
            "rounds": rounds,
        },
    }
