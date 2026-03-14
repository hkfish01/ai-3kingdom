from sqlalchemy.orm import Session

from ..config import settings
from ..models import Agent
from ..rules import DAILY_ENERGY, TROOP_TYPES
from .chronicle import write_chronicle
from .positions import DAILY_AGENT_FOOD_CONSUMPTION


def run_daily_reset(db: Session) -> dict:
    agents = db.query(Agent).all()
    upkeep_total = 0
    base_food_total = 0

    for agent in agents:
        upkeep = (
            agent.infantry * TROOP_TYPES["infantry"]["daily_food"]
            + agent.archer * TROOP_TYPES["archer"]["daily_food"]
            + agent.cavalry * TROOP_TYPES["cavalry"]["daily_food"]
        )
        upkeep_total += upkeep
        base_food_total += DAILY_AGENT_FOOD_CONSUMPTION
        agent.food = max(0, agent.food - upkeep - DAILY_AGENT_FOOD_CONSUMPTION)
        agent.energy = DAILY_ENERGY
        db.add(agent)

    write_chronicle(
        db,
        event_type="daily_reset",
        title=f"{settings.city_name} daily reset completed",
        content=(
            f"Energy reset for {len(agents)} agents. "
            f"Base food upkeep: {base_food_total}. Troop upkeep food: {upkeep_total}."
        ),
    )
    db.commit()
    return {
        "agents_reset": len(agents),
        "base_food_upkeep": base_food_total,
        "total_food_upkeep": upkeep_total,
    }
