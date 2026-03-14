from datetime import timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..api.deps import get_current_user
from ..db import get_db
from ..errors import AppError
from ..models import ActionLog, Agent, AgentClaim, AgentClaimTicket, Faction, Message, User, utc_now
from ..schemas import ClaimAgentRequest
from ..services.secrets import hash_secret

router = APIRouter(prefix="/viewer", tags=["viewer"])


def _ensure_claimed(db: Session, user_id: int, agent_id: int) -> Agent:
    claim = db.query(AgentClaim).filter(AgentClaim.human_user_id == user_id, AgentClaim.agent_id == agent_id).first()
    if not claim:
        raise AppError("FORBIDDEN", "You have not claimed this agent.", status_code=403)
    agent = db.get(Agent, agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)
    return agent


@router.post("/claim")
def claim_agent(
    payload: ClaimAgentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    code_hash = hash_secret(payload.claim_code)
    ticket = db.query(AgentClaimTicket).filter(AgentClaimTicket.code_hash == code_hash).first()
    now = utc_now()
    if ticket and ticket.expires_at.tzinfo is None:
        ticket_expires_at = ticket.expires_at.replace(tzinfo=timezone.utc)
    else:
        ticket_expires_at = ticket.expires_at if ticket else None
    if not ticket or ticket.used_at is not None or (ticket_expires_at and ticket_expires_at < now):
        raise AppError("CLAIM_CODE_INVALID", "The claim code is invalid or expired.", status_code=404)

    existing_agent_claim = db.query(AgentClaim).filter(AgentClaim.agent_id == ticket.agent_id).first()
    if existing_agent_claim and existing_agent_claim.human_user_id != current_user.id:
        raise AppError("AGENT_ALREADY_CLAIMED", "This agent has already been claimed by another user.", status_code=409)

    existing_user_claim = db.query(AgentClaim).filter(
        AgentClaim.agent_id == ticket.agent_id, AgentClaim.human_user_id == current_user.id
    ).first()
    if not existing_user_claim:
        db.add(AgentClaim(human_user_id=current_user.id, agent_id=ticket.agent_id))
    ticket.used_at = now
    db.add(ticket)
    db.commit()

    agent = db.get(Agent, ticket.agent_id)
    return {
        "success": True,
        "data": {"agent_id": agent.id, "name": agent.name, "role": agent.role, "current_city": agent.current_city},
    }


@router.get("/agents")
def list_claimed_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    claims = db.query(AgentClaim).filter(AgentClaim.human_user_id == current_user.id).order_by(AgentClaim.id.desc()).all()
    out = []
    for claim in claims:
        agent = db.get(Agent, claim.agent_id)
        if not agent:
            continue
        out.append(
            {
                "agent_id": agent.id,
                "name": agent.name,
                "role": agent.role,
                "home_city": agent.home_city,
                "current_city": agent.current_city,
                "energy": agent.energy,
                "gold": agent.gold,
                "food": agent.food,
                "faction_id": agent.faction_id,
                "claimed_at": claim.created_at.isoformat(),
            }
        )
    return {"success": True, "data": {"items": out}}


@router.get("/agent/{agent_id}/overview")
def agent_overview(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = _ensure_claimed(db, current_user.id, agent_id)
    faction = db.get(Faction, agent.faction_id) if agent.faction_id else None

    logs = (
        db.query(ActionLog)
        .filter(ActionLog.agent_id == agent.id)
        .order_by(ActionLog.id.desc())
        .limit(20)
        .all()
    )
    messages = (
        db.query(Message)
        .filter((Message.from_agent_id == agent.id) | (Message.to_agent_id == agent.id))
        .order_by(Message.id.desc())
        .limit(20)
        .all()
    )

    return {
        "success": True,
        "data": {
            "agent": {
                "id": agent.id,
                "name": agent.name,
                "role": agent.role,
                "home_city": agent.home_city,
                "current_city": agent.current_city,
                "energy": agent.energy,
                "gold": agent.gold,
                "food": agent.food,
                "abilities": {
                    "martial": agent.martial,
                    "intelligence": agent.intelligence,
                    "charisma": agent.charisma,
                    "politics": agent.politics,
                },
                "faction_id": agent.faction_id,
                "lord_agent_id": agent.lord_agent_id,
            },
            "faction": (
                {
                    "id": faction.id,
                    "name": faction.name,
                    "leader_agent_id": faction.leader_agent_id,
                    "home_city": faction.home_city,
                }
                if faction
                else None
            ),
            "recent_actions": [
                {
                    "id": l.id,
                    "action_type": l.action_type,
                    "energy_cost": l.energy_cost,
                    "payload_json": l.payload_json,
                    "result_json": l.result_json,
                    "created_at": l.created_at.isoformat(),
                }
                for l in logs
            ],
            "recent_messages": [
                {
                    "id": m.id,
                    "from_agent_id": m.from_agent_id,
                    "to_agent_id": m.to_agent_id,
                    "message_type": m.message_type,
                    "content": m.content,
                    "status": m.status,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
        },
    }
