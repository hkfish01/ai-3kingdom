from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import Agent


client = TestClient(app)


def _auth_header(username: str = "fighter", password: str = "Aa1234!!") -> dict:
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


def _seed_agent(agent_id: int, infantry: int, archer: int, cavalry: int, gold: int, food: int, martial: int):
    with SessionLocal() as db:
        agent = db.get(Agent, agent_id)
        agent.infantry = infantry
        agent.archer = archer
        agent.cavalry = cavalry
        agent.gold = gold
        agent.food = food
        agent.martial = martial
        db.add(agent)
        db.commit()


def test_pve_dungeons_and_challenge_flow():
    headers = _auth_header("pve_user")
    agent_id = _register_agent(headers, "PveHero", "武將")
    _seed_agent(agent_id, infantry=60, archer=20, cavalry=5, gold=1000, food=1000, martial=60)

    list_resp = client.get("/pve/dungeons", headers=headers)
    assert list_resp.status_code == 200
    items = list_resp.json()["data"]["items"]
    assert len(items) >= 3

    challenge_resp = client.post(
        "/pve/challenge",
        headers=headers,
        json={
            "agent_id": agent_id,
            "dungeon_id": items[0]["id"],
            "troops": {"infantry": 30, "archer": 10, "cavalry": 5},
        },
    )
    assert challenge_resp.status_code == 200
    data = challenge_resp.json()["data"]
    losses = data["losses"]
    assert losses["infantry"] <= 30
    assert losses["archer"] <= 10
    assert losses["cavalry"] <= 5

    with SessionLocal() as db:
        agent = db.get(Agent, agent_id)
        assert agent.infantry == 60 - losses["infantry"]
        assert agent.archer == 20 - losses["archer"]
        assert agent.cavalry == 5 - losses["cavalry"]


