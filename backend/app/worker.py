import time
from datetime import datetime, timezone

from .api.routes_action import _process_action_event
from .db import SessionLocal, engine
from .models import AgentActionEvent, Base
from .services.daily_reset import run_daily_reset
from .services.system_state import get_state, set_state


def main() -> None:
    Base.metadata.create_all(bind=engine)

    while True:
        now = datetime.now(timezone.utc)
        today = now.date().isoformat()
        db = SessionLocal()
        try:
            queued = (
                db.query(AgentActionEvent)
                .filter(AgentActionEvent.status == "queued")
                .order_by(AgentActionEvent.id.asc())
                .limit(20)
                .all()
            )
            for event in queued:
                try:
                    _process_action_event(db, event.id)
                except Exception:
                    pass

            last_reset = get_state(db, "last_daily_reset", default="")
            if last_reset != today and now.hour == 0:
                run_daily_reset(db)
                set_state(db, "last_daily_reset", today)
                db.commit()
        finally:
            db.close()

        time.sleep(30)


if __name__ == "__main__":
    main()
