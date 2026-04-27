from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _register_and_login(username: str, password: str) -> str:
    reg = client.post("/auth/register", json={"username": username, "email": f"{username}@example.com", "password": password})
    assert reg.status_code == 200
    login = client.post("/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200
    return login.json()["data"]["token"]


def _register_agent(headers: dict, name: str = "ApiKeyAgent", role: str = "平民") -> int:
    resp = client.post("/agent/register", headers=headers, json={"name": name, "role": role})
    assert resp.status_code == 200
    return resp.json()["data"]["agent_id"]


def test_api_key_persistence_and_revoke():
    token = _register_and_login("apikey_user", "Aa1234!!")
    headers = {"Authorization": f"Bearer {token}"}
    agent_id = _register_agent(headers)

    create_resp = client.post("/api-keys", headers=headers, json={"name": "OpenClaw Main Key", "agent_id": agent_id})
    assert create_resp.status_code == 200
    created_id = create_resp.json()["data"]["id"]
    assert create_resp.json()["data"]["key"].startswith("sk_")

    list_resp = client.get("/api-keys", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()["data"]["items"]) == 1
    assert list_resp.json()["data"]["items"][0]["revoked"] is False

    revoke_resp = client.delete(f"/api-keys/{created_id}", headers=headers)
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["data"]["revoked"] is True

    list_after = client.get("/api-keys", headers=headers)
    assert list_after.status_code == 200
    assert list_after.json()["data"]["items"][0]["revoked"] is True


def test_ai_bootstrap_and_human_claim_read_only():
    bootstrap = client.post(
        "/automation/agent/bootstrap",
        json={
            "agent_name": "LiuBei",
            "role": "lord",
            "faction_name": "Shu",
            "key_name": "OpenClaw Key",
        },
    )
    assert bootstrap.status_code == 200
    data = bootstrap.json()["data"]
    claim_code = data["claim_code"]
    agent_id = data["agent"]["agent_id"]

    human_token = _register_and_login("human_viewer", "Aa1234!!")
    human_headers = {"Authorization": f"Bearer {human_token}"}

    claim_resp = client.post("/viewer/claim", headers=human_headers, json={"claim_code": claim_code})
    assert claim_resp.status_code == 200
    assert claim_resp.json()["data"]["agent_id"] == agent_id

    claimed = client.get("/viewer/agents", headers=human_headers)
    assert claimed.status_code == 200
    assert claimed.json()["data"]["items"][0]["agent_id"] == agent_id

    overview = client.get(f"/viewer/agent/{agent_id}/overview", headers=human_headers)
    assert overview.status_code == 200
    assert overview.json()["data"]["agent"]["id"] == agent_id

    human_key_resp = client.post(
        "/api-keys",
        headers=human_headers,
        json={"name": "Claimed Agent Key", "agent_id": agent_id, "allowed_actions": ["farm", "move"]},
    )
    assert human_key_resp.status_code == 200
    human_api_headers = {"X-API-Key": human_key_resp.json()["data"]["key"]}

    # Human can view and control with own agent-bound API key.
    human_work = client.post("/action/work", headers=human_api_headers, json={"action_type": "farm", "payload": {}})
    assert human_work.status_code == 200  # After claim, human can now control

    # After human claims, AI old key should no longer have control.
    ai_api_key = data["api_key"]["key"]
    ai_work = client.post("/action/work", headers={"X-API-Key": ai_api_key}, json={"action_type": "farm", "payload": {}})
    assert ai_work.status_code == 403  # AI no longer owns the agent after human claims

    peer_token = _register_and_login("dialog_peer", "Aa1234!!")
    peer_agent = client.post(
        "/agent/register",
        headers={"Authorization": f"Bearer {peer_token}"},
        json={"name": "PeerAgent", "role": "平民"},
    )
    assert peer_agent.status_code == 200
    peer_agent_id = peer_agent.json()["data"]["agent_id"]

    seed_msg = client.post(
        "/social/message",
        headers={"Authorization": f"Bearer {peer_token}"},
        json={
            "from_agent_id": peer_agent_id,
            "to_agent_id": agent_id,
            "message_type": "task",
            "content": "seed dialogue",
        },
    )
    assert seed_msg.status_code == 200

    inbox = client.get(f"/viewer/dialogues/inbox?agent_id={agent_id}", headers=human_headers)
    assert inbox.status_code == 200
    assert len(inbox.json()["data"]["items"]) >= 1
    history = client.get(
        f"/viewer/dialogues/history?agent_id={agent_id}&peer_agent_id={peer_agent_id}",
        headers=human_headers,
    )
    assert history.status_code == 200
    assert len(history.json()["data"]["messages"]) >= 1
