from sqlalchemy.orm import Session

from ..config import settings
from ..models import ChronicleEntry


def write_chronicle(db: Session, event_type: str, title: str, content: str, city_name: str | None = None) -> None:
    entry = ChronicleEntry(
        city_name=city_name or settings.city_name,
        event_type=event_type,
        title=title,
        content=content,
    )
    db.add(entry)
