from math import log

DAILY_ENERGY = 100
CITY_TAX_RATE = 0.05
LORD_TAX_RATE = 0.1

WORK_TASKS = {
    "farm": {"energy": 10, "gold": 0, "food": 40},
    "irrigation": {"energy": 15, "gold": 0, "food": 70},
    "expand_land": {"energy": 20, "gold": 0, "food": 120},
    "tax": {"energy": 10, "gold": 50, "food": 0},
    "trade": {"energy": 10, "gold": 80, "food": 0},
    "market": {"energy": 15, "gold": 120, "food": 0},
    "storage": {"energy": 5, "gold": 0, "food": 10},
    "patrol": {"energy": 10, "gold": 20, "food": 0},
    "build": {"energy": 15, "gold": 60, "food": 0},
    "research": {"energy": 20, "gold": 150, "food": 0},
}

TROOP_TYPES = {
    "infantry": {"gold": 10, "food": 5, "daily_food": 1, "power": 1.0},
    "archer": {"gold": 20, "food": 8, "daily_food": 1, "power": 1.3},
    "cavalry": {"gold": 40, "food": 15, "daily_food": 2, "power": 2.0},
}


def compute_power(infantry: int, archer: int, cavalry: int) -> float:
    return infantry * 1.0 + archer * 1.3 + cavalry * 2.0


def prosperity(agent_count: int) -> float:
    return log(agent_count + 1)


def city_defense_power(city_wall: int, troop_power: float, city_prosperity: float) -> float:
    return city_wall + troop_power + city_prosperity * 20
