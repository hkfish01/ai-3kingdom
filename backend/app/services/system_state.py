import json

from sqlalchemy.orm import Session

from ..models import SystemState


def get_state(db: Session, key: str, default: str = "") -> str:
    row = db.query(SystemState).filter(SystemState.key == key).first()
    return row.value if row else default


def set_state(db: Session, key: str, value: str) -> None:
    row = db.query(SystemState).filter(SystemState.key == key).first()
    if not row:
        row = SystemState(key=key, value=value)
    else:
        row.value = value
    db.add(row)


def append_to_list(db: Session, list_key: str, item: str, max_size: int = 30) -> None:
    """Append an item to a JSON list stored in system_state."""
    raw = get_state(db, list_key)
    try:
        items = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        items = []
    items.insert(0, item)  # prepend (newest first)
    items = items[:max_size]
    set_state(db, list_key, json.dumps(items))


def get_list(db: Session, list_key: str) -> list[str]:
    """Get a JSON list from system_state."""
    raw = get_state(db, list_key)
    try:
        return json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return []
