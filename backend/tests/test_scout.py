"""尋訪（尋寶／尋人才）回歸測試。

守住四件事：欄位白名單、先檢查再扣款、每日 3 次上限、事件重播不重複扣款。
另外驗證「物資回報永遠低於禮金」——尋訪是金幣出口，不是新的印鈔機。
"""

from fastapi.testclient import TestClient

from app.api.routes_action import _process_action_event
from app.db import SessionLocal
from app.main import app
from app.models import Agent, AgentActionEvent
from app.services import scout as scout_service

client = TestClient(app)


def _register(username: str) -> dict:
    assert client.post(
        "/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "Aa1234!!"},
    ).status_code == 200
    login = client.post("/auth/login", json={"username": username, "password": "Aa1234!!"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['data']['token']}"}


def _agent(headers: dict, name: str = "ScoutLord") -> int:
    resp = client.post("/agent/register", headers=headers, json={"name": name, "role": "平民"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["agent_id"]


def _key(
    headers: dict,
    agent_id: int,
    allowed_actions: list[str] | None = None,
    name: str | None = None,
) -> dict:
    payload = {"name": name or f"scout-key-{agent_id}", "agent_id": agent_id}
    if allowed_actions is not None:
        payload["allowed_actions"] = allowed_actions
    resp = client.post("/api-keys", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return {"X-API-Key": resp.json()["data"]["key"]}


def _scout(key_headers: dict, payload: dict | None = None):
    return client.post(
        "/action/work",
        headers=key_headers,
        json={"action_type": "scout", "payload": payload if payload is not None else {}},
    )


def _state(agent_id: int) -> dict:
    db = SessionLocal()
    try:
        row = db.get(Agent, agent_id)
        return {
            "gold": row.gold, "food": row.food, "energy": row.energy,
            "reputation": row.reputation,
            "martial": row.martial, "intelligence": row.intelligence,
            "charisma": row.charisma, "politics": row.politics,
        }
    finally:
        db.close()


def _set(agent_id: int, **fields) -> None:
    db = SessionLocal()
    try:
        row = db.get(Agent, agent_id)
        for key, value in fields.items():
            setattr(row, key, value)
        db.commit()
    finally:
        db.close()


def test_defaults_and_payload_whitelist():
    headers = _register("scout_payload")
    agent_id = _agent(headers)
    key = _key(headers, agent_id)
    _set(agent_id, gold=10000, energy=100)

    ok = _scout(key)
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["focus"] == "balanced"
    assert ok.json()["data"]["budget"] == 100

    assert _scout(key, {"focus": "talent", "budget": 500}).status_code == 200
    assert _scout(key, {"focus": "wrong"}).json()["error"]["code"] == "INVALID_SCOUT_FOCUS"
    assert _scout(key, {"budget": 999}).json()["error"]["code"] == "INVALID_SCOUT_BUDGET"
    assert _scout(key, {"budget": True}).json()["error"]["code"] == "INVALID_SCOUT_BUDGET"
    assert _scout(key, {"note": "hello"}).json()["error"]["code"] == "INVALID_ACTION_PAYLOAD"
    assert _scout(key, {"url": "https://evil.example"}).json()["error"]["code"] == "INVALID_ACTION_PAYLOAD"


def test_scout_spends_gold_and_energy():
    headers = _register("scout_spend")
    agent_id = _agent(headers)
    key = _key(headers, agent_id)
    _set(agent_id, gold=3000, energy=100)
    before = _state(agent_id)

    resp = _scout(key, {"focus": "supply", "budget": 500})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["gold_spent"] == 500
    assert data["energy_cost"] == 20
    assert data["attempt"] == 1
    assert data["attempts_left"] == 2
    assert data["outcome"] in {"talent", "supply", "nothing"}

    after = _state(agent_id)
    assert after["energy"] == before["energy"] - 20
    assert after["gold"] == before["gold"] - 500 + data["reward"]["gold_gained"]
    assert after["food"] == before["food"] + data["reward"]["food_gained"]


def test_insufficient_gold_or_energy_changes_nothing():
    headers = _register("scout_broke")
    agent_id = _agent(headers)
    key = _key(headers, agent_id)

    _set(agent_id, gold=50, energy=100)
    before = _state(agent_id)
    resp = _scout(key, {"budget": 100})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INSUFFICIENT_RESOURCES"
    assert _state(agent_id) == before

    _set(agent_id, gold=3000, energy=5)
    before = _state(agent_id)
    resp = _scout(key, {"budget": 100})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INSUFFICIENT_ENERGY"
    assert _state(agent_id) == before

    db = SessionLocal()
    try:
        events = db.query(AgentActionEvent).filter(AgentActionEvent.agent_id == agent_id).all()
        assert len(events) == 2
        assert all(event.status == "failed" for event in events)
    finally:
        db.close()


def test_daily_limit_is_three():
    headers = _register("scout_limit")
    agent_id = _agent(headers)
    key = _key(headers, agent_id)
    _set(agent_id, gold=10000, energy=100)

    for attempt in (1, 2, 3):
        resp = _scout(key, {"budget": 100})
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["attempt"] == attempt

    after_three = _state(agent_id)
    blocked = _scout(key, {"budget": 100})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "SCOUT_DAILY_LIMIT_REACHED"
    assert _state(agent_id) == after_three


def test_legacy_key_can_scout_custom_allowlist_stays_strict():
    headers = _register("scout_keys")
    agent_id = _agent(headers)
    _set(agent_id, gold=10000, energy=100)

    legacy = _key(headers, agent_id, ["farm", "trade", "move"], name="legacy-key")
    assert _scout(legacy, {"budget": 100}).status_code == 200

    strict = _key(headers, agent_id, ["farm", "buy"], name="strict-key")
    blocked = _scout(strict, {"budget": 100})
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "ACTION_NOT_ALLOWED"

    allowed = _key(headers, agent_id, ["farm", "scout"], name="scout-key")
    assert _scout(allowed, {"budget": 100}).status_code == 200

    rows = client.get("/api-keys", headers=headers).json()["data"]["items"]
    by_name = {row["name"]: row for row in rows}
    assert "scout" in by_name["legacy-key"]["effective_allowed_actions"]
    assert "scout" not in by_name["legacy-key"]["allowed_actions"]
    assert "scout" not in by_name["strict-key"]["effective_allowed_actions"]


def test_completed_event_is_idempotent():
    headers = _register("scout_idempotent")
    agent_id = _agent(headers)
    key = _key(headers, agent_id)
    _set(agent_id, gold=10000, energy=100)

    first = _scout(key, {"budget": 100})
    assert first.status_code == 200
    event_id = first.json()["data"]["event_id"]
    after_first = _state(agent_id)

    db = SessionLocal()
    try:
        replay = _process_action_event(db, event_id)
    finally:
        db.close()
    assert replay["gold_spent"] == 100
    assert _state(agent_id) == after_first

    # 重播不能偷走第二次尋訪額度。
    second = _scout(key, {"budget": 100})
    assert second.status_code == 200
    assert second.json()["data"]["attempt"] == 2


def test_public_rules_and_recent_feed():
    rules = client.get("/world/public/scout?lang=zh")
    assert rules.status_code == 200
    data = rules.json()["data"]
    assert data["daily_limit"] == 3
    assert data["energy_cost"] == 20
    assert [row["gold"] for row in data["budgets"]] == [100, 500, 2000]
    assert data["how_to_scout"]["body"]["action_type"] == "scout"
    assert "buy" in data["note_zh"]

    headers = _register("scout_feed")
    agent_id = _agent(headers)
    key = _key(headers, agent_id)
    _set(agent_id, gold=3000)
    assert _scout(key, {"focus": "talent", "budget": 500}).status_code == 200

    feed = client.get("/world/public/scout?lang=zh").json()["data"]["recent"]
    assert len(feed) >= 1
    assert feed[0]["agent_id"] == agent_id
    assert feed[0]["outcome"] in {"talent", "supply", "nothing"}
    assert feed[0]["summary_zh"]


def test_rolls_are_deterministic_and_outcomes_stay_in_range():
    first = scout_service._rolls(42, "2026-11-07", 1, "talent", 500)
    assert first == scout_service._rolls(42, "2026-11-07", 1, "talent", 500)
    assert first != scout_service._rolls(42, "2026-11-07", 2, "talent", 500)
    assert all(0 <= value <= 1 for value in first)

    for budget in (100, 500, 2000):
        for focus in ("balanced", "talent", "supply"):
            for step in range(20):
                assert scout_service._pick_outcome(focus, budget, step / 20) in {
                    "talent", "supply", "nothing"
                }


def test_supply_never_prints_money(monkeypatch):
    """物資回報必須低於禮金，否則尋訪會變成洗錢機。"""
    headers = _register("scout_no_print")
    agent_id = _agent(headers)
    _set(agent_id, gold=10000, energy=100)
    monkeypatch.setattr(scout_service, "_rolls", lambda *args: [0.90, 0.10, 1.0, 0.5])

    db = SessionLocal()
    try:
        row = db.get(Agent, agent_id)
        for budget in (100, 500, 2000):
            before_gold = row.gold
            result = scout_service.run_scout(db, row, {"focus": "supply", "budget": budget})
            assert result["reward"]["gold_gained"] < budget
            assert row.gold <= before_gold
    finally:
        db.rollback()
        db.close()


def test_talent_respects_ability_cap(monkeypatch):
    headers = _register("scout_cap")
    agent_id = _agent(headers)
    _set(
        agent_id, gold=10000, energy=100,
        martial=99, intelligence=99, charisma=99, politics=99,
    )
    monkeypatch.setattr(scout_service, "_rolls", lambda *args: [0.01, 0.01, 0.5, 0.5])

    db = SessionLocal()
    try:
        row = db.get(Agent, agent_id)
        result = scout_service.run_scout(db, row, {"focus": "talent", "budget": 2000})
        assert result["outcome"] == "talent"
        assert result["reward"]["ability_after"] == 99
        assert result["reward"]["ability_gain"] == 0
        assert result["reward"]["reputation_gain"] > 0  # 滿能力仍有聲望回報
        assert all(getattr(row, key) <= 99 for key in ("martial", "intelligence", "charisma", "politics"))
    finally:
        db.rollback()
        db.close()


def test_all_focus_budget_combinations_validate():
    for focus in ("balanced", "talent", "supply"):
        for budget in (100, 500, 2000):
            assert scout_service.validate_request(focus, budget) == {"focus": focus, "budget": budget}
