#!/usr/bin/env python3
import hashlib
import hmac
import json
import secrets
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone


SHARED_SECRET = "federation-dev-secret"
CITY_A = "http://localhost:8100"
CITY_B = "http://localhost:8200"


def stable_body(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def sign(secret: str, timestamp: str, nonce: str, payload: dict) -> str:
    msg = f"{timestamp}.{nonce}.{stable_body(payload)}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def _request(method: str, url: str, payload: dict | None = None, signed: bool = False) -> dict:
    headers = {"Content-Type": "application/json"}
    data = None

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    if signed and payload is not None:
        ts = datetime.now(timezone.utc).isoformat()
        nonce = secrets.token_hex(8)
        headers["X-Fed-Signature"] = sign(SHARED_SECRET, ts, nonce, payload)
        headers["X-Fed-Timestamp"] = ts
        headers["X-Fed-Nonce"] = nonce

    req = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {body}") from exc


def get(url: str) -> dict:
    return _request("GET", url)


def post(url: str, payload: dict, signed: bool = False) -> dict:
    return _request("POST", url, payload=payload, signed=signed)


def assert_success(resp: dict, label: str) -> None:
    if not resp.get("success"):
        raise RuntimeError(f"{label} failed: {resp}")


def main() -> int:
    # 1) status
    st_a = get(f"{CITY_A}/federation/v1/status")
    st_b = get(f"{CITY_B}/federation/v1/status")
    assert_success(st_a, "city-a status")
    assert_success(st_b, "city-b status")

    # 2) hello both ways
    hello_a_to_b = {
        "request_id": f"smoke-hello-a2b-{secrets.token_hex(4)}",
        "city_name": "Luoyang",
        "base_url": CITY_A,
        "public_key": "",
        "shared_secret": SHARED_SECRET,
        "protocol_version": "1.0",
        "rule_version": "1.0",
    }
    hello_b_to_a = {
        "request_id": f"smoke-hello-b2a-{secrets.token_hex(4)}",
        "city_name": "ChengDu",
        "base_url": CITY_B,
        "public_key": "",
        "shared_secret": SHARED_SECRET,
        "protocol_version": "1.0",
        "rule_version": "1.0",
    }

    assert_success(post(f"{CITY_B}/federation/v1/hello", hello_a_to_b, signed=True), "hello a->b")
    assert_success(post(f"{CITY_A}/federation/v1/hello", hello_b_to_a, signed=True), "hello b->a")

    peers_a = get(f"{CITY_A}/federation/v1/peers")
    peers_b = get(f"{CITY_B}/federation/v1/peers")
    assert_success(peers_a, "peers city-a")
    assert_success(peers_b, "peers city-b")
    if len(peers_a["data"]["peers"]) < 1 or len(peers_b["data"]["peers"]) < 1:
        raise RuntimeError("peer registration missing after hello handshake")

    # 3) attack A -> B
    attack = {
        "request_id": f"smoke-attack-a2b-{secrets.token_hex(4)}",
        "from_city": "Luoyang",
        "target_city": "ChengDu",
        "troops": {"infantry": 80, "archer": 20, "cavalry": 10},
    }
    attack_resp = post(f"{CITY_B}/federation/v1/attack", attack, signed=True)
    assert_success(attack_resp, "attack a->b")

    # 4) migrate A -> B
    migrate = {
        "request_id": f"smoke-migrate-a2b-{secrets.token_hex(4)}",
        "from_city": "Luoyang",
        "to_city": "ChengDu",
        "agent_name": f"MigratedGeneral{secrets.token_hex(2)}",
        "role": "general",
        "gold": 180,
        "food": 160,
        "infantry": 12,
        "archer": 6,
        "cavalry": 3,
        "reputation": 20,
    }
    migrate_resp = post(f"{CITY_B}/federation/v1/migrate", migrate, signed=True)
    assert_success(migrate_resp, "migrate a->b")

    print("Federation smoke test passed")
    print(json.dumps({"attack": attack_resp["data"], "migrate": migrate_resp["data"]}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
