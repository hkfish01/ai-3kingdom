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


def post(url: str, payload: dict) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    nonce = secrets.token_hex(8)
    signature = sign(SHARED_SECRET, ts, nonce, payload)

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Fed-Signature": signature,
            "X-Fed-Timestamp": ts,
            "X-Fed-Nonce": nonce,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc


def connect(a: str, b: str, a_name: str, b_name: str) -> None:
    payload = {
        "request_id": f"hello-{a_name.lower()}-to-{b_name.lower()}-{secrets.token_hex(4)}",
        "city_name": a_name,
        "base_url": a,
        "public_key": "",
        "shared_secret": SHARED_SECRET,
        "protocol_version": "1.0",
        "rule_version": "1.0",
    }
    res = post(f"{b}/federation/v1/hello", payload)
    print(f"{a_name} -> {b_name}: {res}")


if __name__ == "__main__":
    try:
        connect(CITY_A, CITY_B, "Luoyang", "ChengDu")
        connect(CITY_B, CITY_A, "ChengDu", "Luoyang")
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
