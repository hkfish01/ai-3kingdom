from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..errors import AppError
from ..models import City, FederationPeer, SystemState
from ..services.central_client import get_json, post_json
from ..services.roles import save_central_roles_policy

router = APIRouter(tags=["discovery"])


@router.get("/federation/status")
def federation_status_legacy():
    return {
        "success": True,
        "data": {
            "city_name": settings.city_name,
            "base_url": settings.city_base_url,
            "city_location": settings.city_location,
            "protocol_version": settings.protocol_version,
            "rule_version": settings.rule_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/federation/cities")
def federation_cities():
    db: Session = SessionLocal()
    try:
        local = db.query(City).filter(City.name == settings.city_name).first()
        peers = db.query(FederationPeer).order_by(FederationPeer.city_name.asc()).all()
        out = []
        if local:
            out.append(
                {
                    "city_name": local.name,
                    "base_url": local.base_url,
                    "city_location": settings.city_location,
                    "type": "local",
                }
            )
        out.extend(
            {
                "city_name": p.city_name,
                "base_url": p.base_url,
                "city_location": "",
                "type": "peer",
                "trust_status": p.trust_status,
            }
            for p in peers
        )
        return {"success": True, "data": {"cities": out}}
    finally:
        db.close()


@router.post("/discovery/register-central")
def register_city_to_central():
    if not settings.central_registry_url:
        raise AppError("CENTRAL_REGISTRY_CONFIG_MISSING", "Central registry URL is not configured.", status_code=422)

    payload = {
        "city_name": settings.city_name,
        "base_url": settings.city_base_url,
        "city_location": settings.city_location,
        "protocol_version": settings.protocol_version,
        "rule_version": settings.rule_version,
        "open_for_migration": settings.open_for_migration,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    status, response_payload = post_json(settings.central_registry_url, payload, settings.central_registry_token)
    db: Session = SessionLocal()
    try:
        node_id = ""
        if isinstance(response_payload, dict):
            node_id = (
                str(response_payload.get("node_id", ""))
                or str(response_payload.get("data", {}).get("node_id", ""))  # type: ignore[union-attr]
            )
        if node_id:
            state = db.get(SystemState, "central.node_id")
            if not state:
                state = SystemState(key="central.node_id", value=node_id)
            else:
                state.value = node_id
            db.add(state)
            db.commit()
    finally:
        db.close()

    return {
        "success": True,
        "data": {
            "registry_url": settings.central_registry_url,
            "upstream_status": status,
            "upstream_response": response_payload,
        },
    }


@router.post("/discovery/central/policy/roles/pull")
def pull_roles_policy_from_central():
    if not settings.central_roles_policy_url:
        raise AppError("CENTRAL_REGISTRY_CONFIG_MISSING", "Central roles policy URL is not configured.", status_code=422)

    status, payload = get_json(settings.central_roles_policy_url, settings.central_registry_token)
    roles = []
    version = "unknown"
    if isinstance(payload, dict):
        if isinstance(payload.get("roles"), list):
            roles = [str(item) for item in payload["roles"]]
            version = str(payload.get("version", "unknown"))
        elif isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("roles"), list):
            roles = [str(item) for item in payload["data"]["roles"]]
            version = str(payload["data"].get("version", "unknown"))
    if not roles:
        raise AppError("INVALID_REQUEST", "Central roles policy payload is invalid.", status_code=502)

    db: Session = SessionLocal()
    try:
        save_central_roles_policy(db, roles, version)
        db.commit()
    finally:
        db.close()

    return {
        "success": True,
        "data": {
            "policy_url": settings.central_roles_policy_url,
            "upstream_status": status,
            "roles_count": len(roles),
            "version": version,
        },
    }


@router.post("/discovery/central/heartbeat")
def send_central_heartbeat():
    if not settings.central_heartbeat_url:
        raise AppError("CENTRAL_REGISTRY_CONFIG_MISSING", "Central heartbeat URL is not configured.", status_code=422)

    db: Session = SessionLocal()
    try:
        node_state = db.get(SystemState, "central.node_id")
        effective_node_id = settings.central_node_id or (node_state.value if node_state else "")
    finally:
        db.close()

    payload = {
        "node_id": effective_node_id,
        "city_name": settings.city_name,
        "base_url": settings.city_base_url,
        "city_location": settings.city_location,
        "protocol_version": settings.protocol_version,
        "rule_version": settings.rule_version,
        "open_for_migration": settings.open_for_migration,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    status, response_payload = post_json(settings.central_heartbeat_url, payload, settings.central_registry_token)
    return {
        "success": True,
        "data": {
            "heartbeat_url": settings.central_heartbeat_url,
            "upstream_status": status,
            "upstream_response": response_payload,
        },
    }
