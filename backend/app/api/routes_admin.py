from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..api.deps import get_current_admin
from ..auth import hash_password
from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import (
    ActionLog,
    Agent,
    AgentClaim,
    AgentClaimTicket,
    ApiKey,
    City,
    Message,
    PasswordResetCode,
    User,
)
from ..rules import prosperity
from ..schemas import AdminResetPasswordRequest

router = APIRouter(prefix="/admin", tags=["admin"])


def _delete_agent_related(db: Session, agent_id: int) -> None:
    db.query(ActionLog).filter(ActionLog.agent_id == agent_id).delete(synchronize_session=False)
    db.query(Message).filter((Message.from_agent_id == agent_id) | (Message.to_agent_id == agent_id)).delete(
        synchronize_session=False
    )
    db.query(AgentClaimTicket).filter(AgentClaimTicket.agent_id == agent_id).delete(synchronize_session=False)
    db.query(AgentClaim).filter(AgentClaim.agent_id == agent_id).delete(synchronize_session=False)
    db.query(ApiKey).filter(ApiKey.agent_id == agent_id).delete(synchronize_session=False)


@router.post("/bootstrap")
def bootstrap_world(db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    _ = current_admin
    city = db.query(City).filter(City.name == settings.city_name).first()
    if not city:
        city = City(
            name=settings.city_name,
            base_url=settings.city_base_url,
            city_wall=settings.city_wall,
            city_tax_rate=settings.city_tax_rate,
            protocol_version=settings.protocol_version,
            rule_version=settings.rule_version,
            open_for_migration=settings.open_for_migration,
        )

    agent_count = db.query(func.count(Agent.id)).filter(Agent.current_city == settings.city_name).scalar() or 0
    city.prosperity = round(prosperity(agent_count), 4)
    db.add(city)
    db.commit()
    db.refresh(city)

    return {
        "success": True,
        "data": {
            "city_id": city.id,
            "city_name": city.name,
            "base_url": city.base_url,
            "prosperity": city.prosperity,
        },
    }


@router.get("/overview")
def admin_overview(db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    _ = current_admin

    users = db.query(User).order_by(User.id.asc()).all()
    agents = db.query(Agent).order_by(Agent.id.asc()).all()

    return {
        "success": True,
        "data": {
            "users": [
                {
                    "id": u.id,
                    "username": u.username,
                    "email": u.email,
                    "is_admin": u.is_admin,
                    "created_at": u.created_at.isoformat(),
                    "agent_count": db.query(func.count(Agent.id)).filter(Agent.owner_user_id == u.id).scalar() or 0,
                }
                for u in users
            ],
            "agents": [
                {
                    "id": a.id,
                    "name": a.name,
                    "owner_user_id": a.owner_user_id,
                    "role": a.role,
                    "home_city": a.home_city,
                    "current_city": a.current_city,
                    "energy": a.energy,
                    "gold": a.gold,
                    "food": a.food,
                    "created_at": a.created_at.isoformat(),
                }
                for a in agents
            ],
        },
    }


@router.delete("/agents/{agent_id}")
def delete_agent(agent_id: int, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    _ = current_admin
    agent = db.get(Agent, agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)

    _delete_agent_related(db, agent.id)
    db.delete(agent)
    db.commit()
    return {"success": True, "data": {"deleted": True, "agent_id": agent_id}}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    if current_admin.id == user_id:
        raise AppError("FORBIDDEN", "Admin cannot delete self account.", status_code=403)

    user = db.get(User, user_id)
    if not user:
        raise AppError("USER_NOT_FOUND", "The specified user does not exist.", status_code=404)

    owned_agents = db.query(Agent).filter(Agent.owner_user_id == user.id).all()
    for agent in owned_agents:
        _delete_agent_related(db, agent.id)
        db.delete(agent)

    db.query(ApiKey).filter(ApiKey.owner_user_id == user.id).delete(synchronize_session=False)
    db.query(AgentClaim).filter(AgentClaim.human_user_id == user.id).delete(synchronize_session=False)
    db.query(PasswordResetCode).filter(PasswordResetCode.user_id == user.id).delete(synchronize_session=False)

    db.delete(user)
    db.commit()
    return {"success": True, "data": {"deleted": True, "user_id": user_id}}


@router.post("/users/{user_id}/reset-password")
def admin_reset_user_password(
    user_id: int,
    payload: AdminResetPasswordRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    _ = current_admin
    user = db.get(User, user_id)
    if not user:
        raise AppError("USER_NOT_FOUND", "The specified user does not exist.", status_code=404)

    user.password_hash = hash_password(payload.new_password)
    db.query(PasswordResetCode).filter(PasswordResetCode.user_id == user.id).delete(synchronize_session=False)
    db.add(user)
    db.commit()

    return {"success": True, "data": {"user_id": user.id, "password_reset": True}}
