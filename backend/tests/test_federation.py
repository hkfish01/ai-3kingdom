from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.federation_security import make_signature


client = TestClient(app)


def _auth_header(username: str = "fed_admin", password: str = "Aa1234!!") -> dict:
    register_resp = client.post(
        "/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": password},
    )
    assert register_resp.status_code == 200
    login_resp = client.post("/auth/login", json={"username": username, "password": password})
    token = login_resp.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def _fed_headers(payload: dict, secret: str = "federation-dev-secret", nonce: str = "n-1") -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    sig = make_signature(secret, ts, nonce, payload)
    return {
        "X-Fed-Signature": sig,
        "X-Fed-Timestamp": ts,
        "X-Fed-Nonce": nonce,
    }


def test_federation_hello_attack_migrate_and_replay_guard():
    auth = _auth_header()

    bootstrap = client.post("/admin/bootstrap", headers=auth)
    assert bootstrap.status_code == 200

    legacy_status = client.get("/federation/status")
    assert legacy_status.status_code == 200

    hello_payload = {
        "request_id": "req-hello-001",
        "city_name": "ChengDu",
        "base_url": "https://chengdu.example.com",
        "public_key": "pubkey",
        "shared_secret": "federation-dev-secret",
        "protocol_version": "1.0",
        "rule_version": "1.0",
    }
    hello_resp = client.post("/federation/v1/hello", json=hello_payload, headers=_fed_headers(hello_payload, nonce="h1"))
    assert hello_resp.status_code == 200

    peers_resp = client.get("/federation/v1/peers")
    assert peers_resp.status_code == 200
    assert len(peers_resp.json()["data"]["peers"]) == 1

    cities_resp = client.get("/federation/cities")
    assert cities_resp.status_code == 200
    assert len(cities_resp.json()["data"]["cities"]) >= 1

    attack_payload = {
        "request_id": "req-attack-001",
        "from_city": "ChengDu",
        "target_city": settings.city_name,
        "troops": {"infantry": 50, "archer": 20, "cavalry": 10},
    }
    attack_resp = client.post(
        "/federation/v1/attack",
        json=attack_payload,
        headers=_fed_headers(attack_payload, nonce="a1"),
    )
    assert attack_resp.status_code == 200
    assert "outcome" in attack_resp.json()["data"]

    replay_resp = client.post(
        "/federation/v1/attack",
        json=attack_payload,
        headers=_fed_headers(attack_payload, nonce="a2"),
    )
    assert replay_resp.status_code == 409
    assert replay_resp.json()["error"]["code"] == "FEDERATION_REPLAY"

    migrate_payload = {
        "request_id": "req-migrate-001",
        "from_city": "ChengDu",
        "to_city": settings.city_name,
        "agent_name": "GanNing",
        "role": "武將",
        "gold": 200,
        "food": 150,
        "infantry": 10,
        "archer": 5,
        "cavalry": 2,
        "reputation": 12,
    }
    migrate_resp = client.post(
        "/federation/v1/migrate",
        json=migrate_payload,
        headers=_fed_headers(migrate_payload, nonce="m1"),
    )
    assert migrate_resp.status_code == 200
    assert migrate_resp.json()["data"]["status"] == "accepted"

    city_migrations = client.get("/city/migrations", headers=auth)
    assert city_migrations.status_code == 200
    assert len(city_migrations.json()["data"]["migrations"]) == 1
