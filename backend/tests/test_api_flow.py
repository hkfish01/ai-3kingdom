from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.db import SessionLocal
from app.models import Agent, SystemState, User


client = TestClient(app)


def _auth_header(username: str = "cao", password: str = "Aa1234!!") -> dict:
    register_resp = client.post(
        "/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": password},
    )
    assert register_resp.status_code == 200
    login_resp = client.post("/auth/login", json={"username": username, "password": password})
    token = login_resp.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def _register_agent(headers: dict, name: str, role: str) -> int:
    resp = client.post("/agent/register", headers=headers, json={"name": name, "role": role})
    assert resp.status_code == 200
    return resp.json()["data"]["agent_id"]


def test_end_to_end_mvp_flow():
    headers = _auth_header()
    agent_id = _register_agent(headers, "ZhugeLiang", "文臣")

    work_resp = client.post("/action/work", headers=headers, json={"agent_id": agent_id, "task": "farm"})
    assert work_resp.status_code == 200
    assert work_resp.json()["data"]["food_gained"] == 40

    train_resp = client.post(
        "/action/train",
        headers=headers,
        json={"agent_id": agent_id, "troop_type": "infantry", "quantity": 1},
    )
    assert train_resp.status_code == 200

    status_resp = client.get(f"/agent/status?agent_id={agent_id}", headers=headers)
    assert status_resp.status_code == 200
    body = status_resp.json()["data"]
    assert body["troops"]["infantry"] == 1

    world_resp = client.get("/world/state", headers=headers)
    assert world_resp.status_code == 200
    assert world_resp.json()["data"]["agent_count"] == 1

    chronicle_zh = client.get("/world/chronicle?limit=10&lang=zh", headers=headers)
    assert chronicle_zh.status_code == 200
    entries = chronicle_zh.json()["data"]["entries"]
    assert len(entries) >= 1
    assert "event_type_localized" in entries[0]
    assert "title_localized" in entries[0]
    assert "content_localized" in entries[0]


def test_social_politics_and_faction_flow():
    lord_headers = _auth_header("liu", "Aa1234!!")
    vassal_headers = _auth_header("sun", "Aa1234!!")

    lord_agent_id = _register_agent(lord_headers, "LiuBei", "君主")
    vassal_agent_id = _register_agent(vassal_headers, "ZhaoYun", "武將")
    create_faction_resp = client.post("/social/faction/create", headers=lord_headers, json={"name": "Shu", "leader_agent_id": lord_agent_id})
    assert create_faction_resp.status_code == 403

    join_resp = client.post(
        "/social/join-lord",
        headers=vassal_headers,
        json={"agent_id": vassal_agent_id, "lord_agent_id": lord_agent_id},
    )
    assert join_resp.status_code == 200
    assert join_resp.json()["data"]["lord_agent_id"] == lord_agent_id

    # Trade: base gold 80, city tax 4 => 76, vassal gets +1% (min 1), lord gets +0.1% (min 1).
    work_resp = client.post(
        "/action/work",
        headers=vassal_headers,
        json={"agent_id": vassal_agent_id, "task": "trade"},
    )
    assert work_resp.status_code == 200
    assert work_resp.json()["data"]["gold_gained"] == 77
    assert work_resp.json()["data"]["lord_bonus_to_vassal_gold"] == 1
    assert work_resp.json()["data"]["vassal_bonus_to_lord_gold"] == 1

    lord_status = client.get(f"/agent/status?agent_id={lord_agent_id}", headers=lord_headers)
    vassal_status = client.get(f"/agent/status?agent_id={vassal_agent_id}", headers=vassal_headers)
    assert lord_status.status_code == 200
    assert vassal_status.status_code == 200
    assert lord_status.json()["data"]["gold"] == 101
    assert vassal_status.json()["data"]["gold"] == 177

    message_resp = client.post(
        "/social/message",
        headers=vassal_headers,
        json={
            "from_agent_id": vassal_agent_id,
            "to_agent_id": lord_agent_id,
            "message_type": "alliance_proposal",
            "content": "I will follow your command.",
        },
    )
    assert message_resp.status_code == 200
    assert message_resp.json()["data"]["status"] == "pending"

    messages_resp = client.get(f"/social/messages?agent_id={vassal_agent_id}", headers=vassal_headers)
    assert messages_resp.status_code == 200
    assert len(messages_resp.json()["data"]["messages"]) == 1

    dialogues_resp = client.get("/social/dialogues?limit=20", headers=vassal_headers)
    assert dialogues_resp.status_code == 200
    assert len(dialogues_resp.json()["data"]["messages"]) >= 1

    factions_resp = client.get("/social/factions", headers=lord_headers)
    assert factions_resp.status_code == 200
    assert len(factions_resp.json()["data"]["factions"]) == 0


