import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import SystemState
from ..services.roles import get_effective_allowed_roles

router = APIRouter(tags=["central"])


def _upsert_state(db: Session, key: str, value: str) -> None:
    row = db.get(SystemState, key)
    if not row:
        row = SystemState(key=key, value=value)
    else:
        row.value = value
    db.add(row)


@router.post("/registry/cities/register")
def central_register_city(payload: dict, db: Session = Depends(get_db)):
    city_name = str(payload.get("city_name", "unknown-city"))
    base_url = str(payload.get("base_url", ""))
    node_id = f"local-{city_name}-{uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    compact = {
        "node_id": node_id,
        "city_name": city_name,
        "base_url": base_url,
        "registered_at": now,
    }
    _upsert_state(db, f"central.registry.city.{city_name}", json.dumps(compact, ensure_ascii=False))
    db.commit()

    return {
        "success": True,
        "node_id": node_id,
        "data": {"node_id": node_id, "status": "registered", "timestamp": now},
    }


@router.post("/registry/nodes/heartbeat")
def central_heartbeat(payload: dict, db: Session = Depends(get_db)):
    node_id = str(payload.get("node_id", "")).strip()
    city_name = str(payload.get("city_name", "unknown-city"))
    key = f"central.heartbeat.{node_id or city_name}"
    now = datetime.now(timezone.utc).isoformat()
    compact = {
        "node_id": node_id,
        "city_name": city_name,
        "timestamp": str(payload.get("timestamp", now)),
        "received_at": now,
    }
    _upsert_state(db, key, json.dumps(compact, ensure_ascii=False))
    db.commit()
    return {"success": True, "data": {"status": "ok", "node_id": node_id, "timestamp": now}}


@router.get("/policy/roles")
def central_roles_policy(db: Session = Depends(get_db)):
    # Keep payload intentionally small so it can be cached in SystemState.value (varchar 255).
    roles = get_effective_allowed_roles(db)[:6]
    return {"success": True, "roles": roles, "version": "local-dev-central-v1"}
