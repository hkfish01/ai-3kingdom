import time
from datetime import datetime, timedelta, timezone

from .api.routes_action import _process_action_event
from .config import settings
from .db import SessionLocal, engine
from .models import AgentActionEvent, Base
from .services.ai_devops import run_ai_devops_daily
from .services.daily_reset import run_daily_reset
from .services.system_state import get_state, set_state


def main() -> None:
    Base.metadata.create_all(bind=engine)

    last_devops_run = None  # 追蹤 AI DevOps 最後執行日期
    last_story_refresh_check = None  # 當日史記重算的節流時間戳記（UTC, naive）

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

            # 世界事件推進 (必須排在每日史記之前，當日事件才會被寫進史記)
            if settings.world_events_enabled:
                last_event_eval = get_state(db, "world.event.last_eval", default="")
                if last_event_eval != today and now.hour >= 1:
                    try:
                        from .services.world_events import evaluate_world_events

                        result = evaluate_world_events(db, now=now)
                        if result.get("changes"):
                            print(f"[Events] {', '.join(result['changes'])}")
                        set_state(db, "world.event.last_eval", today)
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        print(f"[Events] Evaluation failed: {e}")

            # 每日 08:00 HKT（= UTC 00:00）備妥史記圖卡與發文包。
            # 不需任何社群憑證就能跑；有 CHRONICLE_CARD_WEBHOOK_URLS 才會真的推送。
            if settings.chronicle_card_enabled:
                hkt = now.astimezone(timezone(timedelta(hours=8)))
                if hkt.hour >= settings.chronicle_card_publish_hour_hkt:
                    last_card_date = get_state(db, "chronicle_card_last_date", default="")
                    if last_card_date != hkt.date().isoformat():
                        try:
                            from .services.chronicle_publish import publish_daily_post

                            result = publish_daily_post(db, now=now)
                            print(f"[ChronicleCard] {result['status']} for {hkt.date().isoformat()}")
                        except Exception as e:
                            db.rollback()
                            print(f"[ChronicleCard] Daily post failed: {e}")

            # 每日史記 (UTC 01:00 之後的第一輪；去重存 system_state，重啟不會漏跑)
            # 這是觀戰內容的地基：即使沒有 LLM、沒有新玩家，也要有可讀的當日記事。
            last_story_date = get_state(db, "chronicle_story_last_date", default="")
            if last_story_date != today and now.hour >= 1:
                try:
                    from .services.daily_chronicle import generate_daily_chronicle

                    generate_daily_chronicle(db)
                    print(f"[Chronicle] Daily story generated for {today}")
                except Exception as e:
                    db.rollback()
                    print(f"[Chronicle] Daily story failed: {e}")

            # 當日史記重算：事件推進、捐糧、背盟或局勢數字變動後，公開觀戰不必等隔天。
            # 每 10 分鐘才檢查一次；檢查本身比對內容簽章，內容沒變就不寫入。
            now_naive = now.replace(tzinfo=None)
            if (
                last_story_refresh_check is None
                or now_naive - last_story_refresh_check >= timedelta(minutes=10)
            ):
                last_story_refresh_check = now_naive
                try:
                    from .services.daily_chronicle import refresh_today_story_if_stale

                    if refresh_today_story_if_stale(db, now=now):
                        print(f"[Chronicle] Same-day story refreshed for {today}")
                except Exception as e:
                    db.rollback()
                    print(f"[Chronicle] Same-day refresh failed: {e}")

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
