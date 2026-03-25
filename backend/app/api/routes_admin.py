from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..api.deps import get_current_admin
from ..auth import hash_password
from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import (
    ActionLog,
    Announcement,
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
from ..schemas import (
    AdminResetPasswordRequest,
    AdminUpdateAgentRequest,
    AdminUpdateClaimExpiryRequest,
    AdminUpdateUserRequest,
    AnnouncementCreateRequest,
    AnnouncementUpdateRequest,
)
from ..services.secrets import hash_secret, make_claim_code

router = APIRouter(prefix="/admin", tags=["admin"])


def _delete_agent_related(db: Session, agent_id: int) -> None:
    db.query(ActionLog).filter(ActionLog.agent_id == agent_id).delete(synchronize_session=False)
    db.query(Message).filter((Message.from_agent_id == agent_id) | (Message.to_agent_id == agent_id)).delete(
        synchronize_session=False
    )
    db.query(AgentClaimTicket).filter(AgentClaimTicket.agent_id == agent_id).delete(synchronize_session=False)
    db.query(AgentClaim).filter(AgentClaim.agent_id == agent_id).delete(synchronize_session=False)
    db.query(ApiKey).filter(ApiKey.agent_id == agent_id).delete(synchronize_session=False)


def _normalize_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_expiry_iso(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppError("INVALID_DATETIME", "Invalid expires_at datetime format.", status_code=422) from exc
    out = _normalize_utc(parsed)
    if out <= datetime.now(timezone.utc):
        raise AppError("INVALID_DATETIME", "expires_at must be in the future.", status_code=422)
    return out


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
    agent_ids = [a.id for a in agents]
    tickets = (
        db.query(AgentClaimTicket).filter(AgentClaimTicket.agent_id.in_(agent_ids)).all()
        if agent_ids
        else []
    )
    tickets_by_agent = {t.agent_id: t for t in tickets}

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
                    "claim_code": "******" if tickets_by_agent.get(a.id) else None,
                    "claim_expires_at": (
                        _normalize_utc(tickets_by_agent[a.id].expires_at).isoformat()
                        if tickets_by_agent.get(a.id)
                        else None
                    ),
                    "claim_used_at": (
                        _normalize_utc(tickets_by_agent[a.id].used_at).isoformat()
                        if tickets_by_agent.get(a.id) and tickets_by_agent[a.id].used_at
                        else None
                    ),
                }
                for a in agents
            ],
            "announcements": [
                {
                    "id": a.id,
                    "title": a.title,
                    "content": a.content,
                    "published": a.published,
                    "created_by_user_id": a.created_by_user_id,
                    "created_at": a.created_at.isoformat(),
                    "updated_at": a.updated_at.isoformat(),
                }
                for a in db.query(Announcement).order_by(Announcement.id.desc()).all()
            ],
        },
    }


