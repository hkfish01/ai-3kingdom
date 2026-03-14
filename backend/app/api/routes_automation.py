from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..api.deps import get_current_user
from ..auth import create_access_token, hash_password
from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import Agent, AgentClaimTicket, ApiKey, Faction, User, utc_now
from ..schemas import BootstrapAIAgentRequest
from ..services.abilities import roll_abilities
from ..services.chronicle import write_chronicle
from ..services.secrets import hash_secret, make_api_key, make_claim_code, make_password
from ..services.positions import STARTING_ROLE_ZH

router = APIRouter(prefix="/automation", tags=["automation"])


@router.post("/agent/bootstrap")
def bootstrap_ai_agent(payload: BootstrapAIAgentRequest, db: Session = Depends(get_db)):
    username = payload.username
    if not username:
        base = f"ai_{payload.agent_name.lower()[:20]}"
        suffix = make_password(8).lower()
        username = f"{base}_{suffix}"

    if db.query(User).filter(User.username == username).first():
        raise AppError("USERNAME_EXISTS", "Username already exists.", status_code=409)

    password = payload.password or make_password(24)
    user = User(
        username=username,
        email=f"{username}@agents.local",
        password_hash=hash_password(password),
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    abilities = roll_abilities()
    agent = Agent(
        owner_user_id=user.id,
        name=payload.agent_name,
        role=STARTING_ROLE_ZH,
        home_city=settings.city_name,
        current_city=settings.city_name,
        martial=abilities["martial"],
        intelligence=abilities["intelligence"],
        charisma=abilities["charisma"],
        politics=abilities["politics"],
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    faction_data = None
    if payload.faction_name:
        existing = db.query(Faction).filter(Faction.name == payload.faction_name).first()
        if existing:
            raise AppError("FACTION_EXISTS", "Faction name already exists.", status_code=409)
        faction = Faction(name=payload.faction_name, leader_agent_id=agent.id, home_city=agent.home_city)
        db.add(faction)
        db.commit()
        db.refresh(faction)
        agent.faction_id = faction.id
        db.add(agent)
        db.commit()
        faction_data = {"faction_id": faction.id, "name": faction.name}

    plain_key = make_api_key()
    key = ApiKey(
        owner_user_id=user.id,
        agent_id=agent.id,
        name=payload.key_name,
        key_prefix=plain_key[:10],
        key_hash=hash_secret(plain_key),
        last4=plain_key[-4:],
    )
    db.add(key)

    claim_code = make_claim_code()
    ticket = AgentClaimTicket(
        agent_id=agent.id,
        code_hash=hash_secret(claim_code),
        expires_at=utc_now() + timedelta(days=30),
    )
    db.add(ticket)

    write_chronicle(
        db,
        event_type="agent",
        title=f"{agent.name} auto-bootstrapped",
        content=f"{agent.name} was initialized by automation bootstrap.",
    )
    db.commit()

    token = create_access_token(user.id)
    return {
        "success": True,
        "data": {
            "ai_account": {"user_id": user.id, "username": user.username, "password": password},
            "token": token,
            "agent": {
                "agent_id": agent.id,
                "name": agent.name,
                "role": agent.role,
                "abilities": {
                    "martial": agent.martial,
                    "intelligence": agent.intelligence,
                    "charisma": agent.charisma,
                    "politics": agent.politics,
                },
            },
            "api_key": {
                "id": key.id,
                "name": key.name,
                "key": plain_key,
                "key_preview": f"{key.key_prefix}...{key.last4}",
            },
            "claim_code": claim_code,
            "claim_expires_at": ticket.expires_at.isoformat(),
            "faction": faction_data,
        },
    }


@router.post("/agent/{agent_id}/claim-code/regenerate")
def regenerate_claim_code(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)
    if agent.owner_user_id != current_user.id:
        raise AppError("FORBIDDEN", "You do not own this agent.", status_code=403)

    claim_code = make_claim_code()
    ticket = db.query(AgentClaimTicket).filter(AgentClaimTicket.agent_id == agent.id).first()
    if not ticket:
        ticket = AgentClaimTicket(
            agent_id=agent.id,
            code_hash=hash_secret(claim_code),
            expires_at=utc_now() + timedelta(days=30),
        )
    else:
        ticket.code_hash = hash_secret(claim_code)
        ticket.expires_at = utc_now() + timedelta(days=30)
        ticket.used_at = None
    db.add(ticket)
    db.commit()

    return {
        "success": True,
        "data": {
            "agent_id": agent.id,
            "name": agent.name,
            "claim_code": claim_code,
            "claim_expires_at": ticket.expires_at.isoformat(),
            "abilities": {
                "martial": agent.martial,
                "intelligence": agent.intelligence,
                "charisma": agent.charisma,
                "politics": agent.politics,
            },
        },
    }
