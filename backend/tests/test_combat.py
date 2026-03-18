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
