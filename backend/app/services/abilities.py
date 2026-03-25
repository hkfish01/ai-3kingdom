import secrets


def roll_stat() -> int:
    return secrets.randbelow(50) + 50


def roll_abilities() -> dict[str, int]:
    return {
        "martial": roll_stat(),
        "intelligence": roll_stat(),
        "charisma": roll_stat(),
        "politics": roll_stat(),
    }
