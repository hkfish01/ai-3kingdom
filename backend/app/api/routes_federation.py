from datetime import datetime, timezone

from fastapi import APIRouter, Header
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..errors import AppError
from ..models import Agent, BattleLog, City, FederationPeer, MigrationLog, User
from ..rules import compute_power, prosperity
from ..schemas import (
    FederationAttackRequest,
    FederationHelloRequest,
    FederationMessageRequest,
    FederationMigrateRequest,
)
from ..services.chronicle import write_chronicle
from ..services.federation_security import assert_federation_request, verify_signature
from ..services.abilities import roll_abilities
from ..services.positions import get_position, has_slot_limit, role_max_slots
from ..services.roles import is_allowed_role

router = APIRouter(prefix="/federation/v1", tags=["federation"])


def _get_db() -> Session:
    db = SessionLocal()
    return db


def _get_or_create_local_city(db: Session) -> City:
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


def _verify_federation_headers(
    db: Session,
    source_city: str,
    body: dict,
    signature: str | None,
    timestamp: str | None,
    nonce: str | None,
):
    if not signature or not timestamp or not nonce:
        raise AppError("FEDERATION_UNAUTHORIZED", "Missing federation auth headers.", status_code=401)

    peer = db.query(FederationPeer).filter(FederationPeer.city_name == source_city).first()
    if peer and peer.trust_status == "blocked":
        raise AppError("FORBIDDEN", "Source city is blocked.", status_code=403)
    shared_secret = peer.shared_secret if peer and peer.shared_secret else settings.federation_shared_secret

    ok = verify_signature(shared_secret, timestamp, nonce, body, signature)
    if not ok:
        raise AppError("FEDERATION_UNAUTHORIZED", "Federation signature verification failed.", status_code=401)


