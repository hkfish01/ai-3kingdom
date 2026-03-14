from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..api.deps import get_current_user
from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import BattleLog, City, FederationPeer, MigrationLog, User

router = APIRouter(prefix="/city", tags=["city"])


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


@router.get("/status")
def city_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _ = current_user
    city = _get_or_create_local_city(db)
    return {
        "success": True,
        "data": {
            "name": city.name,
            "base_url": city.base_url,
            "prosperity": city.prosperity,
            "city_wall": city.city_wall,
            "city_tax_rate": city.city_tax_rate,
            "treasury_gold": city.treasury_gold,
            "treasury_food": city.treasury_food,
            "status": city.status,
            "protocol_version": city.protocol_version,
            "rule_version": city.rule_version,
            "open_for_migration": city.open_for_migration,
        },
    }


@router.get("/battles")
def city_battles(limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _ = current_user
    logs = (
        db.query(BattleLog)
        .filter((BattleLog.attacker_city == settings.city_name) | (BattleLog.defender_city == settings.city_name))
        .order_by(BattleLog.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return {
        "success": True,
        "data": {
            "battles": [
                {
                    "id": b.id,
                    "attacker_city": b.attacker_city,
                    "defender_city": b.defender_city,
                    "attack_power": b.attack_power,
                    "defense_power": b.defense_power,
                    "outcome": b.outcome,
                    "loot_gold": b.loot_gold,
                    "loot_food": b.loot_food,
                    "request_id": b.request_id,
                    "created_at": b.created_at.isoformat(),
                }
                for b in logs
            ]
        },
    }


@router.get("/migrations")
def city_migrations(limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _ = current_user
    logs = db.query(MigrationLog).order_by(MigrationLog.id.desc()).limit(max(1, min(limit, 200))).all()
    return {
        "success": True,
        "data": {
            "migrations": [
                {
                    "id": m.id,
                    "agent_id": m.agent_id,
                    "agent_name": m.agent_name,
                    "from_city": m.from_city,
                    "to_city": m.to_city,
                    "status": m.status,
                    "details": m.details,
                    "created_at": m.created_at.isoformat(),
                }
                for m in logs
            ]
        },
    }


@router.post("/peer/{city_name}/trust")
def set_peer_trust(
    city_name: str,
    trust_status: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    if trust_status not in {"trusted", "blocked", "neutral"}:
        raise AppError("INVALID_REQUEST", "trust_status must be trusted|blocked|neutral", status_code=422)
    peer = db.query(FederationPeer).filter(FederationPeer.city_name == city_name).first()
    if not peer:
        raise AppError("CITY_NOT_FOUND", "The specified city does not exist.", status_code=404)

    peer.trust_status = trust_status
    db.add(peer)
    db.commit()

    return {"success": True, "data": {"city_name": city_name, "trust_status": trust_status}}
