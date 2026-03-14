from datetime import datetime, timezone

import requests

from app.services.federation_security import make_signature


BASE_URL = "http://localhost:8000"
SHARED_SECRET = "federation-dev-secret"

payload = {
    "request_id": "req-hello-example-001",
    "city_name": "ChengDu",
    "base_url": "https://chengdu.example.com",
    "public_key": "",
    "shared_secret": SHARED_SECRET,
    "protocol_version": "1.0",
    "rule_version": "1.0",
}

ts = datetime.now(timezone.utc).isoformat()
nonce = "example-nonce"
sig = make_signature(SHARED_SECRET, ts, nonce, payload)

resp = requests.post(
    f"{BASE_URL}/federation/v1/hello",
    json=payload,
    headers={
        "X-Fed-Signature": sig,
        "X-Fed-Timestamp": ts,
        "X-Fed-Nonce": nonce,
    },
    timeout=30,
)

print(resp.status_code)
print(resp.json())