@router.get("/status")
def federation_status():
    db = _get_db()
    try:
        local_city = _get_or_create_local_city(db)
        agent_count = db.query(func.count(Agent.id)).filter(Agent.current_city == settings.city_name).scalar() or 0
        city_prosperity = round(prosperity(agent_count), 4)
        local_city.prosperity = city_prosperity
        db.add(local_city)
        db.commit()
        return {
            "success": True,
            "data": {
                "protocol_version": settings.protocol_version,
                "rule_version": settings.rule_version,
                "city_name": settings.city_name,
                "city_location": settings.city_location,
                "base_url": settings.city_base_url,
                "public_key": local_city.public_key,
                "agent_count": agent_count,
                "prosperity": city_prosperity,
                "open_for_migration": settings.open_for_migration,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
    finally:
        db.close()


@router.post("/hello")
def federation_hello(
    payload: FederationHelloRequest,
    x_fed_signature: str | None = Header(default=None, alias="X-Fed-Signature"),
    x_fed_timestamp: str | None = Header(default=None, alias="X-Fed-Timestamp"),
    x_fed_nonce: str | None = Header(default=None, alias="X-Fed-Nonce"),
):
    db = _get_db()
    try:
        _verify_federation_headers(
            db,
            payload.city_name,
            payload.model_dump(),
            x_fed_signature,
            x_fed_timestamp,
            x_fed_nonce,
        )
        assert_federation_request(
            db,
            source_city=payload.city_name,
            request_type="hello",
            request_id=payload.request_id,
            timestamp=x_fed_timestamp or "",
        )

        peer = db.query(FederationPeer).filter(FederationPeer.city_name == payload.city_name).first()
        if not peer:
            peer = FederationPeer(
                city_name=payload.city_name,
                base_url=payload.base_url,
                public_key=payload.public_key,
                shared_secret=payload.shared_secret or settings.federation_shared_secret,
                protocol_version=payload.protocol_version,
                rule_version=payload.rule_version,
            )
        else:
            peer.base_url = payload.base_url
            peer.public_key = payload.public_key
            if payload.shared_secret:
                peer.shared_secret = payload.shared_secret
            peer.protocol_version = payload.protocol_version
            peer.rule_version = payload.rule_version
            peer.last_seen_at = datetime.now(timezone.utc)

        db.add(peer)
        write_chronicle(
            db,
            event_type="federation",
            title=f"Peer connected: {payload.city_name}",
            content=f"Registered peer {payload.city_name} at {payload.base_url}.",
        )
        db.commit()

        return {
            "success": True,
            "data": {
                "status": "connected",
                "peer_city": peer.city_name,
                "protocol_version": settings.protocol_version,
            },
        }
    finally:
        db.close()


@router.post("/message")
def federation_message(
    payload: FederationMessageRequest,
    x_fed_signature: str | None = Header(default=None, alias="X-Fed-Signature"),
    x_fed_timestamp: str | None = Header(default=None, alias="X-Fed-Timestamp"),
    x_fed_nonce: str | None = Header(default=None, alias="X-Fed-Nonce"),
):
    db = _get_db()
    try:
        _verify_federation_headers(
            db,
            payload.from_city,
            payload.model_dump(),
            x_fed_signature,
            x_fed_timestamp,
            x_fed_nonce,
        )
        assert_federation_request(
            db,
            source_city=payload.from_city,
            request_type="message",
            request_id=payload.request_id,
            timestamp=x_fed_timestamp or "",
        )
        write_chronicle(
            db,
            event_type="federation",
            title=f"Federation message from {payload.from_city}",
            content=payload.content,
        )
        db.commit()
        return {"success": True, "data": {"status": "delivered", "request_id": payload.request_id}}
    finally:
        db.close()


@router.post("/attack")
def federation_attack(
    payload: FederationAttackRequest,
    x_fed_signature: str | None = Header(default=None, alias="X-Fed-Signature"),
    x_fed_timestamp: str | None = Header(default=None, alias="X-Fed-Timestamp"),
    x_fed_nonce: str | None = Header(default=None, alias="X-Fed-Nonce"),
):
    db = _get_db()
    try:
        _verify_federation_headers(
            db,
            payload.from_city,
            payload.model_dump(),
            x_fed_signature,
            x_fed_timestamp,
            x_fed_nonce,
        )
        assert_federation_request(
            db,
            source_city=payload.from_city,
            request_type="attack",
            request_id=payload.request_id,
            timestamp=x_fed_timestamp or "",
        )

        local_city = _get_or_create_local_city(db)
        if payload.target_city != settings.city_name:
            raise AppError("INVALID_REQUEST", "Attack target city mismatch.", status_code=422)

        agent_count = db.query(func.count(Agent.id)).filter(Agent.current_city == settings.city_name).scalar() or 0
        local_prosperity = prosperity(agent_count)
        defender_troop_power = (
            db.query(func.coalesce(func.sum(Agent.infantry * 1.0 + Agent.archer * 1.3 + Agent.cavalry * 2.0), 0.0))
            .filter(Agent.current_city == settings.city_name)
            .scalar()
            or 0.0
        )
        defense_power = local_city.city_wall + defender_troop_power + local_prosperity * 20
        attack_power = compute_power(payload.troops.infantry, payload.troops.archer, payload.troops.cavalry)

        outcome = "defender_win"
        loot_gold = 0
        loot_food = 0
        if attack_power > defense_power:
            outcome = "attacker_win"
            loot_gold = int(local_city.treasury_gold * 0.2)
            loot_food = int(local_city.treasury_food * 0.2)
            local_city.treasury_gold -= loot_gold
            local_city.treasury_food -= loot_food

        db.add(
            BattleLog(
                attacker_city=payload.from_city,
                defender_city=payload.target_city,
                attack_power=attack_power,
                defense_power=defense_power,
                outcome=outcome,
                loot_gold=loot_gold,
                loot_food=loot_food,
                request_id=payload.request_id,
            )
        )
        db.add(local_city)
        write_chronicle(
            db,
            event_type="federation_battle",
            title=f"{payload.from_city} attacked {payload.target_city}",
            content=f"Outcome: {outcome}. loot_gold={loot_gold}, loot_food={loot_food}",
        )
        db.commit()

        return {
            "success": True,
            "data": {
                "request_id": payload.request_id,
                "outcome": outcome,
                "attack_power": round(attack_power, 4),
                "defense_power": round(defense_power, 4),
                "loot_gold": loot_gold,
                "loot_food": loot_food,
            },
        }
    finally:
        db.close()


@router.post("/migrate")
def federation_migrate(
    payload: FederationMigrateRequest,
    x_fed_signature: str | None = Header(default=None, alias="X-Fed-Signature"),
    x_fed_timestamp: str | None = Header(default=None, alias="X-Fed-Timestamp"),
    x_fed_nonce: str | None = Header(default=None, alias="X-Fed-Nonce"),
):
    db = _get_db()
    try:
        if not settings.open_for_migration:
            raise AppError("FORBIDDEN", "City is closed for migration.", status_code=403)
        if payload.to_city != settings.city_name:
            raise AppError("INVALID_REQUEST", "Migration target city mismatch.", status_code=422)
        if not is_allowed_role(db, payload.role):
            raise AppError("INVALID_ROLE", "The role is not allowed.", status_code=422)

        _verify_federation_headers(
            db,
            payload.from_city,
            payload.model_dump(),
            x_fed_signature,
            x_fed_timestamp,
            x_fed_nonce,
        )
        assert_federation_request(
            db,
            source_city=payload.from_city,
            request_type="migrate",
            request_id=payload.request_id,
            timestamp=x_fed_timestamp or "",
        )
        pos = get_position(payload.role)
        limit = role_max_slots(pos.name_zh)
        if has_slot_limit(pos.name_zh) and limit is not None:
            occupied = (
                db.query(func.count(Agent.id))
                .filter(Agent.current_city == payload.to_city, Agent.role == pos.name_zh)
                .scalar()
                or 0
            )
            if occupied >= limit:
                raise AppError(
                    "ROLE_SLOTS_FULL",
                    f"Role {pos.name_zh} has reached slot limit ({limit}).",
                    status_code=422,
                )

        # Imported agents are managed by system user id 1 by default.
        system_user = db.query(User).filter(User.id == 1).first()
        if not system_user:
            system_user = User(
                username="federation-system",
                email="federation-system@local.invalid",
                password_hash="disabled",
                is_admin=False,
            )
            db.add(system_user)
            db.commit()
            db.refresh(system_user)

        abilities = roll_abilities()
        imported = Agent(
            owner_user_id=system_user.id,
            name=payload.agent_name,
            role=payload.role,
            home_city=payload.from_city,
            current_city=payload.to_city,
            gold=payload.gold,
            food=payload.food,
            infantry=payload.infantry,
            archer=payload.archer,
            cavalry=payload.cavalry,
            reputation=payload.reputation,
            martial=abilities["martial"],
            intelligence=abilities["intelligence"],
            charisma=abilities["charisma"],
            politics=abilities["politics"],
        )
        db.add(imported)
        db.flush()

        db.add(
            MigrationLog(
                agent_id=imported.id,
                agent_name=payload.agent_name,
                from_city=payload.from_city,
                to_city=payload.to_city,
                status="completed",
                details=f"Imported via federation request {payload.request_id}",
            )
        )
        write_chronicle(
            db,
            event_type="migration",
            title=f"{payload.agent_name} migrated from {payload.from_city}",
            content=f"Role={payload.role}, reputation={payload.reputation}",
        )
        db.commit()

        return {
            "success": True,
            "data": {
                "status": "accepted",
                "request_id": payload.request_id,
                "agent_id": imported.id,
                "agent_name": imported.name,
                "current_city": imported.current_city,
            },
        }
    finally:
        db.close()


@router.get("/peers")
def federation_peers():
    db = _get_db()
    try:
        peers = db.query(FederationPeer).order_by(FederationPeer.city_name.asc()).all()
        return {
            "success": True,
            "data": {
                "peers": [
                    {
                        "city_name": p.city_name,
                        "base_url": p.base_url,
                        "trust_status": p.trust_status,
                        "protocol_version": p.protocol_version,
                        "rule_version": p.rule_version,
                        "last_seen_at": p.last_seen_at.isoformat(),
                    }
                    for p in peers
                ]
            },
        }
    finally:
        db.close()