def test_pvp_challenge_awards_spoils():
    attacker_headers = _auth_header("pvp_attacker")
    defender_headers = _auth_header("pvp_defender")
    attacker_id = _register_agent(attacker_headers, "Attacker", "武將")
    defender_id = _register_agent(defender_headers, "Defender", "武將")
    _seed_agent(attacker_id, infantry=200, archer=80, cavalry=40, gold=2000, food=2000, martial=85)
    _seed_agent(defender_id, infantry=40, archer=10, cavalry=5, gold=800, food=600, martial=35)

    resp = client.post(
        "/pvp/challenge",
        headers=attacker_headers,
        json={
            "attacker_id": attacker_id,
            "defender_id": defender_id,
            "troops": {"infantry": 120, "archer": 60, "cavalry": 30},
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["attacker_win"] is True
    spoils = data["spoils"]
    assert spoils["gold"] >= 0
    assert spoils["food"] >= 0

    with SessionLocal() as db:
        attacker = db.get(Agent, attacker_id)
        defender = db.get(Agent, defender_id)
        assert attacker.gold >= 2000 + spoils["gold"]
        assert attacker.food >= 2000 + spoils["food"]
        assert defender.gold <= 800 - spoils["gold"]
        assert defender.food <= 600 - spoils["food"]


def test_pve_power_requirement_and_first_clear_reward_once():
    headers = _auth_header("pve_power_gate")
    agent_id = _register_agent(headers, "GateHero", "武將")
    _seed_agent(agent_id, infantry=20, archer=5, cavalry=1, gold=1000, food=1000, martial=30)

    too_low = client.post(
        "/pve/challenge",
        headers=headers,
        json={
            "agent_id": agent_id,
            "dungeon_id": "hulao",
            "troops": {"infantry": 20, "archer": 5, "cavalry": 1},
        },
    )
    assert too_low.status_code == 422
    assert too_low.json()["error"]["code"] == "PVE_POWER_TOO_LOW"

    _seed_agent(agent_id, infantry=400, archer=200, cavalry=100, gold=1000, food=1000, martial=95)
    first = client.post(
        "/pve/challenge",
        headers=headers,
        json={
            "agent_id": agent_id,
            "dungeon_id": "huangjin",
            "troops": {"infantry": 200, "archer": 100, "cavalry": 50},
        },
    )
    assert first.status_code == 200
    first_data = first.json()["data"]
    assert first_data["win"] is True
    assert 600 <= first_data["rewards"]["gold"] <= 700

    second = client.post(
        "/pve/challenge",
        headers=headers,
        json={
            "agent_id": agent_id,
            "dungeon_id": "huangjin",
            "troops": {"infantry": 200, "archer": 100, "cavalry": 50},
        },
    )
    assert second.status_code == 200
    second_data = second.json()["data"]
    assert second_data["win"] is True
    assert 100 <= second_data["rewards"]["gold"] <= 200


def test_pvp_daily_limit_and_target_protection():
    attacker_headers = _auth_header("pvp_limit_attacker")
    attacker_id = _register_agent(attacker_headers, "LimitAttacker", "武將")
    _seed_agent(attacker_id, infantry=600, archer=250, cavalry=120, gold=3000, food=3000, martial=95)

    defender_ids: list[int] = []
    for i in range(1, 7):
        headers = _auth_header(f"pvp_limit_def_{i}")
        defender_id = _register_agent(headers, f"LimitDef{i}", "武將")
        _seed_agent(defender_id, infantry=40, archer=20, cavalry=10, gold=900, food=900, martial=30)
        defender_ids.append(defender_id)

    first = client.post(
        "/pvp/challenge",
        headers=attacker_headers,
        json={
            "attacker_id": attacker_id,
            "defender_id": defender_ids[0],
            "troops": {"infantry": 250, "archer": 120, "cavalry": 60},
        },
    )
    assert first.status_code == 200
    assert first.json()["data"]["daily_used"] == 1

    protected = client.post(
        "/pvp/challenge",
        headers=attacker_headers,
        json={
            "attacker_id": attacker_id,
            "defender_id": defender_ids[0],
            "troops": {"infantry": 250, "archer": 120, "cavalry": 60},
        },
    )
    assert protected.status_code == 422
    assert protected.json()["error"]["code"] == "PVP_TARGET_PROTECTED"

    for idx in range(1, 5):
        ok = client.post(
            "/pvp/challenge",
            headers=attacker_headers,
            json={
                "attacker_id": attacker_id,
                "defender_id": defender_ids[idx],
                "troops": {"infantry": 250, "archer": 120, "cavalry": 60},
            },
        )
        assert ok.status_code == 200

    limit_hit = client.post(
        "/pvp/challenge",
        headers=attacker_headers,
        json={
            "attacker_id": attacker_id,
            "defender_id": defender_ids[5],
            "troops": {"infantry": 250, "archer": 120, "cavalry": 60},
        },
    )
    assert limit_hit.status_code == 422
    assert limit_hit.json()["error"]["code"] == "PVP_DAILY_LIMIT_REACHED"


def test_pvp_opponents_enforces_rank_window():
    attacker_headers = _auth_header("pvp_rank_attacker")
    attacker_id = _register_agent(attacker_headers, "RankAttacker", "武將")
    _seed_agent(attacker_id, infantry=200, archer=100, cavalry=50, gold=1500, food=1500, martial=70)

    for i in range(1, 15):
        headers = _auth_header(f"pvp_rank_def_{i}")
        defender_id = _register_agent(headers, f"RankDef{i}", "武將")
        _seed_agent(
            defender_id,
            infantry=max(10, 250 - i * 12),
            archer=max(5, 120 - i * 6),
            cavalry=max(2, 60 - i * 3),
            gold=1000,
            food=1000,
            martial=max(20, 80 - i),
        )

    resp = client.get(f"/pvp/opponents?agent_id={attacker_id}", headers=attacker_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["daily_limit"] == 5
    assert "daily_used" in data and "daily_remaining" in data
    attacker_rank = data["attacker_rank"]
    for row in data["items"]:
        assert abs(row["rank"] - attacker_rank) <= 10


def test_pvp_opponents_matchmaking_fields_and_priority():
    attacker_headers = _auth_header("pvp_mm_attacker")
    attacker_id = _register_agent(attacker_headers, "MMAttacker", "武將")
    _seed_agent(attacker_id, infantry=120, archer=60, cavalry=24, gold=1500, food=1500, martial=70)

    balanced_headers = _auth_header("pvp_mm_balanced")
    balanced_id = _register_agent(balanced_headers, "MMBalanced", "武將")
    _seed_agent(balanced_id, infantry=115, archer=55, cavalry=22, gold=1000, food=1000, martial=68)

    weak_headers = _auth_header("pvp_mm_weak")
    weak_id = _register_agent(weak_headers, "MMWeak", "武將")
    _seed_agent(weak_id, infantry=20, archer=8, cavalry=2, gold=1000, food=1000, martial=25)

    strong_headers = _auth_header("pvp_mm_strong")
    strong_id = _register_agent(strong_headers, "MMStrong", "武將")
    _seed_agent(strong_id, infantry=350, archer=170, cavalry=90, gold=1000, food=1000, martial=95)

    resp = client.get(f"/pvp/opponents?agent_id={attacker_id}", headers=attacker_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["matchmaking_target_win_rate"]["min"] == 0.4
    assert data["matchmaking_target_win_rate"]["max"] == 0.6
    assert "attacker_power" in data
    assert len(data["items"]) >= 3

    top = data["items"][0]
    assert top["agent_id"] == balanced_id
    assert 0.0 <= top["estimated_win_rate"] <= 1.0
    ids = [row["agent_id"] for row in data["items"]]
    assert weak_id in ids
    assert strong_id in ids


def test_battle_reports_and_replay_endpoints():
    attacker_headers = _auth_header("pvp_report_attacker")
    defender_headers = _auth_header("pvp_report_defender")
    attacker_id = _register_agent(attacker_headers, "ReportAttacker", "武將")
    defender_id = _register_agent(defender_headers, "ReportDefender", "武將")
    _seed_agent(attacker_id, infantry=220, archer=90, cavalry=35, gold=2200, food=1800, martial=82)
    _seed_agent(defender_id, infantry=90, archer=35, cavalry=12, gold=1400, food=1400, martial=55)

    challenge = client.post(
        "/pvp/challenge",
        headers=attacker_headers,
        json={
            "attacker_id": attacker_id,
            "defender_id": defender_id,
            "troops": {"infantry": 120, "archer": 55, "cavalry": 22},
        },
    )
    assert challenge.status_code == 200
    battle_id = challenge.json()["data"]["battle_id"]

    reports = client.get(f"/battle/reports?agent_id={attacker_id}&mode=pvp", headers=attacker_headers)
    assert reports.status_code == 200
    items = reports.json()["data"]["items"]
    assert any(item["battle_id"] == battle_id for item in items)
    report = next(item for item in items if item["battle_id"] == battle_id)
    assert report["replay_url"] == f"/api/battle/replay/{battle_id}"

    replay = client.get(f"/battle/replay/{battle_id}", headers=attacker_headers)
    assert replay.status_code == 200
    replay_data = replay.json()["data"]
    assert replay_data["mode"] == "pvp"
    assert replay_data["summary"]["attacker_agent_id"] == attacker_id
    assert replay_data["summary"]["defender_agent_id"] == defender_id
    assert len(replay_data["rounds"]) == 3
    for idx, row in enumerate(replay_data["rounds"], start=1):
        assert row["round"] == idx
        assert "casualties" in row
        assert "attacker" in row["casualties"]
        assert "defender" in row["casualties"]
