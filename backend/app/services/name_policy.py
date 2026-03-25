from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def approved_names() -> set[str]:
    path = Path(__file__).resolve().parent.parent / "references" / "three_kingdoms_names.txt"
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def is_approved_name(name: str) -> bool:
    return name in approved_names()
