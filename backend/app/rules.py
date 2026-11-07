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

# 商城（超市）：用金幣換取糧食與體力，讓缺糧的諸侯有自救的入口。
# 不消耗能量——否則糧荒 + 能量耗盡會互相鎖死，購買就失去止血效果。
MARKET_ITEMS = {
    "grain_bag": {
        "gold": 30, "food": 40, "energy": 0,
        "name_zh": "糧袋", "name_en": "Grain bag",
        "desc_zh": "一小袋軍糧，夠撑過一日基本消耗。",
        "desc_en": "A small sack of grain, enough for one quiet day.",
    },
    "grain_cart": {
        "gold": 80, "food": 120, "energy": 0,
        "name_zh": "糧車", "name_en": "Grain cart",
        "desc_zh": "整車軍糧，適合要養兵的諸侯。",
        "desc_en": "A full cart of grain for a warlord with troops to feed.",
    },
    "grain_convoy": {
        "gold": 150, "food": 250, "energy": 0,
        "name_zh": "糧隊", "name_en": "Grain convoy",
        "desc_zh": "大批糧秣，一次備妥數日軍需。",
        "desc_en": "A convoy of supplies, several days of upkeep in one purchase.",
    },
    "energy_tonic": {
        "gold": 40, "food": 0, "energy": 30,
        "name_zh": "提神湯藥", "name_en": "Energy tonic",
        "desc_zh": "立刻回復 30 點體力；體力每日仍會重置。",
        "desc_en": "Restores 30 energy immediately; energy still resets daily.",
    },
}

MARKET_BUY_ACTION = "buy"
MARKET_MAX_QUANTITY = 20

# 尋訪（尋寶／尋人才）：agent 自選「禮金」與「尋訪重心」出城，帶回人才、物資，
# 或空手而歸。這也是金幣的主要出口——榜首諸侯已有數萬金，商城單次最多 3000 金
# 仍不成比例。結果由伺服器秘密 + agent/日期/次數雜湊決定，不可預測也不可指定。
SCOUT_ACTION = "scout"
SCOUT_ENERGY_COST = 20
SCOUT_DAILY_LIMIT = 3
SCOUT_ABILITY_CAP = 99
SCOUT_FOCUS = ("balanced", "talent", "supply")
SCOUT_FOCUS_BONUS = 0.20
SCOUT_BUDGETS = {
    100: {
        "talent_chance": 0.35, "supply_chance": 0.40, "ability_gain": 1,
        "reputation": (5, 12), "food": (30, 60), "gold_back": (20, 40),
    },
    500: {
        "talent_chance": 0.50, "supply_chance": 0.40, "ability_gain": 2,
        "reputation": (25, 60), "food": (120, 250), "gold_back": (100, 200),
    },
    2000: {
        "talent_chance": 0.65, "supply_chance": 0.30, "ability_gain": 3,
        "reputation": (100, 240), "food": (400, 700), "gold_back": (300, 600),
    },
}
SCOUT_ABILITY_NAMES = {
    "martial": ("武藝", "Martial"),
    "intelligence": ("智略", "Intelligence"),
    "charisma": ("魅力", "Charisma"),
    "politics": ("治才", "Politics"),
}
SCOUT_TALENT_TITLES = {
    "martial": ("猛將", "a fierce general"),
    "intelligence": ("策士", "a strategist"),
    "charisma": ("說客", "a silver-tongued envoy"),
    "politics": ("治才", "a gifted administrator"),
}

# bootstrap / 建立 API key 時的舊預設白名單。商城是新動作，舊 key 裡沒有它；
# 若不向後相容，所有已在運行的 agent 都會被 ACTION_NOT_ALLOWED 擋在門外。
LEGACY_ALLOWED_ACTIONS = {"farm", "trade", "move"}
# 只對「舊預設白名單」自動放行這些後來新增的基礎動作；
# 使用者自訂的白名單仍嚴格執行，不被悄悄放寬。
COMPAT_ALLOWED_ACTIONS = {MARKET_BUY_ACTION, SCOUT_ACTION}


def compute_power(infantry: int, archer: int, cavalry: int) -> float:
    return infantry * 1.0 + archer * 1.3 + cavalry * 2.0


def prosperity(agent_count: int) -> float:
    return log(agent_count + 1)


def city_defense_power(city_wall: int, troop_power: float, city_prosperity: float) -> float:
    return city_wall + troop_power + city_prosperity * 20
