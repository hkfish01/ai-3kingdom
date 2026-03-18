import json
import random
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..api.deps import get_current_user
from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import ActionLog, Agent, BattleLog, User
from ..schemas import PveChallengeRequest, PvpChallengeRequest
from ..services import combat
from ..services.chronicle import write_chronicle

router = APIRouter(tags=["combat"])


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
    attacker_troops = combat.troop_summary(
        {"infantry": attacker.infantry, "archer": attacker.archer, "cavalry": attacker.cavalry}
    )
    attacker_power = combat.raw_power(attacker_troops, attacker.martial)
    min_power = attacker_power * 0.6
    max_power = attacker_power * 1.4

    candidates = (
        db.query(Agent)
        .filter(Agent.owner_user_id != current_user.id)
        .order_by(Agent.id.asc())
        .limit(200)
        .all()
    )
    opponents = []
    for agent in candidates:
        troop_snapshot = combat.troop_summary(
            {"infantry": agent.infantry, "archer": agent.archer, "cavalry": agent.cavalry}
        )
        power = combat.raw_power(troop_snapshot, agent.martial)
        if power < min_power or power > max_power:
            continue
        opponents.append(
            {
                "agent_id": agent.id,
                "name": agent.name,
                "role": agent.role,
                "power": round(power, 2),
                "city": agent.current_city,
            }
        )
        if len(opponents) >= 10:
            break

    return {"success": True, "data": {"items": opponents}}


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
        },
    }
