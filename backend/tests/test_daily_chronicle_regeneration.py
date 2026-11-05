"""當日史記重算：冪等 upsert、事件後補寫、升級前的史記自動補齊。"""

from fastapi.testclient import TestClient

from app.api.deps import get_current_admin
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Agent, ChronicleEntry, City, User
from app.services.daily_chronicle import (
    STORY_EVENT_TYPE,
    STORY_SIGNATURE_KEY,
    generate_daily_chronicle,
    get_latest_story,
    refresh_today_story_if_stale,
)
from app.services.system_state import set_state
from app.services.world_events import evaluate_world_events

client = TestClient(app)


def _seed() -> None:
    db = SessionLocal()
    try:
        db.add(
            City(
                name=settings.city_name,
                base_url="http://localhost:8000",
                treasury_gold=3398,
                treasury_food=0,
            )
        )
        user = User(
            username="regen_owner",
            email="regen_owner@example.com",
            password_hash="not-a-real-hash",
            is_admin=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.add(
            Agent(
                owner_user_id=user.id,
                name="小魚兒",
                role="平民",
                home_city=settings.city_name,
                current_city=settings.city_name,
                gold=32473,
                food=0,
                infantry=61,
            )
        )
        db.commit()
    finally:
        db.close()


def _story_rows(db):
    return db.query(ChronicleEntry).filter(ChronicleEntry.event_type == STORY_EVENT_TYPE).all()


def test_force_regeneration_updates_the_same_entry():
    _seed()
    db = SessionLocal()
    try:
        first = generate_daily_chronicle(db, lang="zh", force=True)
        assert "3,398" in "\n".join(first["lines"])
        rows = _story_rows(db)
        assert len(rows) == 1
        entry_id = rows[0].id

        city = db.query(City).first()
        city.treasury_gold = 99001
        db.commit()

        second = generate_daily_chronicle(db, lang="zh", force=True)
        assert "99,001" in "\n".join(second["lines"])
        rows = _story_rows(db)
        assert len(rows) == 1
        assert rows[0].id == entry_id
        assert rows[0].content == second["share_text"]
        assert get_latest_story(db)["share_text"] == second["share_text"]
    finally:
        db.close()


def test_refresh_is_noop_when_nothing_changed():
    _seed()
    db = SessionLocal()
    try:
        generate_daily_chronicle(db, lang="zh", force=True)
        assert refresh_today_story_if_stale(db) is None
        assert len(_story_rows(db)) == 1
    finally:
        db.close()


def test_refresh_backfills_events_opened_after_todays_story(monkeypatch):
    """今天的史記先生成、事件才開啟 —— 這是當日重算要解決的情境。"""
    _seed()
    db = SessionLocal()
    try:
        before = generate_daily_chronicle(db, lang="zh", force=True)
        assert not any("天下有事" in line for line in before["lines"])

        monkeypatch.setattr(settings, "world_events_enabled", True)
        result = evaluate_world_events(db)
        assert result["enabled"] is True
        assert result["changes"]

        refreshed = refresh_today_story_if_stale(db)
        assert refreshed is not None
        assert any("天下有事" in line for line in refreshed["lines"])
        assert get_latest_story(db)["lines"] == refreshed["lines"]
        assert len(_story_rows(db)) == 1
        assert refresh_today_story_if_stale(db) is None
    finally:
        db.close()


def test_legacy_story_without_signature_is_backfilled_once():
    """升級前生成的史記沒有簽章，部署後第一輪要自動補算，且只算一次。"""
    _seed()
    db = SessionLocal()
    try:
        generate_daily_chronicle(db, lang="zh", force=True)
        set_state(db, STORY_SIGNATURE_KEY, "")
        db.commit()

        assert refresh_today_story_if_stale(db) is not None
        assert len(_story_rows(db)) == 1
        assert refresh_today_story_if_stale(db) is None
    finally:
        db.close()


def test_refresh_skips_before_the_first_generation():
    _seed()
    db = SessionLocal()
    try:
        assert refresh_today_story_if_stale(db) is None
        assert db.query(ChronicleEntry).count() == 0
    finally:
        db.close()


def test_admin_regenerate_endpoint_is_idempotent():
    _seed()
    app.dependency_overrides[get_current_admin] = lambda: None
    try:
        first = client.post("/admin/chronicle/generate")
        second = client.post("/admin/chronicle/generate")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["data"]["headline"] == second.json()["data"]["headline"]
        db = SessionLocal()
        try:
            assert len(_story_rows(db)) == 1
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
