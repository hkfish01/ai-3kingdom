"""1.31.0 身分生命週期：註冊冪等、認領恢復、改名。"""

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Agent, AgentIdentity, User
from app.services.identity import backfill_identities, repair_claim_ownership

client = TestClient(app)


def _human(username: str, password: str = "Aa1234!!") -> tuple[str, dict]:
    reg = client.post(
        "/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": password},
    )
    assert reg.status_code == 200
    login = client.post("/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200
    token = login.json()["data"]["token"]
    return token, {"Authorization": f"Bearer {token}"}


def _bootstrap(name: str = "ZhaoYun", **extra) -> dict:
    resp = client.post("/automation/agent/bootstrap", json={"agent_name": name, **extra})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["registration_status"] == "created"
    return data


def _register_agent(headers: dict, name: str) -> int:
    resp = client.post("/agent/register", headers=headers, json={"name": name, "role": "平民"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["agent_id"]


def _agent_count() -> int:
    db = SessionLocal()
    try:
        return db.query(Agent).count()
    finally:
        db.close()


# ---------- 1) 防重複註冊 ----------

def test_bootstrap_resend_is_idempotent_without_request_id():
    first = _bootstrap("IdempotentLord")
    assert _agent_count() == 1

    again = client.post("/automation/agent/bootstrap", json={"agent_name": "IdempotentLord"})
    assert again.status_code == 200
    data = again.json()["data"]
    assert data["registration_status"] == "already_registered"
    assert data["agent"]["agent_id"] == first["agent"]["agent_id"]
    assert "claim_code" not in data  # 憑證绝不重送
    assert "/viewer/claim/recover" in data["recovery"]["with_api_key"]
    assert _agent_count() == 1


def test_bootstrap_request_id_is_stable_across_different_names():
    first = _bootstrap("OriginalName", request_id="fixed-client-0001")
    second = client.post(
        "/automation/agent/bootstrap",
        json={"agent_name": "DifferentName", "request_id": "fixed-client-0001"},
    )
    assert second.status_code == 200
    assert second.json()["data"]["registration_status"] == "already_registered"
    assert second.json()["data"]["agent"]["agent_id"] == first["agent"]["agent_id"]
    assert _agent_count() == 1

    third = _bootstrap("ThirdName", request_id="fixed-client-0002")
    assert third["agent"]["agent_id"] != first["agent"]["agent_id"]
    assert _agent_count() == 2


def test_manual_register_request_id_is_idempotent_but_display_names_may_duplicate():
    _, headers = _human("manual_user")
    first = _register_agent(headers, "ManualLord")

    repeat = client.post(
        "/agent/register", headers=headers, json={"name": "ManualLord2", "role": "平民", "request_id": "manual-0001"}
    )
    # 第一次帶 request_id 時會建立新 agent，重送才冪等。
    assert repeat.status_code == 200
    second_id = repeat.json()["data"]["agent_id"]
    replay = client.post(
        "/agent/register", headers=headers, json={"name": "TotallyDifferent", "role": "平民", "request_id": "manual-0001"}
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["registration_status"] == "already_registered"
    assert replay.json()["data"]["agent_id"] == second_id
    assert _agent_count() == 2

    # 沒帶 request_id 時維持既有語意：顯示名可重複，身分以憑證為準。
    duplicate_name = client.post("/agent/register", headers=headers, json={"name": "ManualLord", "role": "平民"})
    assert duplicate_name.status_code == 200
    assert duplicate_name.json()["data"]["agent_id"] not in (first, second_id)


def test_backfill_blocks_bootstrap_resend_for_legacy_agents():
    """升級前就存在的 agent 沒有指紋；回填後重送註冊也不能長出分身。"""
    boot = _bootstrap("LegacyLord")
    db = SessionLocal()
    try:
        db.query(AgentIdentity).filter(AgentIdentity.agent_id == boot["agent"]["agent_id"]).delete()
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        assert backfill_identities(db)["backfilled"] == 1
        db.commit()
    finally:
        db.close()

    resend = client.post("/automation/agent/bootstrap", json={"agent_name": "LegacyLord"})
    assert resend.status_code == 200
    data = resend.json()["data"]
    assert data["registration_status"] == "already_registered"
    assert data["agent"]["agent_id"] == boot["agent"]["agent_id"]
    assert _agent_count() == 1


# ---------- 2) claim code 找回 / 重新認領 ----------

def test_lost_claim_code_can_be_recovered_with_api_key():
    boot = _bootstrap("LostCodeLord")
    _, headers = _human("recover_human")

    candidates = client.get("/viewer/recovery/candidates?name=LostCode", headers=headers)
    assert candidates.status_code == 200
    items = candidates.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["agent_id"] == boot["agent"]["agent_id"]
    assert items[0]["is_claimed"] is False
    assert "claim_code" not in items[0]

    recover = client.post(
        "/viewer/claim/recover",
        headers=headers,
        json={"agent_id": boot["agent"]["agent_id"], "api_key": boot["api_key"]["key"]},
    )
    assert recover.status_code == 200, recover.text
    assert recover.json()["data"]["status"] == "claimed"

    claimed = client.get("/viewer/agents", headers=headers)
    assert [row["agent_id"] for row in claimed.json()["data"]["items"]] == [boot["agent"]["agent_id"]]


def test_recovery_rejects_wrong_key_name_or_agent_id():
    boot = _bootstrap("ProofLord")
    _, headers = _human("proof_human")

    bad_key = client.post(
        "/viewer/claim/recover", headers=headers, json={"agent_id": boot["agent"]["agent_id"], "api_key": "sk_wrong"}
    )
    assert bad_key.status_code == 403
    assert bad_key.json()["error"]["code"] == "IDENTITY_PROOF_INVALID"

    bad_id = client.post(
        "/viewer/claim/recover", headers=headers, json={"agent_id": 999999, "api_key": boot["api_key"]["key"]}
    )
    assert bad_id.status_code == 403

    bad_name = client.post(
        "/viewer/claim/recover",
        headers=headers,
        json={"agent_name": "SomeoneElse", "api_key": boot["api_key"]["key"]},
    )
    assert bad_name.status_code == 403


def test_recovery_transfers_a_claim_from_another_human():
    boot = _bootstrap("TransferLord")
    _, headers_a = _human("claim_user_a")
    assert client.post("/viewer/claim", headers=headers_a, json={"claim_code": boot["claim_code"]}).status_code == 200

    _, headers_b = _human("claim_user_b")
    recover = client.post(
        "/viewer/claim/recover",
        headers=headers_b,
        json={"agent_id": boot["agent"]["agent_id"], "api_key": boot["api_key"]["key"]},
    )
    assert recover.status_code == 200
    assert recover.json()["data"]["status"] == "transferred"
    assert recover.json()["data"]["transferred_from_another_user"] is True
    assert client.get("/viewer/agents", headers=headers_a).json()["data"]["items"] == []
    assert len(client.get("/viewer/agents", headers=headers_b).json()["data"]["items"]) == 1


def test_agent_can_reissue_claim_code_with_daily_limit():
    boot = _bootstrap("ReissueLord")
    key_headers = {"X-API-Key": boot["api_key"]["key"]}
    _, headers = _human("reissue_human")

    first = client.post("/agent/claim-code", headers=key_headers)
    assert first.status_code == 200, first.text
    new_code = first.json()["data"]["claim_code"]
    assert new_code != boot["claim_code"]

    old = client.post("/viewer/claim", headers=headers, json={"claim_code": boot["claim_code"]})
    assert old.status_code == 404
    assert old.json()["error"]["code"] == "CLAIM_CODE_INVALID"
    fresh = client.post("/viewer/claim", headers=headers, json={"claim_code": new_code})
    assert fresh.status_code == 200

    assert client.post("/agent/claim-code", headers=key_headers).status_code == 200
    assert client.post("/agent/claim-code", headers=key_headers).status_code == 200
    limited = client.post("/agent/claim-code", headers=key_headers)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "CLAIM_CODE_RATE_LIMITED"


def test_claim_does_not_break_the_original_agent_key():
    boot = _bootstrap("StillAutonomous")
    _, headers = _human("observing_human")
    assert client.post("/viewer/claim", headers=headers, json={"claim_code": boot["claim_code"]}).status_code == 200

    work = client.post(
        "/action/work", headers={"X-API-Key": boot["api_key"]["key"]}, json={"action_type": "farm", "payload": {}}
    )
    assert work.status_code == 200, work.text


def test_release_claim_and_repair_legacy_ownership():
    boot = _bootstrap("ReleaseLord")
    _, headers = _human("release_human")
    assert client.post("/viewer/claim", headers=headers, json={"claim_code": boot["claim_code"]}).status_code == 200

    # 模擬舊版認領把 owner 改給 human 的歷史資料。
    db = SessionLocal()
    try:
        human_id = db.query(User).filter(User.username == "release_human").first().id
        agent = db.get(Agent, boot["agent"]["agent_id"])
        agent.owner_user_id = human_id
        db.add(agent)
        db.commit()
    finally:
        db.close()

    repair = client.post("/admin/identity/repair-ownership", headers=headers)
    assert repair.status_code == 200, repair.text
    assert repair.json()["data"]["repaired"] == 1
    assert boot["agent"]["agent_id"] in repair.json()["data"]["agent_ids"]

    db = SessionLocal()
    try:
        agent = db.get(Agent, boot["agent"]["agent_id"])
        assert agent.owner_user_id != human_id
        assert repair_claim_ownership(db)["repaired"] == 0  # 冪等
        db.rollback()
    finally:
        db.close()

    released = client.post(f"/viewer/claim/{boot['agent']['agent_id']}/release", headers=headers)
    assert released.status_code == 200
    assert released.json()["data"]["released"] is True
    assert client.get("/viewer/agents", headers=headers).json()["data"]["items"] == []
    assert client.post(f"/viewer/claim/{boot['agent']['agent_id']}/release", headers=headers).status_code == 403


# ---------- 3) 改名 ----------

def test_agent_rename_is_unique_and_has_cooldown():
    boot = _bootstrap("OldName")
    _bootstrap("TakenName")
    key_headers = {"X-API-Key": boot["api_key"]["key"]}

    conflict = client.post("/agent/rename", headers=key_headers, json={"new_name": "TakenName"})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "AGENT_NAME_EXISTS"

    renamed = client.post("/agent/rename", headers=key_headers, json={"new_name": "BrandNewName"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["data"]["old_name"] == "OldName"
    assert renamed.json()["data"]["name"] == "BrandNewName"

    cooldown = client.post("/agent/rename", headers=key_headers, json={"new_name": "YetAnotherName"})
    assert cooldown.status_code == 429
    assert cooldown.json()["error"]["code"] == "RENAME_COOLDOWN"


def test_case_insensitive_name_conflict_is_rejected():
    boot = _bootstrap("CaseLord")
    other = _bootstrap("OtherLord")
    key_headers = {"X-API-Key": boot["api_key"]["key"]}
    _, headers = _human("rename_human")

    # 用 admin 端點測唯一性（不受 30 天冷卻限制）。
    assert client.patch(
        f"/admin/agents/{other['agent']['agent_id']}", headers=headers, json={"name": "caselord"}
    ).status_code == 409
    assert client.post("/agent/rename", headers=key_headers, json={"new_name": "OTHERLORD"}).status_code == 409
    blank = client.post("/agent/rename", headers=key_headers, json={"new_name": "   "})
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "INVALID_AGENT_NAME"


def test_viewer_rename_requires_a_claim():
    boot = _bootstrap("ViewerRename")
    _, headers_a = _human("viewer_rename_a")
    _, headers_b = _human("viewer_rename_b")

    blocked = client.post(
        f"/viewer/agent/{boot['agent']['agent_id']}/rename", headers=headers_a, json={"new_name": "NewTitle"}
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "AGENT_NOT_CLAIMED"

    assert client.post(
        "/viewer/claim/recover",
        headers=headers_b,
        json={"agent_id": boot["agent"]["agent_id"], "api_key": boot["api_key"]["key"]},
    ).status_code == 200
    renamed = client.post(
        f"/viewer/agent/{boot['agent']['agent_id']}/rename", headers=headers_b, json={"new_name": "NewTitle"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["data"]["name"] == "NewTitle"
