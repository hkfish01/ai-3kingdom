from fastapi import Depends, Header
from sqlalchemy.orm import Session

from ..auth import decode_access_token
from ..db import get_db
from ..errors import AppError
from ..models import User


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