@router.get("/users")
def admin_list_users(
    query: str = Query(default=""),
    is_admin: str = Query(default="all"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    _ = current_admin
    q = db.query(User)
    if query.strip():
        like = f"%{query.strip()}%"
        q = q.filter(or_(User.username.ilike(like), User.email.ilike(like)))
    if is_admin in ("true", "false"):
        q = q.filter(User.is_admin.is_(is_admin == "true"))
    total = q.count()
    rows = (
        q.order_by(User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "success": True,
        "data": {
            "items": [
                {
                    "id": u.id,
                    "username": u.username,
                    "email": u.email,
                    "is_admin": u.is_admin,
                    "created_at": u.created_at.isoformat(),
                    "agent_count": db.query(func.count(Agent.id)).filter(Agent.owner_user_id == u.id).scalar() or 0,
                }
                for u in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


@router.patch("/users/{user_id}")
def admin_update_user(
    user_id: int,
    payload: AdminUpdateUserRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise AppError("USER_NOT_FOUND", "The specified user does not exist.", status_code=404)
    if payload.username is not None:
        out = payload.username.strip()
        if db.query(User).filter(User.username == out, User.id != user.id).first():
            raise AppError("USERNAME_EXISTS", "Username already exists.", status_code=409)
        user.username = out
    if payload.email is not None:
        if db.query(User).filter(User.email == payload.email, User.id != user.id).first():
            raise AppError("EMAIL_EXISTS", "Email already exists.", status_code=409)
        user.email = payload.email
    if payload.is_admin is not None:
        if current_admin.id == user.id and payload.is_admin is False:
            raise AppError("FORBIDDEN", "Admin cannot remove own admin permission.", status_code=403)
        user.is_admin = payload.is_admin
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "success": True,
        "data": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin,
            "created_at": user.created_at.isoformat(),
        },
    }


@router.get("/agents")
def admin_list_agents(
    query: str = Query(default=""),
    role: str = Query(default="all"),
    owner_user_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    _ = current_admin
    q = db.query(Agent)
    if query.strip():
        like = f"%{query.strip()}%"
        q = q.filter(Agent.name.ilike(like))
    if role != "all":
        q = q.filter(Agent.role == role)
    if owner_user_id is not None:
        q = q.filter(Agent.owner_user_id == owner_user_id)
    total = q.count()
    rows = (
        q.order_by(Agent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    agent_ids = [a.id for a in rows]
    tickets = db.query(AgentClaimTicket).filter(AgentClaimTicket.agent_id.in_(agent_ids)).all() if agent_ids else []
    tickets_by_agent = {t.agent_id: t for t in tickets}
    return {
        "success": True,
        "data": {
            "items": [
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
                    "claim_code": "******" if tickets_by_agent.get(a.id) else None,
                    "claim_expires_at": (
                        _normalize_utc(tickets_by_agent[a.id].expires_at).isoformat()
                        if tickets_by_agent.get(a.id)
                        else None
                    ),
                    "claim_used_at": (
                        _normalize_utc(tickets_by_agent[a.id].used_at).isoformat()
                        if tickets_by_agent.get(a.id) and tickets_by_agent[a.id].used_at
                        else None
                    ),
                }
                for a in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


@router.patch("/agents/{agent_id}")
def admin_update_agent(
    agent_id: int,
    payload: AdminUpdateAgentRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    _ = current_admin
    agent = db.get(Agent, agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)
    for key in ("name", "role", "home_city", "current_city", "energy", "gold", "food"):
        val = getattr(payload, key)
        if val is not None:
            setattr(agent, key, val)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return {
        "success": True,
        "data": {
            "id": agent.id,
            "name": agent.name,
            "owner_user_id": agent.owner_user_id,
            "role": agent.role,
            "home_city": agent.home_city,
            "current_city": agent.current_city,
            "energy": agent.energy,
            "gold": agent.gold,
            "food": agent.food,
            "created_at": agent.created_at.isoformat(),
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


@router.post("/agents/{agent_id}/claim-code/regenerate")
def admin_regenerate_agent_claim_code(
    agent_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    _ = current_admin
    agent = db.get(Agent, agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)

    claim_code = make_claim_code()
    ticket = db.query(AgentClaimTicket).filter(AgentClaimTicket.agent_id == agent.id).first()
    if not ticket:
        ticket = AgentClaimTicket(
            agent_id=agent.id,
            code_hash=hash_secret(claim_code),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    else:
        ticket.code_hash = hash_secret(claim_code)
        ticket.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        ticket.used_at = None
    db.add(ticket)
    db.commit()

    return {
        "success": True,
        "data": {
            "agent_id": agent.id,
            "claim_code": claim_code,
            "claim_expires_at": _normalize_utc(ticket.expires_at).isoformat(),
            "claim_used_at": ticket.used_at.isoformat() if ticket.used_at else None,
        },
    }


@router.post("/agents/{agent_id}/claim-expiry")
def admin_update_agent_claim_expiry(
    agent_id: int,
    payload: AdminUpdateClaimExpiryRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    _ = current_admin
    agent = db.get(Agent, agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)

    new_expiry = _parse_expiry_iso(payload.expires_at)
    ticket = db.query(AgentClaimTicket).filter(AgentClaimTicket.agent_id == agent.id).first()
    claim_code: str | None = None
    if not ticket:
        claim_code = make_claim_code()
        ticket = AgentClaimTicket(
            agent_id=agent.id,
            code_hash=hash_secret(claim_code),
            expires_at=new_expiry,
            used_at=None,
        )
    else:
        ticket.expires_at = new_expiry
    db.add(ticket)
    db.commit()

    return {
        "success": True,
        "data": {
            "agent_id": agent.id,
            "claim_code": claim_code,
            "claim_expires_at": _normalize_utc(ticket.expires_at).isoformat(),
            "claim_used_at": ticket.used_at.isoformat() if ticket.used_at else None,
            "created_new_ticket": claim_code is not None,
        },
    }


@router.post("/announcements")
def admin_create_announcement(
    payload: AnnouncementCreateRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    row = Announcement(
        title=payload.title.strip(),
        content=payload.content.strip(),
        published=payload.published,
        created_by_user_id=current_admin.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "success": True,
        "data": {
            "id": row.id,
            "title": row.title,
            "content": row.content,
            "published": row.published,
            "created_by_user_id": row.created_by_user_id,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        },
    }


@router.patch("/announcements/{announcement_id}")
def admin_update_announcement(
    announcement_id: int,
    payload: AnnouncementUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    _ = current_admin
    row = db.get(Announcement, announcement_id)
    if not row:
        raise AppError("ANNOUNCEMENT_NOT_FOUND", "Announcement does not exist.", status_code=404)
    if payload.title is not None:
        row.title = payload.title.strip()
    if payload.content is not None:
        row.content = payload.content.strip()
    if payload.published is not None:
        row.published = payload.published
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "success": True,
        "data": {
            "id": row.id,
            "title": row.title,
            "content": row.content,
            "published": row.published,
            "created_by_user_id": row.created_by_user_id,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        },
    }


@router.delete("/announcements/{announcement_id}")
def admin_delete_announcement(
    announcement_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    _ = current_admin
    row = db.get(Announcement, announcement_id)
    if not row:
        raise AppError("ANNOUNCEMENT_NOT_FOUND", "Announcement does not exist.", status_code=404)
    db.delete(row)
    db.commit()
    return {"success": True, "data": {"deleted": True, "announcement_id": announcement_id}}