def test_role_restriction_and_central_register_config():
    headers = _auth_header("role_tester", "Aa1234!!")
    create_resp = client.post("/agent/register", headers=headers, json={"name": "TestRoleAgent", "role": "raider"})
    assert create_resp.status_code == 200
    assert create_resp.json()["data"]["role"] == "平民"

    register_central_resp = client.post("/discovery/register-central")
    assert register_central_resp.status_code == 422


def test_world_public_readonly_endpoints_without_auth():
    public_state = client.get("/world/public/state")
    assert public_state.status_code == 200
    assert "city" in public_state.json()["data"]

    public_rankings = client.get("/world/public/rankings")
    assert public_rankings.status_code == 200
    assert "top_agents_by_gold" in public_rankings.json()["data"]

    private_state = client.get("/world/state")
    assert private_state.status_code == 401

    private_rankings = client.get("/world/rankings")
    assert private_rankings.status_code == 401


def test_city_roster_endpoint_with_positions():
    headers = _auth_header("roster_user", "Aa1234!!")
    _register_agent(headers, "RosterAgentA", "君主")
    roster_resp = client.get("/world/city/roster", headers=headers)
    assert roster_resp.status_code == 200
    data = roster_resp.json()["data"]
    assert "civil_hierarchy" in data
    assert "military_hierarchy" in data
    assert len(data["agents"]) >= 1


def test_central_roles_policy_pull_and_enforcement(monkeypatch):
    old_url = settings.central_roles_policy_url
    old_required = settings.central_roles_policy_required
    try:
        settings.central_roles_policy_url = "https://central.example.com/policy/roles"
        settings.central_roles_policy_required = False

        def fake_get_json(_: str, __: str = ""):
            return 200, {"roles": ["學生"], "version": "v-central-1"}

        monkeypatch.setattr("app.api.routes_discovery.get_json", fake_get_json)

        pull_resp = client.post("/discovery/central/policy/roles/pull")
        assert pull_resp.status_code == 200
        assert pull_resp.json()["data"]["roles_count"] == 1

        headers = _auth_header("central_role_user", "Aa1234!!")
        ok_resp = client.post("/agent/register", headers=headers, json={"name": "CentralRoleA", "role": "君主"})
        assert ok_resp.status_code == 200
        agent_id = ok_resp.json()["data"]["agent_id"]
        assert ok_resp.json()["data"]["role"] == "平民"

        promote_ok = client.post("/agent/promote", headers=headers, json={"agent_id": agent_id, "target_role": "學生"})
        assert promote_ok.status_code == 200

        blocked_resp = client.post("/agent/promote", headers=headers, json={"agent_id": agent_id, "target_role": "君主"})
        assert blocked_resp.status_code == 422

        db = SessionLocal()
        try:
            row = db.get(SystemState, "central.roles.policy")
            if row:
                db.delete(row)
            db.commit()
        finally:
            db.close()

        settings.central_roles_policy_required = True
        blocked_by_required = client.post(
            "/agent/promote",
            headers=headers,
            json={"agent_id": agent_id, "target_role": "學生"},
        )
        assert blocked_by_required.status_code == 422
    finally:
        settings.central_roles_policy_url = old_url
        settings.central_roles_policy_required = old_required


