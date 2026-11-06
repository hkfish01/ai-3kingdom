"""商城止血 + 三個陷阱的回歸測試。

陷阱：
1. bootstrap 時代的舊 key allowlist 只有 farm/trade/move，新動作 buy 必須相容；
2. 工作分支原本只加錢不檢查餘額，商城必須「先檢查再扣款再發貨」；
3. _validate_work_payload 原本把所有工作動作的 payload 限制成 {}，buy 必須能帶參數。
"""

from fastapi.testclient import TestClient

from app.api.routes_action import _process_action_event
from app.db import SessionLocal
from app.main import app
from app.models import Agent, AgentActionEvent, User

client = TestClient(app)


def _register(username: str) -> dict:
    reg = client.post(
        "/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "Aa1234!!"},
    )
    assert reg.status_code == 200
    login = client.post("/auth/login", json={"username": username, "password": "Aa1234!!"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['data']['token']}"}


def _agent(headers: dict, name: str = "MarketLord") -> int:
    resp = client.post("/agent/register", headers=headers, json={"name": name, "role": "平民"})
    assert resp.status_code == 200
    return resp.json()["data"]["agent_id"]


def _key(headers: dict, agent_id: int, allowed_actions: list[str] | None = None) -> dict:
    payload = {"name": f"key-{agent_id}", "agent_id": agent_id}
    if allowed_actions is not None:
        payload["allowed_actions"] = allowed_actions
    resp = client.post("/api-keys", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return {"X-API-Key": resp.json()["data"]["key"]}


def _buy(key_headers: dict, item: str = "grain_bag", quantity: int = 1, extra: dict | None = None):
    payload = {"item": item, "quantity": quantity}
    if extra:
        payload.update(extra)
    return client.post(
        "/action/work",
        headers=key_headers,
        json={"action_type": "buy", "payload": payload},
    )


def _state(agent_id: int) -> tuple[int, int]:
    db = SessionLocal()
    try:
        row = db.get(Agent, agent_id)
        return row.gold, row.food
    finally:
        db.close()


def _set_gold(agent_id: int, gold: int) -> None:
    db = SessionLocal()
    try:
        db.get(Agent, agent_id).gold = gold
        db.commit()
    finally:
        db.close()


def test_legacy_key_can_buy_and_balance_is_debited():
    """陷阱 1 + 2：舊 key 能買；金幣真的被扣、糧食真的入帳。"""
    headers = _register("market_legacy")
    agent_id = _agent(headers)
    # 這是 bootstrap / CreateApiKeyRequest 的舊預設白名單，不含 buy。
    key = _key(headers, agent_id, ["farm", "trade", "move"])

    before_gold, before_food = _state(agent_id)
    resp = _buy(key, quantity=2)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["action_type"] == "buy"
    assert data["gold_spent"] == 60
    assert data["food_gained"] == 80

    after_gold, after_food = _state(agent_id)
    assert after_gold == before_gold - 60
    assert after_food == before_food + 80
    assert after_gold >= 0


def test_custom_allowlist_stays_strict():
    """相容只放寬舊預設白名單，使用者自訂的仍嚴格執行。"""
    headers = _register("market_custom")
    agent_id = _agent(headers)
    strict = _key(headers, agent_id, ["farm"])
    assert _buy(strict).status_code == 403
    assert _buy(strict).json()["error"]["code"] == "ACTION_NOT_ALLOWED"

    allowed = _key(headers, agent_id, ["farm", "buy"])
    assert _buy(allowed).status_code == 200


def test_api_keys_report_effective_allowlist():
    headers = _register("market_effective")
    agent_id = _agent(headers)
    _key(headers, agent_id, ["farm", "trade", "move"])
    rows = client.get("/api-keys", headers=headers).json()["data"]["items"]
    assert "buy" in rows[0]["effective_allowed_actions"]
    assert "buy" not in rows[0]["allowed_actions"]


def test_insufficient_gold_changes_nothing():
    """陷阱 2：餘額不足時不扣錢、不發貨，事件標記 failed。"""
    headers = _register("market_broke")
    agent_id = _agent(headers)
    key = _key(headers, agent_id)
    _set_gold(agent_id, 20)
    before = _state(agent_id)

    resp = _buy(key, quantity=3)  # 90 gold
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INSUFFICIENT_RESOURCES"
    assert _state(agent_id) == before

    db = SessionLocal()
    try:
        events = db.query(AgentActionEvent).filter(AgentActionEvent.agent_id == agent_id).all()
        assert len(events) == 1
        assert events[0].status == "failed"
        assert events[0].error_code == "INSUFFICIENT_RESOURCES"
    finally:
        db.close()


def test_completed_event_is_idempotent():
    """重播已完成事件不能再扣一次款。"""
    headers = _register("market_idempotent")
    agent_id = _agent(headers)
    key = _key(headers, agent_id)
    first = _buy(key)
    assert first.status_code == 200
    event_id = first.json()["data"]["event_id"]
    after_first = _state(agent_id)

    db = SessionLocal()
    try:
        again = _process_action_event(db, event_id)
    finally:
        db.close()
    assert again["gold_spent"] == 30
    assert _state(agent_id) == after_first


def test_buy_payload_is_validated_but_work_payload_stays_empty():
    """陷阱 3：buy 可帶 item/quantity，其餘工作動作仍只接受 {}。"""
    headers = _register("market_payload")
    agent_id = _agent(headers)
    key = _key(headers, agent_id)

    assert client.post(
        "/action/work", headers=key, json={"action_type": "farm", "payload": {"quantity": 1}}
    ).status_code == 422
    assert _buy(key, extra={"note": "hello"}).status_code == 422
    assert _buy(key, item="not_an_item").json()["error"]["code"] == "MARKET_ITEM_NOT_FOUND"
    assert _buy(key, quantity=0).json()["error"]["code"] == "INVALID_MARKET_QUANTITY"
    assert _buy(key, quantity=21).json()["error"]["code"] == "INVALID_MARKET_QUANTITY"
    assert _buy(key, quantity="2").json()["error"]["code"] == "INVALID_MARKET_QUANTITY"
    # 既有安全檢查仍生效：指令/URL 關鍵字一律擋下。
    assert client.post(
        "/action/work",
        headers=key,
        json={"action_type": "buy", "payload": {"item": "grain_bag", "quantity": 1, "url": "https://evil.example"}},
    ).status_code == 422
    assert _buy(key).status_code == 200


def test_public_catalog_and_admin_relief():
    catalog = client.get("/world/public/market?lang=zh")
    assert catalog.status_code == 200
    items = catalog.json()["data"]["items"]
    assert {row["item_id"] for row in items} == {
        "grain_bag", "grain_cart", "grain_convoy", "energy_tonic"
    }
    assert catalog.json()["data"]["how_to_buy"]["body"]["action_type"] == "buy"

    headers = _register("market_relief")
    agent_id = _agent(headers)
    _set_gold(agent_id, 100)
    db = SessionLocal()
    try:
        db.get(Agent, agent_id).food = 0
        db.query(User).filter(User.username == "market_relief").first().is_admin = True
        db.commit()
    finally:
        db.close()

    # 非 admin 不能執行救濟。
    guest = _register("market_guest")
    assert client.post("/admin/market/relief", headers=guest).status_code == 403

    preview = client.post("/admin/market/relief?floor=60&dry_run=true", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["data"]["status"] == "preview"
    assert preview.json()["data"]["agents"] == 1
    _, food = _state(agent_id)
    assert food == 0  # dry run 不寫入

    applied = client.post("/admin/market/relief?floor=60&dry_run=false", headers=headers)
    assert applied.status_code == 200
    assert applied.json()["data"]["status"] == "applied"
    assert _state(agent_id)[1] == 60

    again = client.post("/admin/market/relief?floor=60&dry_run=false", headers=headers)
    assert again.json()["data"]["status"] == "already_applied"
