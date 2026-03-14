import time
from datetime import datetime, timezone

from .db import SessionLocal, engine
from .models import Base
from .services.daily_reset import run_daily_reset
from .services.system_state import get_state, set_state


def main() -> None:
    Base.metadata.create_all(bind=engine)

    while True:
        now = datetime.now(timezone.utc)
        today = now.date().isoformat()
        db = SessionLocal()
        try:
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