def test_forgot_and_reset_password_flow(monkeypatch):
    username = "reset_user"
    email = "reset_user@example.com"
    old_password = "Aa1234!!"
    new_password = "Bb1234@@"

    reg = client.post("/auth/register", json={"username": username, "email": email, "password": old_password})
    assert reg.status_code == 200

    sent = {"code": ""}

    def fake_send(to_email: str, reset_code: str):
        assert to_email == email
        sent["code"] = reset_code

    monkeypatch.setattr("app.api.routes_auth.send_password_reset_email", fake_send)

    forgot = client.post("/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 200
    assert len(sent["code"]) == 6

    reset = client.post("/auth/reset-password", json={"email": email, "code": sent["code"], "new_password": new_password})
    assert reset.status_code == 200

    old_login = client.post("/auth/login", json={"username": username, "password": old_password})
    assert old_login.status_code == 401

    new_login = client.post("/auth/login", json={"username": username, "password": new_password})
    assert new_login.status_code == 200


def test_admin_overview_delete_and_reset_user_password():
    admin_headers = _auth_header("admin_root", "Aa1234!!")
    user_headers = _auth_header("normal_user", "Aa1234!!")
    _ = user_headers

    db = SessionLocal()
    try:
        normal_user = db.query(User).filter(User.username == "normal_user").first()
        assert normal_user is not None
        agent = Agent(
            owner_user_id=normal_user.id,
            name="NormalAgent",
            role="平民",
            home_city=settings.city_name,
            current_city=settings.city_name,
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
        normal_user_id = normal_user.id
        normal_agent_id = agent.id
    finally:
        db.close()

    overview = client.get("/admin/overview", headers=admin_headers)
    assert overview.status_code == 200
    assert any(u["id"] == normal_user_id for u in overview.json()["data"]["users"])
    assert any(a["id"] == normal_agent_id for a in overview.json()["data"]["agents"])

    reset = client.post(
        f"/admin/users/{normal_user_id}/reset-password",
        headers=admin_headers,
        json={"new_password": "Cc1234##"},
    )
    assert reset.status_code == 200

    old_login = client.post("/auth/login", json={"username": "normal_user", "password": "Aa1234!!"})
    assert old_login.status_code == 401
    new_login = client.post("/auth/login", json={"username": "normal_user", "password": "Cc1234##"})
    assert new_login.status_code == 200

    del_agent = client.delete(f"/admin/agents/{normal_agent_id}", headers=admin_headers)
    assert del_agent.status_code == 200

    del_user = client.delete(f"/admin/users/{normal_user_id}", headers=admin_headers)
    assert del_user.status_code == 200


def test_admin_users_agents_pagination_and_update():
    admin_headers = _auth_header("admin_manage", "Aa1234!!")
    user_headers = _auth_header("managed_user", "Aa1234!!")
    aid = _register_agent(user_headers, "ManagedA", "平民")

    users_page = client.get("/admin/users?page=1&page_size=1&query=managed", headers=admin_headers)
    assert users_page.status_code == 200
    assert users_page.json()["data"]["total"] >= 1

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == "managed_user").first()
        assert u is not None
        uid = u.id
    finally:
        db.close()

    patch_user = client.patch(
        f"/admin/users/{uid}",
        headers=admin_headers,
        json={"email": "managed_user_new@example.com", "is_admin": False},
    )
    assert patch_user.status_code == 200
    assert patch_user.json()["data"]["email"] == "managed_user_new@example.com"

    agents_page = client.get("/admin/agents?page=1&page_size=1&query=ManagedA", headers=admin_headers)
    assert agents_page.status_code == 200
    assert agents_page.json()["data"]["total"] >= 1

    patch_agent = client.patch(
        f"/admin/agents/{aid}",
        headers=admin_headers,
        json={"name": "ManagedB", "gold": 777},
    )
    assert patch_agent.status_code == 200
    assert patch_agent.json()["data"]["name"] == "ManagedB"


def test_agent_display_name_can_duplicate_but_user_id_unique():
    h1 = _auth_header("dup_user_a", "Aa1234!!")
    h2 = _auth_header("dup_user_b", "Aa1234!!")
    same_name = "SameDisplayName"

    r1 = client.post("/agent/register", headers=h1, json={"name": same_name, "role": "平民"})
    r2 = client.post("/agent/register", headers=h2, json={"name": same_name, "role": "平民"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["data"]["agent_id"] != r2.json()["data"]["agent_id"]


def test_regenerate_claim_code_without_deleting_agent():
    resp = client.post(
        "/automation/agent/bootstrap",
        json={"agent_name": "ReclaimAgent", "key_name": "reclaim-key"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    token = data["token"]
    aid = data["agent"]["agent_id"]
    first_code = data["claim_code"]

    regen = client.post(
        f"/automation/agent/{aid}/claim-code/regenerate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert regen.status_code == 200
    regen_data = regen.json()["data"]
    assert regen_data["agent_id"] == aid
    assert regen_data["claim_code"] != first_code
    assert 50 <= regen_data["abilities"]["martial"] <= 99


def test_role_slot_limit_is_enforced():
    h1 = _auth_header("slot_user_a", "Aa1234!!")
    h2 = _auth_header("slot_user_b", "Aa1234!!")
    a1 = _register_agent(h1, "SlotA", "平民")
    a2 = _register_agent(h2, "SlotB", "平民")

    db = SessionLocal()
    try:
        ag1 = db.get(Agent, a1)
        ag2 = db.get(Agent, a2)
        assert ag1 and ag2
        ag1.gold = 5000
        ag2.gold = 5000
        db.add(ag1)
        db.add(ag2)
        db.commit()
    finally:
        db.close()

    p1 = client.post("/agent/promote", headers=h1, json={"agent_id": a1, "target_role": "太傅"})
    assert p1.status_code == 200
    p2 = client.post("/agent/promote", headers=h2, json={"agent_id": a2, "target_role": "太傅"})
    assert p2.status_code == 422
    assert p2.json()["error"]["code"] == "ROLE_SLOTS_FULL"


def test_admin_can_regenerate_claim_and_update_expiry():
    admin_headers = _auth_header("admin_claim", "Aa1234!!")

    bootstrap = client.post(
        "/automation/agent/bootstrap",
        json={"agent_name": "AdminClaimAgent", "key_name": "adm-claim-key"},
    )
    assert bootstrap.status_code == 200
    agent_id = bootstrap.json()["data"]["agent"]["agent_id"]

    regen = client.post(f"/admin/agents/{agent_id}/claim-code/regenerate", headers=admin_headers)
    assert regen.status_code == 200
    regen_data = regen.json()["data"]
    assert regen_data["agent_id"] == agent_id
    assert len(regen_data["claim_code"]) >= 12

    future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    update = client.post(
        f"/admin/agents/{agent_id}/claim-expiry",
        headers=admin_headers,
        json={"expires_at": future},
    )
    assert update.status_code == 200
    update_data = update.json()["data"]
    assert update_data["agent_id"] == agent_id
    assert update_data["created_new_ticket"] is False

    overview = client.get("/admin/overview", headers=admin_headers)
    assert overview.status_code == 200
    row = next((a for a in overview.json()["data"]["agents"] if a["id"] == agent_id), None)
    assert row is not None
    assert row["claim_code"] == "******"
    assert row["claim_expires_at"] is not None


def test_agent_inbox_orders_unread_and_unreplied_first():
    a_headers = _auth_header("inbox_a", "Aa1234!!")
    b_headers = _auth_header("inbox_b", "Aa1234!!")
    c_headers = _auth_header("inbox_c", "Aa1234!!")

    a_id = _register_agent(a_headers, "InboxA", "平民")
    b_id = _register_agent(b_headers, "InboxB", "平民")
    c_id = _register_agent(c_headers, "InboxC", "平民")

    msg1 = client.post(
        "/social/message",
        headers=b_headers,
        json={"from_agent_id": b_id, "to_agent_id": a_id, "message_type": "task", "content": "pending-1"},
    )
    assert msg1.status_code == 200
    msg2 = client.post(
        "/social/message",
        headers=b_headers,
        json={"from_agent_id": b_id, "to_agent_id": a_id, "message_type": "task", "content": "pending-2"},
    )
    assert msg2.status_code == 200
    msg3 = client.post(
        "/social/message",
        headers=c_headers,
        json={"from_agent_id": c_id, "to_agent_id": a_id, "message_type": "task", "content": "older"},
    )
    assert msg3.status_code == 200

    # A replies to C, so C-thread should no longer be unreplied.
    reply_c = client.post(
        "/social/inbox/reply",
        headers=a_headers,
        json={"from_agent_id": a_id, "to_agent_id": c_id, "content": "ack"},
    )
    assert reply_c.status_code == 200

    inbox = client.get(f"/social/inbox?agent_id={a_id}", headers=a_headers)
    assert inbox.status_code == 200
    items = inbox.json()["data"]["items"]
    assert len(items) >= 2
    assert items[0]["peer_agent_id"] == b_id
    assert items[0]["unread_count"] >= 2
    assert items[0]["unreplied_count"] >= 2
    assert items[0]["thread_status"] == "unreplied"

    history = client.get(f"/social/inbox/history?agent_id={a_id}&peer_agent_id={b_id}&mark_read=true", headers=a_headers)
    assert history.status_code == 200

    inbox_after = client.get(f"/social/inbox?agent_id={a_id}", headers=a_headers)
    assert inbox_after.status_code == 200
    row_b = next(i for i in inbox_after.json()["data"]["items"] if i["peer_agent_id"] == b_id)
    assert row_b["unread_count"] == 0
    assert row_b["thread_status"] == "unreplied"


def test_admin_can_manage_announcements():
    admin_headers = _auth_header("admin_notice", "Aa1234!!")
    create = client.post(
        "/admin/announcements",
        headers=admin_headers,
        json={"title": "Maintenance", "content": "Server restart at UTC 02:00", "published": True},
    )
    assert create.status_code == 200
    aid = create.json()["data"]["id"]

    pub = client.get("/world/public/announcements")
    assert pub.status_code == 200
    assert any(x["id"] == aid for x in pub.json()["data"]["items"])

    update = client.patch(
        f"/admin/announcements/{aid}",
        headers=admin_headers,
        json={"published": False},
    )
    assert update.status_code == 200
    assert update.json()["data"]["published"] is False

    pub2 = client.get("/world/public/announcements")
    assert pub2.status_code == 200
    assert all(x["id"] != aid for x in pub2.json()["data"]["items"])

    delete = client.delete(f"/admin/announcements/{aid}", headers=admin_headers)
    assert delete.status_code == 200
