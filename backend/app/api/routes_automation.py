import json
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..api.deps import get_current_user
from ..auth import create_access_token, hash_password
from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import Agent, AgentClaimTicket, ApiKey, Faction, User, utc_now
from ..rules import COMPAT_ALLOWED_ACTIONS, LEGACY_ALLOWED_ACTIONS
from ..schemas import BootstrapAIAgentRequest
from ..services.abilities import roll_abilities
from ..services.chronicle import write_chronicle
from ..services import identity as identity_service
from ..services.secrets import hash_secret, make_api_key, make_claim_code, make_password
from ..services.positions import STARTING_ROLE_ZH

router = APIRouter(prefix="/automation", tags=["automation"])


def _identity_key(payload: BootstrapAIAgentRequest) -> str:
    if payload.request_id:
        return identity_service.make_identity_key("req", payload.request_id)
    # 沒給 request_id 時，用 agent 名稱當指紋：同一個諸侯重送不會長出分身。
    return identity_service.make_identity_key("name", payload.agent_name)


def _already_registered(db: Session, identity_key: str, agent: Agent) -> dict:
    db.rollback()
    return {
        "success": True,
        "data": {
            "registration_status": "already_registered",
            "identity_key": identity_key,
            "agent": identity_service.registration_summary(agent),
            "recovery": identity_service.recovery_hint(),
            "note": (
                "This identity was already registered. Credentials are never re-sent; "
                "use one of the recovery paths above instead of bootstrapping again."
            ),
        },
    }


@router.post("/agent/bootstrap")
def bootstrap_ai_agent(payload: BootstrapAIAgentRequest, db: Session = Depends(get_db)):
    """建立 AI 諸侯。整個註冊改成單一交易 + 冪等指紋，逾時重送不會產生分身。"""
    identity_key = _identity_key(payload)
    status, existing = identity_service.begin_registration(db, identity_key)
    if status == "duplicate" and existing is not None:
        return _already_registered(db, identity_key, existing)
    if status == "in_progress":
        db.rollback()
        raise AppError(
            "REGISTRATION_IN_PROGRESS",
            "A registration with this identity is already in progress; retry shortly instead of resending.",
            status_code=409,
        )

    username = payload.username
    if not username:
        base = f"ai_{payload.agent_name.lower()[:20]}"
        suffix = make_password(8).lower()
        username = f"{base}_{suffix}"

    if db.query(User).filter(User.username == username).first():
        db.rollback()
        raise AppError("USERNAME_EXISTS", "Username already exists.", status_code=409)

    password = payload.password or make_password(24)
    user = User(
        username=username,
        email=f"{username}@agents.local",
        password_hash=hash_password(password),
        is_admin=False,
    )
    db.add(user)
    db.flush()

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
    db.flush()

    faction_data = None
    if payload.faction_name:
        if db.query(Faction).filter(Faction.name == payload.faction_name).first():
            db.rollback()
            raise AppError("FACTION_EXISTS", "Faction name already exists.", status_code=409)
        faction = Faction(name=payload.faction_name, leader_agent_id=agent.id, home_city=agent.home_city)
        db.add(faction)
        db.flush()
        agent.faction_id = faction.id
        db.add(agent)
        faction_data = {"faction_id": faction.id, "name": faction.name}

    plain_key = make_api_key()
    key = ApiKey(
        owner_user_id=user.id,
        agent_id=agent.id,
        name=payload.key_name,
        key_prefix=plain_key[:10],
        key_hash=hash_secret(plain_key),
        last4=plain_key[-4:],
        scope_json=json.dumps(["agent:read", "action:submit"], ensure_ascii=False),
        rate_limit="60/min",
        allowed_actions_json=json.dumps(["farm", "trade", "move"], ensure_ascii=False),
        expires_at=utc_now() + timedelta(days=30),
    )
    db.add(key)

    claim_code = make_claim_code()
    ticket = AgentClaimTicket(
        agent_id=agent.id,
        code_hash=hash_secret(claim_code),
        expires_at=utc_now() + timedelta(days=30),
    )
    db.add(ticket)
    identity_service.record_identity(db, agent.id, identity_key, "bootstrap")

    write_chronicle(
        db,
        event_type="agent",
        title=f"{agent.name} auto-bootstrapped",
        content=f"{agent.name} was initialized by automation bootstrap.",
    )
    token = create_access_token(user.id)
    db.flush()

    data = {
        "registration_status": "created",
        "identity_key": identity_key,
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
            "scope": ["agent:read", "action:submit"],
            "rate_limit": key.rate_limit,
            "allowed_actions": sorted(LEGACY_ALLOWED_ACTIONS),
            # 舊預設白名單自動相容後來新增的基礎動作，不需為舊 agent 換 key。
            "effective_allowed_actions": sorted(LEGACY_ALLOWED_ACTIONS | COMPAT_ALLOWED_ACTIONS),
            "expires_at": key.expires_at.isoformat() if key.expires_at else None,
        },
        "claim_code": claim_code,
        "claim_expires_at": ticket.expires_at.isoformat(),
        "faction": faction_data,
        "recovery": identity_service.recovery_hint(),
    }
    db.commit()
    return {"success": True, "data": data}


@router.post("/agent/{agent_id}/claim-code/regenerate")
def regenerate_claim_code(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI 帳號用 JWT 重簽 claim code（與 /agent/claim-code 共用每日上限）。

    不比對 agent.owner_user_id：舊版認領曾把 owner 改給 human，
    只要求「這支 token 的帳號確實擁有該 agent 的 API key」即可。
    """
    agent = db.get(Agent, agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)
    owns_key = (
        db.query(ApiKey)
        .filter(
            ApiKey.agent_id == agent.id,
            ApiKey.owner_user_id == current_user.id,
            ApiKey.revoked_at.is_(None),
        )
        .first()
    )
    if not owns_key:
        raise AppError("FORBIDDEN", "You do not own this agent.", status_code=403)

    result = identity_service.issue_claim_code(db, agent)
    db.commit()
    return {
        "success": True,
        "data": {
            **result,
            "abilities": {
                "martial": agent.martial,
                "intelligence": agent.intelligence,
                "charisma": agent.charisma,
                "politics": agent.politics,
            },
        },
    }
