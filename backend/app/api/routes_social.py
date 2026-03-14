from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..api.deps import get_current_user
from ..db import get_db
from ..errors import AppError
from ..models import Agent, Faction, Message, User
from ..schemas import CreateFactionRequest, InboxMarkReadRequest, InboxReplyRequest, JoinLordRequest, MessageRequest
from ..services.chronicle import write_chronicle

router = APIRouter(prefix="/social", tags=["social"])
LORD_TO_VASSAL_BONUS_PCT = 1.0
VASSAL_TO_LORD_BONUS_PCT = 0.1


def _normalize_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_owned_agent(db: Session, user_id: int, agent_id: int) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)
    if agent.owner_user_id != user_id:
        raise AppError("FORBIDDEN", "You do not own this agent.", status_code=403)
    return agent


def _list_owned_agents(db: Session, user_id: int) -> list[Agent]:
    return db.query(Agent).filter(Agent.owner_user_id == user_id).order_by(Agent.id.asc()).all()


@router.post("/join-lord")
def join_lord(
    payload: JoinLordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = _get_owned_agent(db, current_user.id, payload.agent_id)
    lord = db.get(Agent, payload.lord_agent_id)
    if not lord:
        raise AppError("LORD_NOT_FOUND", "Target lord agent does not exist.", status_code=404)
    if lord.id == agent.id:
        raise AppError("INVALID_LORD", "Agent cannot join itself.", status_code=422)

    agent.lord_agent_id = lord.id
    agent.faction_id = lord.faction_id
    db.add(agent)
    write_chronicle(
        db,
        event_type="social",
        title=f"{agent.name} joined {lord.name}",
        content=f"{agent.name} is now vassal of {lord.name}.",
    )
    db.commit()

    return {
        "success": True,
        "data": {
            "agent_id": agent.id,
            "lord_agent_id": lord.id,
            "faction_id": agent.faction_id,
            "vassal_bonus_pct": LORD_TO_VASSAL_BONUS_PCT,
            "lord_bonus_pct": VASSAL_TO_LORD_BONUS_PCT,
        },
    }


@router.post("/recruit")
def recruit(
    lord_agent_id: int,
    target_agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lord = _get_owned_agent(db, current_user.id, lord_agent_id)
    target = db.get(Agent, target_agent_id)
    if not target:
        raise AppError("AGENT_NOT_FOUND", "Target agent does not exist.", status_code=404)
    if target.id == lord.id:
        raise AppError("INVALID_TARGET", "Cannot recruit self.", status_code=422)

    target.lord_agent_id = lord.id
    if lord.faction_id:
        target.faction_id = lord.faction_id
    db.add(target)
    write_chronicle(
        db,
        event_type="social",
        title=f"{lord.name} recruited {target.name}",
        content=f"{target.name} joined under lord {lord.name}.",
    )
    db.commit()

    return {
        "success": True,
        "data": {
            "lord_agent_id": lord.id,
            "target_agent_id": target.id,
            "faction_id": target.faction_id,
            "status": "accepted",
            "vassal_bonus_pct": LORD_TO_VASSAL_BONUS_PCT,
            "lord_bonus_pct": VASSAL_TO_LORD_BONUS_PCT,
        },
    }


@router.post("/message")
def message(
    payload: MessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = _get_owned_agent(db, current_user.id, payload.from_agent_id)
    target = db.get(Agent, payload.to_agent_id)
    if not target:
        raise AppError("AGENT_NOT_FOUND", "Target agent does not exist.", status_code=404)

    msg = Message(
        from_agent_id=payload.from_agent_id,
        to_agent_id=payload.to_agent_id,
        message_type=payload.message_type,
        content=payload.content,
        status="pending",
    )
    db.add(msg)
    incoming_to_reply = (
        db.query(Message)
        .filter(
            Message.from_agent_id == payload.to_agent_id,
            Message.to_agent_id == payload.from_agent_id,
            Message.replied_at.is_(None),
        )
        .all()
    )
    now = datetime.now(timezone.utc)
    for item in incoming_to_reply:
        item.replied_at = now
        if item.read_at is None:
            item.read_at = now
            item.status = "read"
        item.status = "replied"
        db.add(item)
    write_chronicle(
        db,
        event_type="diplomacy",
        title=f"Message: {payload.message_type}",
        content=f"{payload.from_agent_id} -> {payload.to_agent_id}: {payload.content}",
    )
    db.commit()
    db.refresh(msg)

    return {
        "success": True,
        "data": {
            "id": msg.id,
            "from_agent_id": msg.from_agent_id,
            "to_agent_id": msg.to_agent_id,
            "message_type": msg.message_type,
            "content": msg.content,
            "status": msg.status,
            "read_at": msg.read_at.isoformat() if msg.read_at else None,
            "replied_at": msg.replied_at.isoformat() if msg.replied_at else None,
            "created_at": msg.created_at.isoformat(),
        },
    }


@router.get("/messages")
def list_messages(
    agent_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = _get_owned_agent(db, current_user.id, agent_id)
    messages = (
        db.query(Message)
        .filter((Message.from_agent_id == agent_id) | (Message.to_agent_id == agent_id))
        .order_by(Message.id.desc())
        .all()
    )

    return {
        "success": True,
        "data": {
            "messages": [
                {
                    "id": m.id,
                    "from_agent_id": m.from_agent_id,
                    "to_agent_id": m.to_agent_id,
                    "message_type": m.message_type,
                    "content": m.content,
                    "status": m.status,
                    "read_at": m.read_at.isoformat() if m.read_at else None,
                    "replied_at": m.replied_at.isoformat() if m.replied_at else None,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ]
        },
    }


@router.get("/dialogues")
def list_dialogues(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    owned_agents = _list_owned_agents(db, current_user.id)
    owned_ids = [a.id for a in owned_agents]
    if not owned_ids:
        return {"success": True, "data": {"messages": [], "owned_agents": []}}

    messages = (
        db.query(Message)
        .filter((Message.from_agent_id.in_(owned_ids)) | (Message.to_agent_id.in_(owned_ids)))
        .order_by(Message.id.desc())
        .limit(limit)
        .all()
    )
    involved_ids = sorted({m.from_agent_id for m in messages} | {m.to_agent_id for m in messages})
    involved_agents = db.query(Agent).filter(Agent.id.in_(involved_ids)).all() if involved_ids else []
    name_map = {a.id: a.name for a in involved_agents}

    return {
        "success": True,
        "data": {
            "owned_agents": [
                {"id": a.id, "name": a.name, "role": a.role, "current_city": a.current_city}
                for a in owned_agents
            ],
            "messages": [
                {
                    "id": m.id,
                    "from_agent_id": m.from_agent_id,
                    "from_agent_name": name_map.get(m.from_agent_id, str(m.from_agent_id)),
                    "to_agent_id": m.to_agent_id,
                    "to_agent_name": name_map.get(m.to_agent_id, str(m.to_agent_id)),
                    "message_type": m.message_type,
                    "content": m.content,
                    "status": m.status,
                    "read_at": m.read_at.isoformat() if m.read_at else None,
                    "replied_at": m.replied_at.isoformat() if m.replied_at else None,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
        },
    }


@router.get("/inbox")
def list_agent_inbox(
    agent_id: int = Query(...),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = _get_owned_agent(db, current_user.id, agent_id)
    messages = (
        db.query(Message)
        .filter((Message.from_agent_id == agent.id) | (Message.to_agent_id == agent.id))
        .order_by(Message.id.desc())
        .limit(limit)
        .all()
    )
    summary_map: dict[int, dict] = {}
    peer_ids: set[int] = set()
    for msg in messages:
        peer_id = msg.to_agent_id if msg.from_agent_id == agent.id else msg.from_agent_id
        peer_ids.add(peer_id)
        incoming = msg.to_agent_id == agent.id
        if peer_id not in summary_map:
            summary_map[peer_id] = {
                "peer_agent_id": peer_id,
                "latest_message_id": msg.id,
                "latest_message_type": msg.message_type,
                "latest_content": msg.content,
                "latest_from_agent_id": msg.from_agent_id,
                "latest_to_agent_id": msg.to_agent_id,
                "latest_at": _normalize_utc(msg.created_at),
                "unread_count": 0,
                "unreplied_count": 0,
            }
        if incoming and msg.read_at is None:
            summary_map[peer_id]["unread_count"] += 1
        if incoming and msg.replied_at is None:
            summary_map[peer_id]["unreplied_count"] += 1

    peers = db.query(Agent).filter(Agent.id.in_(peer_ids)).all() if peer_ids else []
    peer_name_map = {p.id: p.name for p in peers}
    peer_role_map = {p.id: p.role for p in peers}

    items = []
    for row in summary_map.values():
        latest_at = row["latest_at"]
        unread_count = row["unread_count"]
        unreplied_count = row["unreplied_count"]
        items.append(
            {
                "peer_agent_id": row["peer_agent_id"],
                "peer_agent_name": peer_name_map.get(row["peer_agent_id"], str(row["peer_agent_id"])),
                "peer_agent_role": peer_role_map.get(row["peer_agent_id"], ""),
                "latest_message_id": row["latest_message_id"],
                "latest_message_type": row["latest_message_type"],
                "latest_content": row["latest_content"],
                "latest_from_agent_id": row["latest_from_agent_id"],
                "latest_to_agent_id": row["latest_to_agent_id"],
                "latest_at": latest_at.isoformat(),
                "unread_count": unread_count,
                "unreplied_count": unreplied_count,
                "pending_count": unread_count + unreplied_count,
                "thread_status": (
                    "unreplied"
                    if unreplied_count > 0
                    else ("unread" if unread_count > 0 else "synced")
                ),
            }
        )

    items.sort(
        key=lambda x: (
            x["unread_count"] > 0,
            x["unreplied_count"] > 0,
            x["latest_at"],
        ),
        reverse=True,
    )
    return {"success": True, "data": {"agent_id": agent.id, "agent_name": agent.name, "items": items}}


@router.get("/inbox/history")
def get_agent_inbox_history(
    agent_id: int = Query(...),
    peer_agent_id: int = Query(...),
    limit: int = Query(default=100, ge=1, le=500),
    mark_read: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = _get_owned_agent(db, current_user.id, agent_id)
    peer = db.get(Agent, peer_agent_id)
    if not peer:
        raise AppError("AGENT_NOT_FOUND", "Target agent does not exist.", status_code=404)

    messages = (
        db.query(Message)
        .filter(
            ((Message.from_agent_id == agent.id) & (Message.to_agent_id == peer.id))
            | ((Message.from_agent_id == peer.id) & (Message.to_agent_id == agent.id))
        )
        .order_by(Message.id.desc())
        .limit(limit)
        .all()
    )
    messages = list(reversed(messages))

    if mark_read:
        now = datetime.now(timezone.utc)
        for msg in messages:
            if msg.from_agent_id == peer.id and msg.to_agent_id == agent.id and msg.read_at is None:
                msg.read_at = now
                if msg.status == "pending":
                    msg.status = "read"
                db.add(msg)
        db.commit()

    return {
        "success": True,
        "data": {
            "agent_id": agent.id,
            "peer_agent_id": peer.id,
            "peer_agent_name": peer.name,
            "messages": [
                {
                    "id": m.id,
                    "from_agent_id": m.from_agent_id,
                    "to_agent_id": m.to_agent_id,
                    "message_type": m.message_type,
                    "content": m.content,
                    "status": m.status,
                    "read_at": m.read_at.isoformat() if m.read_at else None,
                    "replied_at": m.replied_at.isoformat() if m.replied_at else None,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
        },
    }


@router.post("/inbox/mark-read")
def mark_agent_inbox_read(
    payload: InboxMarkReadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = _get_owned_agent(db, current_user.id, payload.agent_id)
    now = datetime.now(timezone.utc)
    targets = (
        db.query(Message)
        .filter(
            Message.from_agent_id == payload.peer_agent_id,
            Message.to_agent_id == payload.agent_id,
            Message.read_at.is_(None),
        )
        .all()
    )
    for msg in targets:
        msg.read_at = now
        if msg.status == "pending":
            msg.status = "read"
        db.add(msg)
    db.commit()
    return {"success": True, "data": {"agent_id": payload.agent_id, "peer_agent_id": payload.peer_agent_id, "marked": len(targets)}}


@router.post("/inbox/reply")
def reply_agent_inbox(
    payload: InboxReplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = _get_owned_agent(db, current_user.id, payload.from_agent_id)
    target = db.get(Agent, payload.to_agent_id)
    if not target:
        raise AppError("AGENT_NOT_FOUND", "Target agent does not exist.", status_code=404)

    now = datetime.now(timezone.utc)
    to_mark = (
        db.query(Message)
        .filter(
            Message.from_agent_id == payload.to_agent_id,
            Message.to_agent_id == payload.from_agent_id,
            Message.replied_at.is_(None),
        )
        .all()
    )
    for msg in to_mark:
        msg.replied_at = now
        if msg.read_at is None:
            msg.read_at = now
            msg.status = "read"
        msg.status = "replied"
        db.add(msg)

    out = Message(
        from_agent_id=payload.from_agent_id,
        to_agent_id=payload.to_agent_id,
        message_type=payload.message_type,
        content=payload.content,
        status="pending",
    )
    db.add(out)
    db.commit()
    db.refresh(out)
    return {
        "success": True,
        "data": {
            "id": out.id,
            "from_agent_id": out.from_agent_id,
            "to_agent_id": out.to_agent_id,
            "message_type": out.message_type,
            "content": out.content,
            "status": out.status,
            "created_at": out.created_at.isoformat(),
            "marked_replied": len(to_mark),
        },
    }


@router.post("/faction/create")
def create_faction(
    payload: CreateFactionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = payload
    _ = db
    _ = current_user
    raise AppError("FEATURE_DISABLED", "Faction creation is currently disabled.", status_code=403)


@router.get("/factions")
def list_factions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    factions = db.query(Faction).order_by(Faction.id.asc()).all()
    out = []
    for faction in factions:
        member_count = db.query(Agent).filter(Agent.faction_id == faction.id).count()
        out.append(
            {
                "id": faction.id,
                "name": faction.name,
                "leader_agent_id": faction.leader_agent_id,
                "home_city": faction.home_city,
                "member_count": member_count,
                "created_at": faction.created_at.isoformat(),
            }
        )
    return {"success": True, "data": {"factions": out}}
