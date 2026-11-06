from datetime import timedelta, timezone
import logging
import unicodedata

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import create_access_token, create_refresh_token, hash_password, verify_password
from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import PasswordResetCode, RefreshToken, User, utc_now
from ..schemas import ForgotPasswordRequest, LoginRequest, RefreshTokenRequest, RegisterUserRequest, ResetPasswordRequest
from ..services.email import (
    DELIVERY_FAILED,
    DELIVERY_NOT_CONFIGURED,
    delivery_health,
    send_password_reset_email,
)
from ..services.secrets import hash_secret, make_numeric_code
from .deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

REASON_NOT_CONFIGURED = "EMAIL_NOT_CONFIGURED"
REASON_DELIVERY_FAILED = "EMAIL_DELIVERY_FAILED"


def _normalize_utc(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _find_user_by_email(db: Session, email: str) -> User | None:
    """Case-insensitive email lookup.

    Registration/forgot/reset all normalize emails to lowercase, but rows
    created before that convention (or by a direct DB import) may not be.
    """
    value = email.strip().lower()
    if not value:
        return None
    return db.query(User).filter(func.lower(User.email) == value).first()


def _find_login_user(db: Session, identifier: str) -> User | None:
    """Accept a username *or* the registered email address.

    Password reset is entirely email-based, so users naturally type the same
    address into the login form. Username is matched first so an existing
    username is never shadowed by a different account's email.
    """
    value = identifier.strip()
    if not value:
        return None
    user = db.query(User).filter(User.username == value).first()
    if user is not None:
        return user
    return _find_user_by_email(db, value)


def _issue_tokens(db: Session, user_id: int) -> dict:
    now = utc_now()
    refresh = create_refresh_token()
    refresh_expiry = now + timedelta(days=settings.refresh_token_exp_days)
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_secret(refresh),
            expires_at=refresh_expiry,
        )
    )
    access = create_access_token(user_id)
    return {
        "token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": settings.jwt_exp_minutes * 60,
        "refresh_expires_in": settings.refresh_token_exp_days * 24 * 60 * 60,
    }


@router.post("/register")
def register(payload: RegisterUserRequest, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.username == payload.username).first()
    if exists:
        raise AppError("USERNAME_EXISTS", "Username already exists.", status_code=409)
    if _find_user_by_email(db, payload.email):
        raise AppError("EMAIL_EXISTS", "Email already exists.", status_code=409)

    admins = {name.strip() for name in settings.admin_usernames.split(",") if name.strip()}
    has_admin = db.query(User).filter(User.is_admin.is_(True)).first() is not None
    is_admin = payload.username in admins or not has_admin

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "success": True,
        "data": {"user_id": user.id, "username": user.username, "email": user.email, "is_admin": user.is_admin},
    }


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = _find_login_user(db, payload.username)
    normalized_password = unicodedata.normalize("NFKC", payload.password)
    if not user or not verify_password(normalized_password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Invalid username or password.", status_code=401)

    token_data = _issue_tokens(db, user.id)
    db.commit()
    return {"success": True, "data": token_data}


@router.post("/refresh")
def refresh(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    now = utc_now()
    token_hash = hash_secret(payload.refresh_token)
    row = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
        )
        .order_by(RefreshToken.id.desc())
        .first()
    )
    if not row:
        raise AppError("REFRESH_TOKEN_INVALID", "Refresh token is invalid or expired.", status_code=401)

    expires_at = _normalize_utc(row.expires_at)
    if expires_at < now:
        row.revoked_at = now
        row.last_used_at = now
        db.add(row)
        db.commit()
        raise AppError("REFRESH_TOKEN_INVALID", "Refresh token is invalid or expired.", status_code=401)

    row.revoked_at = now
    row.last_used_at = now
    db.add(row)
    token_data = _issue_tokens(db, row.user_id)
    db.commit()
    return {"success": True, "data": token_data}


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "success": True,
        "data": {
            "user_id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "is_admin": current_user.is_admin,
        },
    }


def _delivery_failure(reason: str) -> dict:
    return {"success": True, "data": {"sent": False, "reason": reason}}


@router.get("/password-reset/status")
def password_reset_status():
    """Public, account-free mail health for the forgot-password UI.

    Only global state is exposed, never whether an email address is registered.
    """
    health = delivery_health()
    return {
        "success": True,
        "data": {
            "email_enabled": health["configured"],
            "delivery_degraded": health["degraded"],
        },
    }


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # 回應只取決於「全域郵件狀態」與「這次寄送結果」，不取決於帳號是否存在，
    # 避免攻擊者用 sent/reason 的差異枚舉註冊信箱。
    health = delivery_health()
    global_reason = None
    if not health["configured"]:
        global_reason = REASON_NOT_CONFIGURED
    elif health["degraded"]:
        global_reason = REASON_DELIVERY_FAILED

    user = _find_user_by_email(db, payload.email)
    if not user:
        if global_reason:
            return _delivery_failure(global_reason)
        return {"success": True, "data": {"sent": True}}

    code = make_numeric_code(6)
    expires_at = utc_now() + timedelta(minutes=settings.password_reset_code_ttl_minutes)
    ticket = PasswordResetCode(
        user_id=user.id,
        email=user.email,
        code_hash=hash_secret(code),
        expires_at=expires_at,
    )
    db.add(ticket)
    db.commit()

    try:
        delivery = send_password_reset_email(user.email, code)
    except Exception as exc:  # noqa: BLE001 - 寄送異常不應讓 API 500
        logger.warning("Password reset mail raised unexpectedly (%s): %s", type(exc).__name__, exc)
        delivery = DELIVERY_FAILED

    if delivery in (DELIVERY_NOT_CONFIGURED, DELIVERY_FAILED):
        # 沒寄出去，就不留一組仍然有效的驗證碼在資料庫裡。
        db.delete(ticket)
        db.commit()
        reason = REASON_NOT_CONFIGURED if delivery == DELIVERY_NOT_CONFIGURED else REASON_DELIVERY_FAILED
        return _delivery_failure(reason)

    # None 視為成功，相容舊版的測試替身／自訂寄送函式。
    return {"success": True, "data": {"sent": True}}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = _find_user_by_email(db, payload.email)
    if not user:
        raise AppError("RESET_CODE_INVALID", "Reset code is invalid or expired.", status_code=400)

    now = utc_now()
    code_hash = hash_secret(payload.code)
    ticket = (
        db.query(PasswordResetCode)
        .filter(
            PasswordResetCode.user_id == user.id,
            PasswordResetCode.code_hash == code_hash,
            PasswordResetCode.used_at.is_(None),
        )
        .order_by(PasswordResetCode.id.desc())
        .first()
    )
    if not ticket:
        raise AppError("RESET_CODE_INVALID", "Reset code is invalid or expired.", status_code=400)

    expires_at = ticket.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise AppError("RESET_CODE_INVALID", "Reset code is invalid or expired.", status_code=400)

    user.password_hash = hash_password(payload.new_password)
    ticket.used_at = now
    db.add(user)
    db.add(ticket)
    db.commit()

    return {"success": True, "data": {"reset": True}}
