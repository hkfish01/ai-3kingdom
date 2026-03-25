from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..api.deps import get_current_user
from ..db import get_db
from ..errors import AppError
from ..models import Agent, ApiKey, User
from ..schemas import CreateApiKeyRequest
from ..services.secrets import hash_secret, make_api_key

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("")
def list_api_keys(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    keys = (
        db.query(ApiKey)
        .filter(ApiKey.owner_user_id == current_user.id)
        .order_by(ApiKey.id.desc())
        .all()
    )
    return {
        "success": True,
        "data": {
            "items": [
                {
                    "id": k.id,
                    "name": k.name,
                    "agent_id": k.agent_id,
                    "key_preview": f"{k.key_prefix}...{k.last4}",
                    "revoked": k.revoked_at is not None,
                    "created_at": k.created_at.isoformat(),
                    "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                }
                for k in keys
            ]
        },
    }


@router.post("")
def create_api_key(
    payload: CreateApiKeyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.agent_id is not None:
        agent = db.get(Agent, payload.agent_id)
        if not agent:
            raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)
        if agent.owner_user_id != current_user.id:
            raise AppError("FORBIDDEN", "You do not own this agent.", status_code=403)

    plain_key = make_api_key()
    key = ApiKey(
        owner_user_id=current_user.id,
        agent_id=payload.agent_id,
        name=payload.name,
        key_prefix=plain_key[:10],
        key_hash=hash_secret(plain_key),
        last4=plain_key[-4:],
    )
    db.add(key)
    db.commit()
    db.refresh(key)

    return {
        "success": True,
        "data": {
            "id": key.id,
            "name": key.name,
            "agent_id": key.agent_id,
            "key": plain_key,
            "key_preview": f"{key.key_prefix}...{key.last4}",
            "created_at": key.created_at.isoformat(),
        },
    }


@router.delete("/{key_id}")
def revoke_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    key = db.get(ApiKey, key_id)
    if not key or key.owner_user_id != current_user.id:
        raise AppError("API_KEY_NOT_FOUND", "The specified API key does not exist.", status_code=404)
    if key.revoked_at is None:
        from ..models import utc_now

        key.revoked_at = utc_now()
        db.add(key)
        db.commit()

    return {"success": True, "data": {"id": key.id, "revoked": True}}
