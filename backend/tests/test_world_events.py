"""世界事件引擎：開關、狀態機、不可逆、背刺懲罰、史記注入、權限。"""

from datetime import timedelta

from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Agent, ChronicleEntry, City, Faction, User
from app.services.daily_chronicle import generate_daily_chronicle
from app.services.world_events import (
    BETRAYAL_EVENT_TYPE,
    EVENT_TYPE,
    contribute_food,
    break_pact,
    evaluate_world_events,
    event_lines,
    form_pact,
    load_state,
    public_events,
    _now,
)

client = TestClient(app)


def _seed(treasury_food: int = 0, names: tuple[str, ...] = ("小魚兒", "趙雲", "姜維")) -> list[int]:
    """conftest 會在每個測試前 drop_all/create_all，所以每次都要自己 seed。"""
    db = SessionLocal()
    try:
        db.add(
            City(
                name=settings.city_name,
                base_url="http://localhost:8000",
                treasury_gold=3398,
                treasury_food=treasury_food,
                city_wall=300,
            )
        )
        user = User(username="event_owner", email="event_owner@example.com", password_hash="x", is_admin=False)
        db.add(user)
        db.commit()
        db.refresh(user)
        ids = []
        for i, name in enumerate(names):
            agent = Agent(
                owner_user_id=user.id,
                name=name,
                role="平民",
                home_city=settings.city_name,
                current_city=settings.city_name,
                gold=1000,
                food=1000,
                reputation=50,
                faction_id=1 if i == 0 else None,
            )
            db.add(agent)
            ids.append(agent)
        db.add(Faction(name="Wei", leader_agent_id=1, home_city=settings.city_name))
        db.commit()
        for agent in ids:
            db.refresh(agent)
        return [a.id for a in ids]
    finally:
        db.close()


def _enable(monkeypatch) -> None:
    monkeypatch.setattr(settings, "world_events_enabled", True)


def _auth_header(username: str = "ev_admin") -> dict:
    client.post(
        "/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "Aa1234!!"},
    )
    resp = client.post("/auth/login", json={"username": username, "password": "Aa1234!!"})
    return {"Authorization": f"Bearer {resp.json()['data']['token']}"}


def test_disabled_by_default_keeps_existing_payload_shape():
    assert settings.world_events_enabled is False
    _seed()

    state = client.get("/world/public/state").json()["data"]
    assert "events" not in state
    assert "treasury" in state and "agent_count" in state

    ev = client.get("/world/public/events").json()["data"]
    assert ev["enabled"] is False and ev["events"] == []

    db = SessionLocal()
    try:
        assert event_lines(db, "zh") == []
    finally:
        db.close()


def test_evaluate_opens_three_crises_and_writes_chronicle(monkeypatch):
    _enable(monkeypatch)
    _seed(treasury_food=0)
    db = SessionLocal()
    try:
        result = evaluate_world_events(db)
        assert result["enabled"] is True
        assert sorted(result["changes"]) == [
            "chancellor:opened", "famine:opened", "three_powers:opened"
        ]
        state = load_state(db)
        assert state["revision"] == 1
        assert all(
            state["events"][k]["status"] == "active" and state["events"][k]["irreversible"]
            for k in ("famine", "chancellor", "three_powers")
        )
        assert all(state["events"][k]["deadline_utc"].endswith("Z") for k in state["events"])
        assert db.query(ChronicleEntry).filter(ChronicleEntry.event_type == EVENT_TYPE).count() == 3
        assert any("洛陽糧盡" in e["title"] for e in public_events(db, "zh"))
        assert "限" in event_lines(db, "zh")[0]
    finally:
        db.close()


