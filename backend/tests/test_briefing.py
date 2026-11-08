"""每日簡報回歸測試。

守住五件事：API key 才能讀自己的簡報、不洩漏個資、建議動作真的划算且付得起、
自訂白名單不會收到注定 403 的建議、引導文件確實把簡報指給 agent 看。
"""

from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Agent, AgentDailyQuest
from app.services import updates as updates_service

client = TestClient(app)


def _register(username: str) -> dict:
    assert client.post(
        "/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "Aa1234!!"},
    ).status_code == 200
    login = client.post("/auth/login", json={"username": username, "password": "Aa1234!!"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['data']['token']}"}


def _agent(headers: dict, name: str = "BriefingLord") -> int:
    resp = client.post("/agent/register", headers=headers, json={"name": name, "role": "平民"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["agent_id"]


def _key(headers: dict, agent_id: int, allowed_actions: list[str] | None = None) -> dict:
    payload = {"name": f"briefing-key-{agent_id}", "agent_id": agent_id}
    if allowed_actions is not None:
        payload["allowed_actions"] = allowed_actions
    resp = client.post("/api-keys", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return {"X-API-Key": resp.json()["data"]["key"]}


def _set_state(agent_id: int, **fields) -> None:
    db = SessionLocal()
    try:
        row = db.get(Agent, agent_id)
        assert row is not None
        for key, value in fields.items():
            setattr(row, key, value)
        db.commit()
    finally:
        db.close()


def test_agent_briefing_requires_api_key():
    assert client.get("/agent/briefing").status_code == 401


def test_agent_briefing_returns_own_state_without_pii():
    headers = _register("briefing_owner")
    agent_id = _agent(headers)
    key = _key(headers, agent_id)

    resp = client.get("/agent/briefing?lang=zh", headers=key)
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["agent"]["id"] == agent_id
    for field in ("gold", "food", "energy", "troops", "abilities"):
        assert field in body["agent"]
    assert "quests" in body and "claimable_count" in body["quests"]
    assert "world" in body and "next_actions" in body
    assert body["update_revision"] == body["world"]["update_revision"]

    raw = resp.text
    for secret in ("email", "owner_user_id", "password_hash", "claim_code", "sk_"):
        assert secret not in raw


def test_low_food_suggests_an_affordable_purchase():
    headers = _register("briefing_hungry")
    agent_id = _agent(headers, "HungryLord")
    key = _key(headers, agent_id)
    _set_state(agent_id, food=0, gold=500, energy=100)

    body = client.get("/agent/briefing?lang=zh", headers=key).json()["data"]
    buys = [
        row for row in body["next_actions"]
        if (row.get("body") or {}).get("action_type") == "buy"
    ]
    assert len(buys) == 1
    buy = buys[0]
    payload = buy["body"]["payload"]
    assert buy["path"] == "/action/work"
    assert payload["item"] == body["world"]["market"]["best_food_item"]["item_id"]
    assert payload["quantity"] >= 1
    unit = body["world"]["market"]["best_food_item"]["unit_price_gold"]
    assert unit * payload["quantity"] <= 500  # 建議一定是付得起的
    assert client.post("/action/work", headers=key, json=buy["body"]).status_code == 200


def test_legacy_keys_see_new_actions_but_custom_allowlist_does_not():
    headers = _register("briefing_allowlist")
    agent_id = _agent(headers, "AllowlistLord")
    legacy = _key(headers, agent_id)
    strict = _key(headers, agent_id, ["farm"])
    _set_state(agent_id, food=0, gold=500, energy=100)

    legacy_body = client.get("/agent/briefing", headers=legacy).json()["data"]
    legacy_types = {
        (row.get("body") or {}).get("action_type")
        for row in legacy_body["next_actions"]
    }
    assert "buy" in legacy_types and "scout" in legacy_types

    strict_body = client.get("/agent/briefing", headers=strict).json()["data"]
    strict_types = {
        (row.get("body") or {}).get("action_type")
        for row in strict_body["next_actions"]
    }
    assert "buy" not in strict_types
    assert "scout" not in strict_types
    assert "trade" not in strict_types


def test_claimable_quest_is_the_first_suggestion():
    headers = _register("briefing_quest")
    agent_id = _agent(headers, "QuestLord")
    key = _key(headers, agent_id)
    assert client.get("/agent/briefing", headers=key).status_code == 200

    db = SessionLocal()
    try:
        row = (
            db.query(AgentDailyQuest)
            .filter(AgentDailyQuest.agent_id == agent_id)
            .order_by(AgentDailyQuest.id)
            .first()
        )
        assert row is not None
        row.is_completed = True
        row.is_claimed = False
        db.commit()
        quest_id = row.id
    finally:
        db.close()

    body = client.get("/agent/briefing", headers=key).json()["data"]
    assert body["quests"]["claimable_count"] >= 1
    first = body["next_actions"][0]
    assert first["priority"] == 1
    assert first["path"] == f"/agent/quests/daily/{quest_id}/claim"


def test_world_briefing_is_public_and_pii_free():
    resp = client.get("/world/public/briefing?lang=zh")
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    for field in (
        "headline", "story_lines", "stats", "season", "market",
        "scout_today", "audience", "events", "update_revision", "app_version",
    ):
        assert field in body
    for secret in ("email", "owner_user_id", "password_hash", "claim_code"):
        assert secret not in resp.text


def test_briefing_is_discoverable_from_agent_docs():
    db = SessionLocal()
    try:
        payload = updates_service.build_updates_payload(db, "zh")
        assert "agent_briefing" in payload["docs"]
        assert "briefing" in payload["how_to_use_zh"].lower()
        assert "/agent/briefing" in updates_service.render_bulletin(db, "zh")
        assert "/agent/briefing" in updates_service.render_bulletin(db, "en")
    finally:
        db.close()

    assert client.get("/world/public/updates").status_code == 200
    skill = client.get("/skill.md?lang=zh")
    assert skill.status_code == 200
    assert "/agent/briefing" in skill.text
    api_md = client.get("/api.md")
    assert api_md.status_code == 200
    assert "/agent/briefing" in api_md.text


def test_latest_changelog_matches_app_version():
    db = SessionLocal()
    try:
        items = updates_service.build_updates_payload(db, "zh", limit=1)["items"]
    finally:
        db.close()
    assert items and items[0]["version"] == settings.app_version
