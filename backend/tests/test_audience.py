"""觀眾助威／押陣：防刷、士氣上限、演武整合與公開欄位限縮。"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Agent, BattleLog, City, User
from app.services import audience as audience_service
from app.services.arena_exhibition import run_daily_arena
from app.services.chronicle_publish import current_post_package
from app.services.system_state import get_state, set_state

client = TestClient(app)

# 2026-11-05 22:59 UTC = 2026-11-06 06:59 HKT（演武前）
BEFORE = datetime(2026, 11, 5, 22, 59, tzinfo=timezone.utc)
# 2026-11-05 23:00 UTC = 2026-11-06 07:00 HKT（演武後）
AFTER = datetime(2026, 11, 5, 23, 0, tzinfo=timezone.utc)


def _seed(n: int = 2) -> list[int]:
    db = SessionLocal()
    try:
        db.add(City(name=settings.city_name, base_url="http://localhost:8000"))
        ids = []
        for i in range(n):
            user = User(
                username=f"audience_owner_{i}",
                email=f"audience_owner_{i}@example.com",
                password_hash="x",
                is_admin=False,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            agent = Agent(
                owner_user_id=user.id,
                name=f"觀眾諸侯{i}",
                role="平民",
                home_city=settings.city_name,
                current_city=settings.city_name,
                infantry=60 + i * 20,
                archer=10,
                cavalry=5,
                martial=60,
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
            ids.append(agent.id)
        return ids
    finally:
        db.close()


def _write_bucket(date_str: str, cheers: dict | None = None, challenger: int = 0, defender: int = 0) -> None:
    data = audience_service._empty_bucket(date_str)
    data["cheers"] = {str(k): v for k, v in (cheers or {}).items()}
    data["votes"] = {"challenger": challenger, "defender": defender}
    _set_raw(audience_service._key(date_str), json.dumps(data))


def _set_raw(key: str, value: str) -> None:
    with SessionLocal() as db:
        set_state(db, key, value)
        db.commit()


def _morale(day: str) -> dict:
    with SessionLocal() as db:
        return audience_service.morale_for_date(db, day)


def _arena(now: datetime) -> dict:
    with SessionLocal() as db:
        return run_daily_arena(db, now=now, force=True)


def _battle_power(battle_id: str) -> float:
    with SessionLocal() as db:
        return float(db.query(BattleLog).filter(BattleLog.request_id == battle_id).first().attack_power)


@pytest.fixture(autouse=True)
def _audience_on(monkeypatch):
    monkeypatch.setattr(settings, "audience_enabled", True)
    monkeypatch.setattr(settings, "arena_enabled", True)
    monkeypatch.setattr(settings, "audience_max_boost", 0.12)
    monkeypatch.setattr(settings, "audience_min_votes", 3)


def test_target_date_rolls_over_at_arena_hour():
    assert audience_service.target_date(BEFORE) == "2026-11-06"
    assert audience_service.target_date(AFTER) == "2026-11-07"
    assert audience_service.audience_date(BEFORE) == "2026-11-06"


def test_cheer_and_vote_are_once_per_visitor_per_day():
    ids = _seed()
    first = client.post("/world/public/audience/cheer", json={"visitor_id": "visitor_AAAA", "agent_id": ids[0]})
    assert first.status_code == 200
    assert first.json()["data"]["recorded"] is True
    assert first.json()["data"]["target_date"] == audience_service.target_date()

    repeat = client.post("/world/public/audience/cheer", json={"visitor_id": "visitor_AAAA", "agent_id": ids[1]})
    assert repeat.json()["data"]["recorded"] is False
    assert repeat.json()["data"]["reason"] == "ALREADY_CHEERED"

    other = client.post("/world/public/audience/cheer", json={"visitor_id": "visitor_BBBB", "agent_id": ids[0]})
    assert other.json()["data"]["recorded"] is True

    vote = client.post("/world/public/audience/vote", json={"visitor_id": "visitor_AAAA", "side": "challenger"})
    assert vote.json()["data"]["recorded"] is True
    vote_repeat = client.post("/world/public/audience/vote", json={"visitor_id": "visitor_AAAA", "side": "defender"})
    assert vote_repeat.json()["data"]["recorded"] is False
    assert vote_repeat.json()["data"]["reason"] == "ALREADY_VOTED"

    today = client.get("/world/public/audience/today?visitor_id=visitor_AAAA").json()["data"]
    assert today["already_cheered"] is True
    assert today["already_voted"] is True
    assert today["cheer_total"] == 2
    assert today["cheer_standings"][0]["agent_id"] == ids[0]
    assert today["cheer_standings"][0]["cheers"] == 2
    assert today["votes"] == {"challenger": 1, "defender": 0}


def test_invalid_payloads_are_rejected():
    ids = _seed(1)
    bad_side = client.post("/world/public/audience/vote", json={"visitor_id": "visitor_AAAA", "side": "banana"})
    assert bad_side.status_code == 422
    bad_visitor = client.post("/world/public/audience/cheer", json={"visitor_id": "a", "agent_id": ids[0]})
    assert bad_visitor.status_code == 422
    missing_agent = client.post("/world/public/audience/cheer", json={"visitor_id": "visitor_AAAA", "agent_id": 99999})
    assert missing_agent.status_code == 404


def test_morale_has_minimum_threshold_and_hard_cap():
    day = audience_service.target_date(BEFORE)
    _write_bucket(day, challenger=2)
    low = _morale(day)
    assert low["applied"] is False and low["boost"] == 0.0

    _write_bucket(day, challenger=20)
    high = _morale(day)
    assert high["applied"] is True
    assert high["boost"] == pytest.approx(0.12)

    _write_bucket(day, challenger=200)
    assert _morale(day)["boost"] == pytest.approx(0.12)

    _write_bucket(day, defender=20)
    assert _morale(day)["boost"] == pytest.approx(-0.12)

    _write_bucket(day, challenger=10, defender=10)
    assert _morale(day)["boost"] == 0.0


def test_arena_uses_morale_without_touching_agent_state():
    ids = _seed(1)
    day = audience_service.target_date(BEFORE)

    _write_bucket(day)
    plain = _arena(BEFORE)
    assert plain["status"] == "created"
    power_without = _battle_power(plain["battle_id"])

    _write_bucket(day, challenger=20)
    boosted = _arena(BEFORE)
    assert boosted["status"] == "created"
    power_with = _battle_power(boosted["battle_id"])
    assert power_with > power_without * 1.05

    with SessionLocal() as db:
        agent = db.get(Agent, ids[0])
        assert (agent.infantry, agent.archer, agent.cavalry, agent.gold) == (60, 10, 5, 100)
        snapshot = json.loads(get_state(db, "arena.snapshot." + boosted["battle_id"]))
        assert snapshot["audience"]["boost_pct"] > 0
        assert "觀眾押陣" in snapshot["verdict"]


def test_public_api_never_exposes_private_fields():
    ids = _seed(1)
    client.post("/world/public/audience/cheer", json={"visitor_id": "visitor_AAAA", "agent_id": ids[0]})
    raw = json.dumps(client.get("/world/public/audience/today?visitor_id=visitor_AAAA").json())
    for forbidden in ("owner_user_id", "password_hash", "@example.com", "visitor_AAAA", "jwt_secret"):
        assert forbidden not in raw
    agents = client.get("/world/public/audience/agents").json()["data"]["items"]
    assert set(agents[0]) == {"agent_id", "name", "city", "troops"}


def test_disabled_feature_rejects_writes_but_keeps_reads(monkeypatch):
    monkeypatch.setattr(settings, "audience_enabled", False)
    assert client.get("/world/public/audience/today").status_code == 200
    denied = client.post("/world/public/audience/vote", json={"visitor_id": "visitor_AAAA", "side": "challenger"})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "AUDIENCE_DISABLED"


def test_share_card_and_post_package():
    ids = _seed(1)
    client.post("/world/public/audience/cheer", json={"visitor_id": "visitor_AAAA", "agent_id": ids[0]})
    svg = client.get("/world/public/audience/card.svg?lang=zh")
    assert svg.status_code == 200
    assert "觀眾席" in svg.text
    png = client.get("/world/public/audience/card.png?lang=zh")
    assert png.status_code == 200
    assert png.headers["content-type"] in ("image/png", "image/svg+xml")

    post = client.get("/world/public/audience/post?lang=zh").json()["data"]
    assert post["cheer_total"] == 1
    assert "/audience" in post["link"]
    assert post["image_url"].endswith("card.png?lang=zh")
    assert "觀眾席" in post["caption"]


def test_chronicle_post_package_picks_up_same_day_audience(monkeypatch):
    _seed(1)
    # 08:00 HKT 發文包要讀「當日已結束的演武」bucket，不是下一場；
    # 固定日期避免測試結果跟著執行日漂移。
    day = "2026-11-06"
    _write_bucket(day, challenger=8, defender=2)
    monkeypatch.setattr(audience_service, "audience_date", lambda now=None: day)
    with SessionLocal() as db:
        package = current_post_package(db, "zh")
    assert "觀眾席" in package.get("audience_note", "")
    assert "觀眾席" in package["caption"]


def test_old_buckets_are_pruned_on_write():
    old = (datetime(2026, 11, 6).date() - timedelta(days=90)).isoformat()
    old_key = audience_service._key(old)
    _set_raw(old_key, "{}")
    with SessionLocal() as db:
        assert get_state(db, old_key) == "{}"
    ids = _seed(1)
    client.post("/world/public/audience/cheer", json={"visitor_id": "visitor_AAAA", "agent_id": ids[0]})
    with SessionLocal() as db:
        assert get_state(db, old_key) == ""
