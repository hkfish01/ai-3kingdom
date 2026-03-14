from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..api.deps import get_current_user
from ..config import settings
from ..db import get_db
from ..models import Agent, Announcement, ChronicleEntry, City, Faction, User
from ..rules import DAILY_ENERGY, TROOP_TYPES, WORK_TASKS, city_defense_power, prosperity
from ..services.chronicle_i18n import WORK_TASK_ZH, localize_event_type, localize_text, localize_work_task
from ..services.positions import civil_hierarchy, get_position, military_hierarchy, role_max_slots
from ..services.roles import get_effective_allowed_roles

router = APIRouter(prefix="/world", tags=["world"])


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


def _build_world_state_payload(db: Session) -> dict:
    local_city = _get_or_create_local_city(db)
    agent_count = db.query(func.count(Agent.id)).filter(Agent.current_city == settings.city_name).scalar() or 0
    local_troop_power = (
        db.query(func.coalesce(func.sum(Agent.infantry * 1.0 + Agent.archer * 1.3 + Agent.cavalry * 2.0), 0.0))
        .filter(Agent.current_city == settings.city_name)
        .scalar()
        or 0.0
    )
    city_prosperity = round(prosperity(agent_count), 4)
    local_city.prosperity = city_prosperity
    db.add(local_city)
    db.commit()

    return {
        "city": settings.city_name,
        "city_location": settings.city_location,
        "agent_count": agent_count,
        "prosperity": city_prosperity,
        "city_wall": local_city.city_wall,
        "defense_power": round(city_defense_power(local_city.city_wall, local_troop_power, city_prosperity), 4),
        "treasury": {"gold": local_city.treasury_gold, "food": local_city.treasury_food},
        "available_work_tasks": list(WORK_TASKS.keys()),
        "available_work_tasks_zh": {k: localize_work_task(k, "zh") for k in WORK_TASKS},
    }


def _build_rankings_payload(db: Session) -> dict:
    top_agents = db.query(Agent).order_by(Agent.gold.desc()).limit(10).all()
    top_factions = (
        db.query(Faction.name, func.count(Agent.id).label("members"))
        .outerjoin(Agent, Agent.faction_id == Faction.id)
        .group_by(Faction.id, Faction.name)
        .order_by(func.count(Agent.id).desc())
        .limit(10)
        .all()
    )
    top_cities = db.query(City).order_by(City.prosperity.desc()).limit(10).all()

    return {
        "top_agents_by_gold": [
            {
                "agent_id": a.id,
                "name": a.name,
                "gold": a.gold,
                "food": a.food,
                "home_city": a.home_city,
            }
            for a in top_agents
        ],
        "top_factions_by_members": [{"name": name, "members": members} for name, members in top_factions],
        "top_cities_by_prosperity": [
            {"name": c.name, "prosperity": c.prosperity, "agent_tax_rate": c.city_tax_rate} for c in top_cities
        ],
    }


@router.get("/manifest")
def manifest(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _ = current_user
    return {
        "success": True,
        "data": {
            "world_name": settings.world_name,
            "city_name": settings.city_name,
            "city_location": settings.city_location,
            "daily_energy": DAILY_ENERGY,
            "reset_time": "UTC 00:00",
            "available_actions": ["work", "train", "join_lord", "recruit_vassal", "attack", "message"],
            "supported_roles": get_effective_allowed_roles(db),
            "protocol_version": settings.protocol_version,
            "rule_version": settings.rule_version,
        },
    }


@router.get("/rules")
def rules_endpoint(current_user: User = Depends(get_current_user)):
    _ = current_user
    return {
        "success": True,
        "data": {
            "daily_energy": DAILY_ENERGY,
            "city_tax_rate": settings.city_tax_rate,
            "work_tasks": WORK_TASKS,
            "work_tasks_zh": WORK_TASK_ZH,
            "troop_types": TROOP_TYPES,
            "battle_loot_ratio": {"gold": 0.3, "food": 0.3},
            "rule_version": settings.rule_version,
        },
    }


@router.get("/state")
def state(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _ = current_user
    return {"success": True, "data": _build_world_state_payload(db)}


@router.get("/rankings")
def rankings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _ = current_user
    return {"success": True, "data": _build_rankings_payload(db)}


@router.get("/public/state")
def public_state(db: Session = Depends(get_db)):
    return {"success": True, "data": _build_world_state_payload(db)}


@router.get("/public/rankings")
def public_rankings(db: Session = Depends(get_db)):
    return {"success": True, "data": _build_rankings_payload(db)}


@router.get("/public/announcements")
def public_announcements(db: Session = Depends(get_db)):
    rows = (
        db.query(Announcement)
        .filter(Announcement.published.is_(True))
        .order_by(Announcement.id.desc())
        .limit(30)
        .all()
    )
    return {
        "success": True,
        "data": {
            "items": [
                {
                    "id": a.id,
                    "title": a.title,
                    "content": a.content,
                    "published": a.published,
                    "created_at": a.created_at.isoformat(),
                    "updated_at": a.updated_at.isoformat(),
                }
                for a in rows
            ]
        },
    }


@router.get("/city/roster")
def city_roster(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _ = current_user
    agents = (
        db.query(Agent)
        .filter(Agent.current_city == settings.city_name)
        .order_by(Agent.gold.desc(), Agent.id.asc())
        .all()
    )
    role_counts: dict[str, int] = {}
    for a in agents:
        role_counts[a.role] = role_counts.get(a.role, 0) + 1
    return {
        "success": True,
        "data": {
            "city_name": settings.city_name,
            "city_location": settings.city_location,
            "civil_hierarchy": civil_hierarchy("zh"),
            "military_hierarchy": military_hierarchy("zh"),
            "role_slots": [
                {
                    "role": role,
                    "occupied": count,
                    "max_slots": role_max_slots(role),
                }
                for role, count in sorted(role_counts.items(), key=lambda x: (-x[1], x[0]))
            ],
            "agents": [
                {
                    "id": a.id,
                    "name": a.name,
                    "role": a.role,
                    "branch": get_position(a.role).branch,
                    "tier": get_position(a.role).tier,
                    "bonus": get_position(a.role).bonus,
                    "energy": a.energy,
                    "gold": a.gold,
                    "food": a.food,
                    "abilities": {
                        "martial": a.martial,
                        "intelligence": a.intelligence,
                        "charisma": a.charisma,
                        "politics": a.politics,
                    },
                    "faction_id": a.faction_id,
                }
                for a in agents
            ],
        },
    }


@router.get("/chronicle")
def chronicle(
    limit: int = 50,
    lang: str = "en",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    lang = "zh" if lang == "zh" else "en"
    entries = (
        db.query(ChronicleEntry)
        .filter(ChronicleEntry.city_name == settings.city_name)
        .order_by(ChronicleEntry.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return {
        "success": True,
        "data": {
            "entries": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "event_type_localized": localize_event_type(e.event_type, lang),
                    "title": e.title,
                    "title_localized": localize_text(e.title, lang),
                    "content": e.content,
                    "content_localized": localize_text(e.content, lang),
                    "created_at": e.created_at.isoformat(),
                }
                for e in entries
            ]
        },
    }
