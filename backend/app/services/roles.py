import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..config import settings
from ..models import SystemState
from .positions import POSITION_DEFINITIONS

DEFAULT_ALLOWED_ROLES = tuple(
    dict.fromkeys(
        [item.name_zh for item in POSITION_DEFINITIONS]
        + [item.name_en for item in POSITION_DEFINITIONS]
        + ["学生", "举人", "将军", "武将", "散骑常侍", "尚书令", "尚书仆射", "给事黄门侍郎", "司隶校尉"]
    )
)

ROLES_POLICY_KEY = "central.roles.policy"
ROLES_POLICY_VERSION_KEY = "central.roles.policy.version"
ROLES_POLICY_UPDATED_AT_KEY = "central.roles.policy.updated_at"


def _set_state(db: Session, key: str, value: str) -> None:
    row = db.get(SystemState, key)
    if not row:
        row = SystemState(key=key, value=value)
    else:
        row.value = value
    db.add(row)


def save_central_roles_policy(db: Session, roles: list[str], version: str) -> None:
    _set_state(db, ROLES_POLICY_KEY, json.dumps(roles, ensure_ascii=False))
    _set_state(db, ROLES_POLICY_VERSION_KEY, version)
    _set_state(db, ROLES_POLICY_UPDATED_AT_KEY, datetime.now(timezone.utc).isoformat())


def get_central_roles_policy(db: Session) -> list[str]:
    row = db.get(SystemState, ROLES_POLICY_KEY)
    if not row or not row.value:
        return []
    try:
        data = json.loads(row.value)
        if isinstance(data, list):
            return [str(item) for item in data if isinstance(item, str)]
    except json.JSONDecodeError:
        return []
    return []


def get_effective_allowed_roles(db: Session) -> list[str]:
    central_roles = get_central_roles_policy(db)
    if central_roles:
        return central_roles
    if settings.central_roles_policy_required:
        return []
    return list(DEFAULT_ALLOWED_ROLES)


def is_allowed_role(db: Session, role: str) -> bool:
    return role in get_effective_allowed_roles(db)
