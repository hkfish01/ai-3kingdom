"""每日史記敘事層測試：公開性、內容正確性、冪等性與 skill.md 改造。"""

from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Agent, ChronicleEntry, City, User
from app.services.daily_chronicle import (
    STORY_EVENT_TYPE,
    build_story,
    collect_daily_facts,
    generate_daily_chronicle,
    get_latest_story,
)

client = TestClient(app)


def _seed_world():
    db = SessionLocal()
    try:
        city = City(
            name=settings.city_name,
            base_url="http://localhost:8000",
            treasury_gold=3398,
            treasury_food=0,
        )
        db.add(city)
        user = User(
            username="chronicle_owner",
            email="chronicle_owner@example.com",
            password_hash="not-a-real-hash",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        agent = Agent(
            owner_user_id=user.id,
            name="小魚兒",
            role="平民",
            home_city=settings.city_name,
            current_city=settings.city_name,
            gold=32473,
            food=0,
            infantry=61,
        )
        db.add(agent)
        db.commit()
    finally:
        db.close()


def test_public_chronicle_requires_no_token():
    _seed_world()
    resp = client.get("/world/public/chronicle?lang=zh")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["story"] is not None
    assert "史記" in data["story"]["headline"]
    assert data["story"]["aphorism"]
    assert isinstance(data["entries"], list)


def test_story_is_grounded_in_real_facts():
    _seed_world()
    db = SessionLocal()
    try:
        facts = collect_daily_facts(db)
        story = build_story(facts, lang="zh")
    finally:
        db.close()

    assert facts["treasury_food"] == 0
    assert "小魚兒" in "\n".join(story["lines"])
    assert story["aphorism"] == "金滿倉，倉無糧；兵未滿百，已言天下。"
    assert "史官曰：" in story["share_text"]
    assert settings.public_site_url in story["share_text"]


def test_generate_writes_once_and_is_idempotent():
    _seed_world()
    db = SessionLocal()
    try:
        story = generate_daily_chronicle(db, lang="zh", force=True)
        assert story["headline"]
        assert get_latest_story(db) is not None
        first_count = db.query(ChronicleEntry).filter(
            ChronicleEntry.event_type == STORY_EVENT_TYPE
        ).count()
        assert first_count == 1

        generate_daily_chronicle(db, lang="zh", force=False)
        second_count = db.query(ChronicleEntry).filter(
            ChronicleEntry.event_type == STORY_EVENT_TYPE
        ).count()
        assert second_count == 1
    finally:
        db.close()


def test_skill_md_injects_situation_and_drops_decision_tree():
    _seed_world()
    resp = client.get("/skill.md?lang=zh")
    assert resp.status_code == 200
    text = resp.text
    assert "本週局勢" in text
    assert "soul.md" in text
    assert "城中現有" in text
    assert "不要照抄" in text
    # 決策樹本體與 Python 範例已搬到 reference.md，skill.md 只剩「禁止照抄」的提醒
    assert "體力 < 20" not in text
    assert "```python" not in text
    assert "{{WEEKLY_SITUATION}}" not in text

    reference = client.get("/reference.md")
    assert reference.status_code == 200
    assert "決策樹" in reference.text
    assert "僅為理解用" in reference.text


def test_admin_chronicle_trigger_stays_protected():
    resp = client.post("/admin/chronicle/generate")
    assert resp.status_code in (401, 403)
