from dataclasses import dataclass
from datetime import timezone

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from ..auth import decode_access_token
from ..db import get_db
from ..errors import AppError
from ..models import Agent, ApiKey, User, utc_now
from ..services.secrets import hash_secret


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError("UNAUTHORIZED", "Missing Bearer token.", status_code=401)

    token = authorization.split(" ", 1)[1]
    try:
        user_id = decode_access_token(token)
    except ValueError as exc:
        raise AppError("UNAUTHORIZED", "Invalid token.", status_code=401) from exc

    user = db.get(User, user_id)
    if not user:
        raise AppError("USER_NOT_FOUND", "The specified user does not exist.", status_code=404)
    return user


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise AppError("FORBIDDEN", "Admin permission is required.", status_code=403)
    return current_user


@dataclass
class AgentAuthContext:
    user: User
    agent: Agent
    api_key: ApiKey
    scope: set[str]
    allowed_actions: set[str]


def _parse_json_list(raw: str) -> set[str]:
    import json

    try:
        data = json.loads(raw or "[]")
        if not isinstance(data, list):
            return set()
        return {str(item).strip() for item in data if str(item).strip()}
    except Exception:
        return set()


def get_current_agent_auth(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AgentAuthContext:
    plain_key = (x_api_key or "").strip()
    if not plain_key and authorization and authorization.startswith("Bearer "):
        bearer = authorization.split(" ", 1)[1].strip()
        if bearer.startswith("sk_"):
            plain_key = bearer

    if not plain_key:
        raise AppError("UNAUTHORIZED", "Missing API key (X-API-Key or Bearer sk_*).", status_code=401)

    key_hash = hash_secret(plain_key)
    key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
    if not key:
        raise AppError("INVALID_API_KEY", "API key is invalid.", status_code=401)
    if key.revoked_at is not None:
        raise AppError("API_KEY_REVOKED", "The API key has been revoked.", status_code=401)
    expires_at = key.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at <= utc_now():
        raise AppError("API_KEY_EXPIRED", "API key has expired.", status_code=401)
    if key.agent_id is None:
        raise AppError("INVALID_API_KEY", "API key must be bound to an agent.", status_code=401)

    agent = db.get(Agent, key.agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)
    if agent.owner_user_id != key.owner_user_id:
        raise AppError("FORBIDDEN", "This API key no longer owns the target agent.", status_code=403)

    user = db.get(User, key.owner_user_id)
    if not user:
        raise AppError("USER_NOT_FOUND", "The specified user does not exist.", status_code=404)

    key.last_used_at = utc_now()
    db.add(key)
    db.commit()

    return AgentAuthContext(
        user=user,
        agent=agent,
        api_key=key,
        scope=_parse_json_list(key.scope_json),
        allowed_actions=_parse_json_list(key.allowed_actions_json),
    )
