import time
from datetime import datetime, timezone

from .api.routes_action import _process_action_event
from .db import SessionLocal, engine
from .models import AgentActionEvent, Base
from .services.ai_devops import run_ai_devops_daily
from .services.daily_reset import run_daily_reset
from .services.system_state import get_state, set_state


def main() -> None:
    Base.metadata.create_all(bind=engine)

    last_devops_run = None  # 追蹤 AI DevOps 最後執行日期

    while True:
        now = datetime.now(timezone.utc)
        today = now.date().isoformat()
        db = SessionLocal()
        try:
            # 處理排隊中的 action events
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

            # 每日重置 (凌晨 0 點)
            last_reset = get_state(db, "last_daily_reset", default="")
            if last_reset != today and now.hour == 0:
                run_daily_reset(db)
                set_state(db, "last_daily_reset", today)
                db.commit()

            # AI DevOps 每日檢查 (凌晨 2 點，低流量時段)
            if last_devops_run != today and now.hour == 2:
                try:
                    import asyncio
                    report = asyncio.run(run_ai_devops_daily(db))
                    last_devops_run = today
                    # 將報告寫入 chronicle 供管理員查看
                    from .services.chronicle import write_chronicle
                    write_chronicle(
                        db,
                        event_type="ai_devops_report",
                        title=f"AI DevOps Daily Report: {report['summary']}",
                        content=f"Report ID: {report['report_id']}\n"
                               f"Health Status: {report['health']['status']}\n"
                               f"Balance Issues: {len(report['game_analysis']['balance_issues'])}\n"
                               f"Economy Issues: {len(report['game_analysis']['economy_issues'])}\n"
                               f"Planned Features: {len(report['planned_features'])}\n\n"
                               f"Full report: check system_state devops_report_{report['report_id']}",
                    )
                    db.commit()
                    print(f"[AI DevOps] Daily check completed: {report['summary']}")
                except Exception as e:
                    print(f"[AI DevOps] Daily check failed: {e}")

        finally:
            db.close()

        time.sleep(30)


if __name__ == "__main__":
    main()
