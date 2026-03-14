from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import Agent, MigrationLog, User
from ..api.deps import get_current_user
from ..rules import compute_power
from ..schemas import PromoteAgentRequest, RegisterAgentRequest
from ..services.chronicle import write_chronicle
from ..services.positions import (
    STARTING_ROLE_ZH,
    can_promote_to,
    get_position,
    has_slot_limit,
    promotion_cost,
    role_max_slots,
    role_display,
)
from ..services.roles import is_allowed_role
from ..services.abilities import roll_abilities

router = APIRouter(prefix="/agent", tags=["agent"])


def _assert_role_slot_available(db: Session, role: str, city_name: str, exclude_agent_id: int | None = None) -> None:
    pos = get_position(role)
    limit = role_max_slots(pos.name_zh)
    if not has_slot_limit(pos.name_zh) or limit is None:
        return
    q = db.query(func.count(Agent.id)).filter(Agent.current_city == city_name, Agent.role == pos.name_zh)
    if exclude_agent_id is not None:
        q = q.filter(Agent.id != exclude_agent_id)
    occupied = q.scalar() or 0
    if occupied >= limit:
        raise AppError(
            "ROLE_SLOTS_FULL",
            f"Role {pos.name_zh} has reached slot limit ({limit}).",
            status_code=422,
        )


@router.post("/register")
def register_agent(
    payload: RegisterAgentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # New agents always start from commoner role regardless of submitted role.
    starting_role = STARTING_ROLE_ZH
    abilities = roll_abilities()

    agent = Agent(
        owner_user_id=current_user.id,
        name=payload.name,
        role=starting_role,
        home_city=settings.city_name,
        current_city=settings.city_name,
        martial=abilities["martial"],
        intelligence=abilities["intelligence"],
        charisma=abilities["charisma"],
        politics=abilities["politics"],
    )
    db.add(agent)
    write_chronicle(
        db,
        event_type="agent",
        title=f"{agent.name} registered",
        content=f"{agent.name} joined city {settings.city_name} as {agent.role}.",
    )
    db.commit()
    db.refresh(agent)

    return {
        "success": True,
        "data": {
            "agent_id": agent.id,
            "name": agent.name,
            "role": agent.role,
            "home_city": agent.home_city,
            "abilities": {
                "martial": agent.martial,
                "intelligence": agent.intelligence,
                "charisma": agent.charisma,
                "politics": agent.politics,
            },
        },
    }


@router.post("/promote")
def promote_agent(
    payload: PromoteAgentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = db.get(Agent, payload.agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)
    if agent.owner_user_id != current_user.id:
        raise AppError("FORBIDDEN", "You do not own this agent.", status_code=403)
    if not can_promote_to(payload.target_role):
        raise AppError("INVALID_ROLE", "Target role is not promotable.", status_code=422)
    if not is_allowed_role(db, payload.target_role):
        raise AppError("INVALID_ROLE", "The role is not allowed.", status_code=422)

    new_pos = get_position(payload.target_role)
    old_pos = get_position(agent.role)
    if new_pos.tier <= old_pos.tier:
        raise AppError("INVALID_REQUEST", "Target role tier must be higher than current role.", status_code=422)
    _assert_role_slot_available(db, new_pos.name_zh, agent.current_city, exclude_agent_id=agent.id)

    cost = promotion_cost(payload.target_role)
    if agent.gold < cost:
        raise AppError("INSUFFICIENT_GOLD", "Not enough gold to promote.", status_code=422)

    agent.gold -= cost
    agent.role = new_pos.name_zh
    db.add(agent)
    write_chronicle(
        db,
        event_type="social",
        title=f"{agent.name} promoted",
        content=f"{agent.name} promoted from {role_display(old_pos.name_zh)} to {new_pos.name_zh} for {cost} gold.",
    )
    db.commit()
    db.refresh(agent)
    return {
        "success": True,
        "data": {
            "agent_id": agent.id,
            "role": agent.role,
            "gold": agent.gold,
            "promotion_cost": cost,
            "slot_limit": role_max_slots(agent.role),
        },
    }


@router.get("/status")
def agent_status(
    agent_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)

    if agent.owner_user_id != current_user.id:
        raise AppError("FORBIDDEN", "You do not own this agent.", status_code=403)

    return {
        "success": True,
        "data": {
            "id": agent.id,
            "name": agent.name,
            "role": agent.role,
            "home_city": agent.home_city,
            "current_city": agent.current_city,
            "energy": agent.energy,
            "gold": agent.gold,
            "food": agent.food,
            "troops": {
                "infantry": agent.infantry,
                "archer": agent.archer,
                "cavalry": agent.cavalry,
            },
            "reputation": agent.reputation,
            "abilities": {
                "martial": agent.martial,
                "intelligence": agent.intelligence,
                "charisma": agent.charisma,
                "politics": agent.politics,
            },
            "power": compute_power(agent.infantry, agent.archer, agent.cavalry),
            "lord_agent_id": agent.lord_agent_id,
            "faction_id": agent.faction_id,
        },
    }


@router.post("/migrate")
def migrate_agent(
    agent_id: int = Query(...),
    target_city: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)
    if agent.owner_user_id != current_user.id:
        raise AppError("FORBIDDEN", "You do not own this agent.", status_code=403)

    from_city = agent.current_city
    agent.home_city = target_city
    agent.current_city = target_city
    db.add(agent)
    db.add(
        MigrationLog(
            agent_id=agent.id,
            agent_name=agent.name,
            from_city=from_city,
            to_city=target_city,
            status="completed",
            details="Self migration via /agent/migrate",
        )
    )
    write_chronicle(
        db,
        event_type="migration",
        title=f"{agent.name} migrated",
        content=f"{agent.name} moved from {from_city} to {target_city}.",
    )
    db.commit()

    return {
        "success": True,
        "data": {"agent_id": agent.id, "home_city": agent.home_city, "current_city": agent.current_city},
    }


@router.get("/mine")
def list_my_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agents = db.query(Agent).filter(Agent.owner_user_id == current_user.id).order_by(Agent.id.asc()).all()
    return {
        "success": True,
        "data": {
            "items": [
                {
                    "id": a.id,
                    "name": a.name,
                    "role": a.role,
                    "home_city": a.home_city,
                    "current_city": a.current_city,
                    "energy": a.energy,
                    "gold": a.gold,
                    "food": a.food,
                    "lord_agent_id": a.lord_agent_id,
                    "faction_id": a.faction_id,
                }
                for a in agents
            ]
        },
    }
