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
