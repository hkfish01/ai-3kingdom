from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable


TROOP_TYPES = ("infantry", "archer", "cavalry")


@dataclass(frozen=True)
class DungeonConfig:
    id: str
    name: str
    difficulty: int
    power_requirement: int
    reward_gold: tuple[int, int]
    reward_food: tuple[int, int]
    reward_exp: int
    enemy_troops: Dict[str, int]
    first_clear_gold: int | None = None


DUNGEONS: list[DungeonConfig] = [
    DungeonConfig(
        id="huangjin",
        name="黃巾之亂",
        difficulty=1,
        power_requirement=50,
        reward_gold=(100, 200),
        reward_food=(50, 100),
        reward_exp=80,
        enemy_troops={"infantry": 35, "archer": 10, "cavalry": 3},
        first_clear_gold=500,
    ),
    DungeonConfig(
        id="hulao",
        name="虎牢關",
        difficulty=3,
        power_requirement=200,
        reward_gold=(500, 1000),
        reward_food=(200, 500),
        reward_exp=180,
        enemy_troops={"infantry": 120, "archer": 40, "cavalry": 12},
        first_clear_gold=2000,
    ),
    DungeonConfig(
        id="chibi",
        name="赤壁之戰",
        difficulty=5,
        power_requirement=1000,
        reward_gold=(2000, 5000),
        reward_food=(1000, 2000),
        reward_exp=500,
        enemy_troops={"infantry": 380, "archer": 150, "cavalry": 60},
        first_clear_gold=10000,
    ),
]


def _dominant_troop(troops: Dict[str, int]) -> str | None:
    if not troops:
        return None
    max_type = None
    max_value = -1
    for troop in TROOP_TYPES:
        value = troops.get(troop, 0)
        if value > max_value:
            max_value = value
            max_type = troop
    if max_value <= 0:
        return None
    return max_type


def _matchup_bonus(attacker_type: str | None, defender_type: str | None) -> float:
    if not attacker_type or not defender_type:
        return 0.0
    if attacker_type == defender_type:
        return 0.0
    bonus_map = {
        ("infantry", "archer"): 0.5,
        ("archer", "cavalry"): 0.5,
        ("cavalry", "infantry"): 0.5,
        ("infantry", "cavalry"): -0.3,
        ("archer", "infantry"): -0.3,
        ("cavalry", "archer"): -0.3,
    }
    return bonus_map.get((attacker_type, defender_type), 0.0)


def base_power(troops: Dict[str, int]) -> float:
    return troops.get("infantry", 0) * 1.0 + troops.get("archer", 0) * 3.0 + troops.get("cavalry", 0) * 5.0


def leader_bonus(martial: int) -> float:
    return 1.0 + martial / 100.0


def total_power(troops: Dict[str, int], martial: int, defender_troops: Dict[str, int]) -> float:
    bonus = _matchup_bonus(_dominant_troop(troops), _dominant_troop(defender_troops))
    return base_power(troops) * leader_bonus(martial) * (1.0 + bonus)


def raw_power(troops: Dict[str, int], martial: int) -> float:
    return base_power(troops) * leader_bonus(martial)


def win_rate(attacker_power: float, defender_power: float) -> float:
    total = attacker_power + defender_power
    if total <= 0:
        return 0.5
    return attacker_power / total


def _allocate_losses(troops: Dict[str, int], total_loss: int) -> Dict[str, int]:
    total_units = sum(troops.get(t, 0) for t in TROOP_TYPES)
    if total_units <= 0 or total_loss <= 0:
        return {t: 0 for t in TROOP_TYPES}

    raw_losses = {}
    for troop in TROOP_TYPES:
        portion = troops.get(troop, 0) / total_units
        raw_losses[troop] = int(round(total_loss * portion))

    losses = {t: min(raw_losses[t], troops.get(t, 0)) for t in TROOP_TYPES}
    assigned = sum(losses.values())
    remaining = max(0, total_loss - assigned)

    if remaining:
        for troop in TROOP_TYPES:
            if remaining <= 0:
                break
            cap = troops.get(troop, 0) - losses[troop]
            if cap <= 0:
                continue
            add = min(cap, remaining)
            losses[troop] += add
            remaining -= add

    return losses


def compute_losses(
    attacker_troops: Dict[str, int],
    defender_troops: Dict[str, int],
    attacker_win: bool,
    attacker_win_rate: float,
) -> tuple[Dict[str, int], Dict[str, int]]:
    attacker_total = sum(attacker_troops.get(t, 0) for t in TROOP_TYPES)
    defender_total = sum(defender_troops.get(t, 0) for t in TROOP_TYPES)
    if attacker_total <= 0 or defender_total <= 0:
        return ({t: 0 for t in TROOP_TYPES}, {t: 0 for t in TROOP_TYPES})

    if attacker_win:
        winner_rate = attacker_win_rate
        attacker_loss_total = int(round(attacker_total * winner_rate * 0.2))
        defender_loss_total = int(round(defender_total * (1.0 - winner_rate) * 0.5))
    else:
        winner_rate = 1.0 - attacker_win_rate
        attacker_loss_total = int(round(attacker_total * (1.0 - winner_rate) * 0.5))
        defender_loss_total = int(round(defender_total * winner_rate * 0.2))

    attacker_losses = _allocate_losses(attacker_troops, attacker_loss_total)
    defender_losses = _allocate_losses(defender_troops, defender_loss_total)
    return attacker_losses, defender_losses


def clamp_troops(troops: Dict[str, int]) -> Dict[str, int]:
    return {t: max(0, int(troops.get(t, 0))) for t in TROOP_TYPES}


def troop_summary(troops: Dict[str, int]) -> Dict[str, int]:
    return {t: troops.get(t, 0) for t in TROOP_TYPES}


def is_valid_troops(troops: Dict[str, int]) -> bool:
    return sum(max(0, troops.get(t, 0)) for t in TROOP_TYPES) > 0


def list_dungeons() -> Iterable[DungeonConfig]:
    return DUNGEONS


def get_dungeon(dungeon_id: str) -> DungeonConfig | None:
    for dungeon in DUNGEONS:
        if dungeon.id == dungeon_id:
            return dungeon
    return None
