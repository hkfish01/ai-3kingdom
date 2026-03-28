import json
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..api.deps import get_current_user
from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import ActionLog, Agent, BattleLog, City, User
from ..rules import CITY_TAX_RATE, TROOP_TYPES, WORK_TASKS, compute_power
from ..schemas import TrainActionRequest, WorkActionRequest
from ..services.chronicle import write_chronicle
from ..services.positions import get_position

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/action", tags=["action"])
LORD_TO_VASSAL_BONUS_RATE = 0.01
VASSAL_TO_LORD_BONUS_RATE = 0.001


def _get_owned_agent(db: Session, user_id: int, agent_id: int) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)
    if agent.owner_user_id != user_id:
        raise AppError("FORBIDDEN", "You do not own this agent.", status_code=403)
    return agent


def _ensure_local_city(db: Session) -> City:
    city = db.query(City).filter(City.name == settings.city_name).first()
    if city:
        return city

    city = City(
        name=settings.city_name,
        base_url=settings.city_base_url,
        city_wall=settings.city_wall,
        city_tax_rate=settings.city_tax_rate,
        protocol_version=settings.protocol_version,
        rule_version=settings.rule_version,
        open_for_migration=settings.open_for_migration,
    )
    db.add(city)
    db.commit()
    db.refresh(city)
    return city


def _get_utc_date() -> str:
    """Get current UTC date string (YYYY-MM-DD)"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_week_start() -> str:
    """Get current week's Monday UTC date string"""
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    return monday.strftime("%Y-%m-%d")


def _update_quest_progress(db: Session, agent_id: int, quest_type: str, progress_delta: int):
    """Update quest progress for an agent (daily and weekly)"""
    try:
        # Import here to avoid issues if tables don't exist
        from ..models import AgentDailyQuest, AgentWeeklyQuest
        
        utc_date = _get_utc_date()
        week_start = _get_week_start()
        
        # Update daily quest progress
        daily_quest = db.query(AgentDailyQuest).filter(
            AgentDailyQuest.agent_id == agent_id,
            AgentDailyQuest.quest_type == quest_type,
            AgentDailyQuest.quest_date == utc_date
        ).first()
        
        if daily_quest and not daily_quest.is_claimed:
            daily_quest.current_progress += progress_delta
            if daily_quest.current_progress >= daily_quest.target:
                daily_quest.is_completed = True
            db.add(daily_quest)
        
        # Update weekly quest progress (for weekly versions of quest types)
        weekly_quest_type = f"{quest_type}_weekly" if quest_type == "earn_gold" else quest_type
        weekly_quest = db.query(AgentWeeklyQuest).filter(
            AgentWeeklyQuest.agent_id == agent_id,
            AgentWeeklyQuest.quest_type == weekly_quest_type,
            AgentWeeklyQuest.week_start == week_start
        ).first()
        
        if weekly_quest and not weekly_quest.is_claimed:
            weekly_quest.current_progress += progress_delta
            if weekly_quest.current_progress >= weekly_quest.target:
                weekly_quest.is_completed = True
            db.add(weekly_quest)
            
    except Exception as e:
        # Log but don't fail the action if quest update fails
        logger.warning(f"Failed to update quest progress: {e}")
        pass