def test_expiry_is_irreversible(monkeypatch):
    _enable(monkeypatch)
    _seed(treasury_food=0)
    db = SessionLocal()
    try:
        evaluate_world_events(db, now=_now())
        result = evaluate_world_events(db, now=_now() + timedelta(hours=200))
        assert sorted(result["changes"]) == [
            "chancellor:expired", "famine:expired", "three_powers:expired"
        ]
        city = db.query(City).first()
        assert city.city_wall == 300 - settings.world_events_famine_wall_penalty - 30
        assert city.treasury_gold == 3398 - 500

        # 已結案的事件永不再回寫，即使條件事後滿足也一樣。
        second = evaluate_world_events(db, now=_now() + timedelta(hours=400))
        assert second["changes"] == []
        state = load_state(db)
        assert state["events"]["famine"]["status"] == "expired"
        assert state["events"]["famine"]["outcome"] == "expired"
    finally:
        db.close()


def test_contribute_food_resolves_famine(monkeypatch):
    _enable(monkeypatch)
    ids = _seed(treasury_food=0)
    db = SessionLocal()
    try:
        evaluate_world_events(db)
        agent = db.get(Agent, ids[0])
        result = contribute_food(db, agent, 500)
        assert result["resolved"] is True
        assert result["city_food"] == 500
        assert result["agent_food"] == 500
        assert load_state(db)["events"]["famine"]["status"] == "resolved"
        assert db.query(ChronicleEntry).filter(ChronicleEntry.title.like("%已解%")).count() == 1
    finally:
        db.close()


def test_betrayal_deducts_reputation_and_is_public(monkeypatch):
    _enable(monkeypatch)
    ids = _seed()
    db = SessionLocal()
    try:
        a, b, c = (db.get(Agent, i) for i in ids)
        form_pact(db, a, b)
        assert a.reputation == 50

        result = form_pact(db, a, c)
        assert result["betrayal"]["victim_name"] == b.name
        assert a.reputation == 50 - settings.world_events_betrayal_penalty
        assert db.query(ChronicleEntry).filter(
            ChronicleEntry.event_type == BETRAYAL_EVENT_TYPE
        ).count() == 1
        assert any("【背盟】" in line for line in event_lines(db, "zh"))

        chronicle = client.get("/world/public/chronicle?lang=zh").json()["data"]
        assert any("背盟" in e["title"] for e in chronicle["entries"])
        assert any(e["event_type_localized"] == "背盟" for e in chronicle["entries"])
    finally:
        db.close()


def test_break_pact_and_no_pact_error(monkeypatch):
    _enable(monkeypatch)
    ids = _seed()
    db = SessionLocal()
    try:
        a, b, _ = (db.get(Agent, i) for i in ids)
        form_pact(db, a, b)
        result = break_pact(db, a)
        assert result["betrayal"]["breaker_name"] == a.name
        assert a.reputation == 50 - settings.world_events_betrayal_penalty
        try:
            break_pact(db, a)
            assert False, "expected EVENT_NO_PACT"
        except Exception as exc:
            assert getattr(exc, "code", "") == "EVENT_NO_PACT"
    finally:
        db.close()


def test_event_lines_flow_into_daily_story(monkeypatch):
    _enable(monkeypatch)
    _seed(treasury_food=0)
    db = SessionLocal()
    try:
        evaluate_world_events(db)
        story = generate_daily_chronicle(db, lang="zh", force=True)
        assert any("【天下有事】" in line for line in story["lines"])
        assert "【天下有事】" in story["share_text"]
    finally:
        db.close()


def test_event_endpoints_require_auth_or_admin(monkeypatch):
    _enable(monkeypatch)
    _seed()
    assert client.post("/world/events/contribute", json={"agent_id": 1, "amount": 10}).status_code == 401
    assert client.post("/admin/events/advance").status_code == 401
    # routes_auth 會把「第一個註冊者」設為管理員，所以第二個才是一般使用者。
    admin_headers = _auth_header("ev_admin")
    normal_headers = _auth_header("ev_normal")
    assert client.post("/admin/events/advance", headers=admin_headers).status_code == 200
    assert client.post("/admin/events/advance", headers=normal_headers).status_code == 403
    assert client.get("/world/public/events").status_code == 200
