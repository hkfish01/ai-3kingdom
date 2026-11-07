"""饑荒自動止血：只有全城一起餓才開倉，且每天最多一次。

1.28.0 上線後線上排行榜顯示所有 agent 都 food=0；這組測試確保 1.29.0 部署後
worker 第一輪就會補糧，但正常年景不會把商城經濟洗成「每天白送」。
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Agent
from app.services import market as market_service
from app.services.system_state import get_state

client = TestClient(app)
DAY_1 = datetime(2026, 11, 7, 5, tzinfo=timezone.utc)
DAY_2 = datetime(2026, 11, 8, 5, tzinfo=timezone.utc)


def _seed(foods: list[int]) -> None:
    """每個測試的 DB 都是乾淨的（conftest 會 drop/create），直接建立諸侯。"""
    for i, food in enumerate(foods):
        username = f"famine_{i}"
        assert client.post(
            "/auth/register",
            json={"username": username, "email": f"{username}@example.com", "password": "Aa1234!!"},
        ).status_code == 200
        login = client.post("/auth/login", json={"username": username, "password": "Aa1234!!"})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}
        resp = client.post(
            "/agent/register", headers=headers, json={"name": f"Famine-{i}", "role": "平民"}
        )
        assert resp.status_code == 200, resp.text
        _set_food(resp.json()["data"]["agent_id"], food)


def _set_food(agent_id: int, food: int) -> None:
    db = SessionLocal()
    try:
        db.get(Agent, agent_id).food = food
        db.commit()
    finally:
        db.close()


def _set_all_food(food: int) -> None:
    db = SessionLocal()
    try:
        for row in db.query(Agent).all():
            row.food = food
        db.commit()
    finally:
        db.close()


def _foods() -> list[int]:
    db = SessionLocal()
    try:
        return [row.food for row in db.query(Agent).order_by(Agent.id.asc()).all()]
    finally:
        db.close()


def _ensure(now: datetime = DAY_1, **kwargs) -> dict:
    db = SessionLocal()
    try:
        return market_service.ensure_famine_relief(db, now=now, **kwargs)
    finally:
        db.close()


def test_healthy_world_is_untouched_and_checked_once():
    _seed([100, 100, 100, 0])
    before = _foods()

    result = _ensure()
    assert result["status"] == "healthy"
    assert result["applied"] is False
    assert result["starving_ratio"] == 0.25
    assert result["total_agents"] == 4
    assert _foods() == before  # 正常年景一個 agent 都不改

    assert _ensure(now=datetime(2026, 11, 7, 6, tzinfo=timezone.utc))["status"] == "already_checked"


def test_threshold_is_strict():
    """3/4 = 0.75 未達 0.8，不能開倉。"""
    _seed([100, 0, 0, 0])
    result = _ensure()
    assert result["status"] == "healthy"
    assert result["starving_ratio"] == 0.75
    assert _foods() == [100, 0, 0, 0]


def test_too_few_agents_never_triggers():
    _seed([0, 0])  # 100% 斷糧，但未達 MARKET_FAMINE_MIN_AGENTS=3
    assert _ensure()["status"] == "healthy"
    assert _foods() == [0, 0]


def test_citywide_famine_opens_granary_once_per_day():
    _seed([0, 0, 5, 0])
    result = _ensure()
    assert result["status"] == "relief_applied"
    assert result["applied"] is True
    assert result["starving_agents"] == 4
    assert result["relief"]["agents"] == 4
    assert _foods() == [60, 60, 60, 60]

    db = SessionLocal()
    try:
        assert get_state(db, "market.famine.checked.2026-11-07").startswith("relief;")
        assert "agents=4" in get_state(db, "market.relief.2026-11-07")
    finally:
        db.close()

    assert _ensure(now=datetime(2026, 11, 7, 9, tzinfo=timezone.utc))["status"] == "already_checked"
    assert _foods() == [60, 60, 60, 60]

    # 強制重跑也不會重複補糧：已經沒人低於底線。
    forced = _ensure(force=True)
    assert forced["status"] == "healthy"
    assert _foods() == [60, 60, 60, 60]


def test_relief_does_not_become_a_daily_handout():
    """關鍵回歸：補到 60 後隔日重置只剩 50，仍付得起口糧 → 不能再開倉。"""
    _seed([0, 0, 0, 0])
    assert _ensure(DAY_1)["status"] == "relief_applied"
    assert _foods() == [60, 60, 60, 60]

    _set_all_food(50)  # 模擬每日重置扣掉 10 糧，但沒有人餓到付不起
    result = _ensure(DAY_2)
    assert result["status"] == "healthy"
    assert result["trigger_food"] == 10
    assert result["starving_agents"] == 0
    assert _foods() == [50, 50, 50, 50]


def test_next_day_rechecks_after_another_famine():
    _seed([0, 0, 0, 0])
    assert _ensure(DAY_1)["status"] == "relief_applied"

    _set_all_food(0)  # 模擬隔日又被扣光
    second = _ensure(DAY_2)
    assert second["status"] == "relief_applied"
    assert second["date"] == "2026-11-08"
    assert _foods() == [60, 60, 60, 60]


def test_no_starving_agents_does_not_write_an_empty_chronicle():
    _seed([100, 100, 100])
    db = SessionLocal()
    try:
        result = market_service.run_market_relief(db, 60, day="2026-11-07")
        assert result["status"] == "no_starving_agents"
        assert get_state(db, "market.relief.2026-11-07") == "no_starving_agents"
    finally:
        db.close()
    assert "開倉賑濟" not in client.get("/world/public/chronicle?lang=zh").text


def test_disabled_floor_short_circuits(monkeypatch):
    _seed([0, 0, 0, 0])
    monkeypatch.setattr(settings, "market_famine_relief_floor", 0)
    result = _ensure()
    assert result["status"] == "disabled"
    assert _foods() == [0, 0, 0, 0]
