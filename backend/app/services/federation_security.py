import hashlib
import hmac
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..config import settings
from ..errors import AppError
from ..models import FederationRequestLog


def stable_body(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def make_signature(shared_secret: str, timestamp: str, nonce: str, body: dict) -> str:
    message = f"{timestamp}.{nonce}.{stable_body(body)}"
    return hmac.new(shared_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(shared_secret: str, timestamp: str, nonce: str, body: dict, signature: str) -> bool:
    expected = make_signature(shared_secret, timestamp, nonce, body)
    return hmac.compare_digest(expected, signature)


def assert_federation_request(
    db: Session,
    source_city: str,
    request_type: str,
    request_id: str,
    timestamp: str,
) -> None:
    now = datetime.now(timezone.utc)
    try:
        request_ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppError("INVALID_REQUEST", "Invalid federation timestamp.", status_code=422) from exc

    delta = abs((now - request_ts).total_seconds())
    if delta > settings.federation_request_ttl_sec:
        raise AppError("FEDERATION_UNAUTHORIZED", "Federation request timestamp expired.", status_code=401)

    replay = db.query(FederationRequestLog).filter(FederationRequestLog.request_id == request_id).first()
    if replay:
        raise AppError("FEDERATION_REPLAY", "Federation request replay detected.", status_code=409)

    db.add(
        FederationRequestLog(
            request_id=request_id,
            source_city=source_city,
            request_type=request_type,
        )
    )
