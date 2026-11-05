"""資料稽核必須是唯讀的。"""

from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Agent, City, Faction, User
from app.services.world_data_audit import audit_world_data

client = TestClient(app)


def _seed() -> None:
    db = SessionLocal()
    try:
        db.add(City(name=settings.city_name, base_url="http://localhost", treasury_food=0))
        db.add(City(name="Luoyang", base_url="http://localhost2", treasury_food=7))
        u = User(username="audit_owner", email="audit_owner@example.com", password_hash="x")
        db.add(u)
        db.commit()
        db.refresh(u)
        for i, name in enumerate(
            ["小魚兒", "小魚兒", "小魚兒", "probe-1", "TestAgent", "OpenClaw定時任務代理", "趙雲"]
        ):
            db.add(
                Agent(
                    owner_user_id=u.id,
                    name=name,
                    role="平民",
                    home_city=settings.city_name if i % 2 else "Luoyang",
                    current_city=settings.city_name,
                    food=0,
                    reputation=0,
                    faction_id=1 if i == 6 else None,
                )
            )
        db.add(Faction(name="Wei", leader_agent_id=999, home_city="Luoyang"))
        db.commit()
    finally:
        db.close()


def test_audit_detects_test_agents_duplicates_and_city_variants():
    _seed()
    db = SessionLocal()
    try:
        report = audit_world_data(db)
        assert report["read_only"] is True
        assert report["summary"]["agents"] == 7
        assert report["summary"]["test_agents"] == 3
        assert any(d["name"] == "小魚兒" and d["count"] == 3 for d in report["duplicate_names"])
        assert "Luoyang" in report["summary"]["city_names_in_use"]
        assert report["summary"]["agents_zero_food"] == 7
        assert report["summary"]["agents_without_faction"] == 6
        assert any(not f["leader_exists"] for f in report["factions"])
        assert report["recommendations"]
    finally:
        db.close()


def test_audit_does_not_modify_data():
    _seed()
    db = SessionLocal()
    try:
        before = [(a.id, a.name, a.home_city, a.food, a.reputation) for a in db.query(Agent).all()]
        audit_world_data(db)
        db.expire_all()
        after = [(a.id, a.name, a.home_city, a.food, a.reputation) for a in db.query(Agent).all()]
        assert before == after
    finally:
        db.close()


def test_audit_endpoint_requires_admin():
    _seed()
    assert client.get("/admin/data/audit").status_code == 401

    client.post(
        "/auth/register",
        json={"username": "audit_admin", "email": "audit_admin@example.com", "password": "Aa1234!!"},
    )
    login = client.post("/auth/login", json={"username": "audit_admin", "password": "Aa1234!!"})
    headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}
    resp = client.get("/admin/data/audit", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["read_only"] is True