@router.post("/work")
def action_work(
    payload: WorkActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.task not in WORK_TASKS:
        raise AppError("INVALID_TASK", "Unsupported work task.", status_code=422)

    city = _ensure_local_city(db)
    agent = _get_owned_agent(db, current_user.id, payload.agent_id)
    rule = WORK_TASKS[payload.task]

    if agent.energy < rule["energy"]:
        raise AppError("INSUFFICIENT_ENERGY", "Not enough energy for this action.", status_code=422)

    pos_bonus = get_position(agent.role).bonus
    boosted_gold = int(rule["gold"] * (1 + (pos_bonus.get("work_gold_pct", 0) / 100)))
    boosted_food = int(rule["food"] * (1 + (pos_bonus.get("work_food_pct", 0) / 100)))

    city_tax_gold = int(boosted_gold * CITY_TAX_RATE)
    remaining_gold = boosted_gold - city_tax_gold
    remaining_food = boosted_food
    lord_bonus_to_vassal_gold = 0
    lord_bonus_to_vassal_food = 0
    vassal_bonus_to_lord_gold = 0
    vassal_bonus_to_lord_food = 0
    lord = None

    if agent.lord_agent_id:
        lord = db.get(Agent, agent.lord_agent_id)
        if lord:
            lord_bonus_to_vassal_gold = max(1, int(remaining_gold * LORD_TO_VASSAL_BONUS_RATE)) if remaining_gold > 0 else 0
            lord_bonus_to_vassal_food = max(1, int(remaining_food * LORD_TO_VASSAL_BONUS_RATE)) if remaining_food > 0 else 0
            vassal_bonus_to_lord_gold = max(1, int(remaining_gold * VASSAL_TO_LORD_BONUS_RATE)) if remaining_gold > 0 else 0
            vassal_bonus_to_lord_food = max(1, int(remaining_food * VASSAL_TO_LORD_BONUS_RATE)) if remaining_food > 0 else 0

    agent.energy -= rule["energy"]
    agent.gold += remaining_gold + lord_bonus_to_vassal_gold
    agent.food += remaining_food + lord_bonus_to_vassal_food

    city.treasury_gold += city_tax_gold

    if lord:
        lord.gold += vassal_bonus_to_lord_gold
        lord.food += vassal_bonus_to_lord_food

    result = {
        "task": payload.task,
        "role_bonus": pos_bonus,
        "base_gold": rule["gold"],
        "base_food": rule["food"],
        "boosted_gold": boosted_gold,
        "boosted_food": boosted_food,
        "energy_cost": rule["energy"],
        "gold_gained": remaining_gold + lord_bonus_to_vassal_gold,
        "food_gained": remaining_food + lord_bonus_to_vassal_food,
        "city_tax_gold": city_tax_gold,
        "lord_bonus_to_vassal_gold": lord_bonus_to_vassal_gold,
        "lord_bonus_to_vassal_food": lord_bonus_to_vassal_food,
        "vassal_bonus_to_lord_gold": vassal_bonus_to_lord_gold,
        "vassal_bonus_to_lord_food": vassal_bonus_to_lord_food,
    }

    db.add(
        ActionLog(
            agent_id=agent.id,
            city_name=settings.city_name,
            action_type="work",
            payload_json=json.dumps(payload.model_dump()),
            energy_cost=rule["energy"],
            result_json=json.dumps(result),
        )
    )
    db.add(agent)
    db.add(city)
    if lord:
        db.add(lord)

    write_chronicle(
        db,
        event_type="economy",
        title=f"{agent.name} completed {payload.task}",
        content=(
            f"{agent.name} gained {remaining_gold} gold and {remaining_food} food. "
            f"City tax gold: {city_tax_gold}."
        ),
    )
    db.commit()

    # 任務 1: 更新任務進度 (earn_gold)
    _update_quest_progress(db, agent.id, "earn_gold", 1)

    return {
        "success": True,
        "data": {
            **result,
            "agent": {
                "energy": agent.energy,
                "gold": agent.gold,
                "food": agent.food,
            },
        },
    }


@router.post("/train")
def action_train(
    payload: TrainActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.troop_type not in TROOP_TYPES:
        raise AppError("INVALID_TROOP_TYPE", "Unsupported troop type.", status_code=422)

    agent = _get_owned_agent(db, current_user.id, payload.agent_id)
    rule = TROOP_TYPES[payload.troop_type]

    cost_gold = rule["gold"] * payload.quantity
    cost_food = rule["food"] * payload.quantity
    energy_cost = 15

    if agent.energy < energy_cost:
        raise AppError("INSUFFICIENT_ENERGY", "Not enough energy for this action.", status_code=422)
    if agent.gold < cost_gold or agent.food < cost_food:
        raise AppError("INSUFFICIENT_RESOURCES", "Not enough gold or food.", status_code=422)

    agent.energy -= energy_cost
    agent.gold -= cost_gold
    agent.food -= cost_food

    if payload.troop_type == "infantry":
        agent.infantry += payload.quantity
    elif payload.troop_type == "archer":
        agent.archer += payload.quantity
    elif payload.troop_type == "cavalry":
        agent.cavalry += payload.quantity

    power = compute_power(agent.infantry, agent.archer, agent.cavalry)

    result = {
        "troop_type": payload.troop_type,
        "quantity": payload.quantity,
        "energy_cost": energy_cost,
        "gold_spent": cost_gold,
        "food_spent": cost_food,
        "power": power,
    }

    db.add(
        ActionLog(
            agent_id=agent.id,
            city_name=settings.city_name,
            action_type="train",
            payload_json=json.dumps(payload.model_dump()),
            energy_cost=energy_cost,
            result_json=json.dumps(result),
        )
    )
    db.add(agent)
    write_chronicle(
        db,
        event_type="military",
        title=f"{agent.name} trained {payload.quantity} {payload.troop_type}",
        content=f"Total power is now {power:.2f}.",
    )
    db.commit()

    # 任務 1: 更新任務進度 (train_troops)
    _update_quest_progress(db, agent.id, "train_troops", payload.quantity)

    return {
        "success": True,
        "data": {
            **result,
            "agent": {
                "energy": agent.energy,
                "gold": agent.gold,
                "food": agent.food,
                "troops": {
                    "infantry": agent.infantry,
                    "archer": agent.archer,
                    "cavalry": agent.cavalry,
                },
            },
        },
    }


@router.post("/attack")
def action_attack(
    agent_id: int,
    target_agent_id: int,
    target_type: str = None,  # 任務 2: PVE 攻擊類型 (bandits, rogue)
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attacker = _get_owned_agent(db, current_user.id, agent_id)
    
    # 任務 2: PVE 副本攻擊邏輯
    if target_type in ["bandits", "rogue"]:
        # PVE 模式：攻擊盜賊或流寇
        if target_type == "bandits":
            enemy_power = 3.0
            reward_gold = 50
            enemy_name = "盜賊"
        elif target_type == "rogue":
            enemy_power = 5.0
            reward_gold = 100
            enemy_name = "流寇"
        
        if attacker.energy < 25:
            raise AppError("INSUFFICIENT_ENERGY", "Not enough energy for this action.", status_code=422)
        
        attacker_power = compute_power(attacker.infantry, attacker.archer, attacker.cavalry)
        attacker.energy -= 25
        
        outcome = "defeat"
        loot_gold = 0
        loot_food = 0
        
        if attacker_power >= enemy_power:
            outcome = "victory"
            loot_gold = reward_gold
            loot_food = 0  # PVE 戰鬥只獲得金幣
            attacker.gold += loot_gold
            attacker.food += loot_food
        
        db.add(
            BattleLog(
                attacker_city=attacker.current_city,
                defender_city=settings.city_name,
                attacker_agent_id=attacker.id,
                defender_agent_id=None,  # PVE 沒有 defender agent
                attack_power=attacker_power,
                defense_power=enemy_power,
                outcome=outcome,
                loot_gold=loot_gold,
                loot_food=loot_food,
            )
        )
        db.add(
            ActionLog(
                agent_id=attacker.id,
                city_name=settings.city_name,
                action_type="attack",
                payload_json=json.dumps({"target_type": target_type}),
                energy_cost=25,
                result_json=json.dumps(
                    {
                        "target_type": target_type,
                        "enemy_name": enemy_name,
                        "outcome": outcome,
                        "attacker_power": attacker_power,
                        "enemy_power": enemy_power,
                        "loot_gold": loot_gold,
                        "loot_food": loot_food,
                    }
                ),
            )
        )
        db.add(attacker)
        
        if outcome == "victory":
            write_chronicle(
                db,
                event_type="battle",
                title=f"{attacker.name} 擊敗了{enemy_name}",
                content=f"Outcome: {outcome}. Loot gold={loot_gold}, food={loot_food}.",
            )
            # 任務 1: 更新任務進度 (complete_battle for PVE)
            _update_quest_progress(db, attacker.id, "complete_battle", 1)
        
        db.commit()
        
        return {
            "success": True,
            "data": {
                "target_type": target_type,
                "enemy_name": enemy_name,
                "outcome": outcome,
                "attacker_power": attacker_power,
                "enemy_power": enemy_power,
                "loot_gold": loot_gold,
                "loot_food": loot_food,
            },
        }
    
    # PVP 模式：原有用戶對用戶攻擊
    defender = db.get(Agent, target_agent_id)
    if not defender:
        raise AppError("AGENT_NOT_FOUND", "Target agent does not exist.", status_code=404)

    if attacker.energy < 25:
        raise AppError("INSUFFICIENT_ENERGY", "Not enough energy for this action.", status_code=422)

    attacker_power = compute_power(attacker.infantry, attacker.archer, attacker.cavalry)
    defender_power = compute_power(defender.infantry, defender.archer, defender.cavalry)
    attacker.energy -= 25

    outcome = "defeat"
    loot_gold = 0
    loot_food = 0

    if attacker_power > defender_power:
        outcome = "victory"
        loot_gold = int(defender.gold * 0.3)
        loot_food = int(defender.food * 0.3)
        
        # 任務 3: 確保戰利品轉移邏輯正確並 commit
        defender.gold -= loot_gold
        defender.food -= loot_food
        attacker.gold += loot_gold
        attacker.food += loot_food

    db.add(
        BattleLog(
            attacker_city=attacker.current_city,
            defender_city=defender.current_city,
            attacker_agent_id=attacker.id,
            defender_agent_id=defender.id,
            attack_power=attacker_power,
            defense_power=defender_power,
            outcome=outcome,
            loot_gold=loot_gold,
            loot_food=loot_food,
        )
    )
    db.add(
        ActionLog(
            agent_id=attacker.id,
            city_name=settings.city_name,
            action_type="attack",
            payload_json=json.dumps({"target_agent_id": target_agent_id}),
            energy_cost=25,
            result_json=json.dumps(
                {
                    "outcome": outcome,
                    "attacker_power": attacker_power,
                    "defender_power": defender_power,
                    "loot_gold": loot_gold,
                    "loot_food": loot_food,
                }
            ),
        )
    )
    db.add(attacker)
    db.add(defender)
    
    if outcome == "victory":
        write_chronicle(
            db,
            event_type="battle",
            title=f"{attacker.name} attacked {defender.name}",
            content=f"Outcome: {outcome}. Loot gold={loot_gold}, food={loot_food}.",
        )
        # 任務 1: 更新任務進度 (complete_battle for PVP)
        _update_quest_progress(db, attacker.id, "complete_battle", 1)
    
    db.commit()

    return {
        "success": True,
        "data": {
            "outcome": outcome,
            "attacker_power": attacker_power,
            "defender_power": defender_power,
            "loot_gold": loot_gold,
            "loot_food": loot_food,
        },
    }