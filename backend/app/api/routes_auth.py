from datetime import timedelta, timezone
import unicodedata

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import create_access_token, create_refresh_token, hash_password, verify_password
from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import PasswordResetCode, RefreshToken, User, utc_now
from ..schemas import ForgotPasswordRequest, LoginRequest, RefreshTokenRequest, RegisterUserRequest, ResetPasswordRequest
from ..services.email import send_password_reset_email
from ..services.secrets import hash_secret, make_numeric_code
from .deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _normalize_utc(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
    if db.query(User).filter(User.email == payload.email).first():
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
    user = db.query(User).filter(User.username == payload.username).first()
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


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Always return success to avoid account enumeration.
    user = db.query(User).filter(User.email == payload.email).first()
    if user:
        code = make_numeric_code(6)
        expires_at = utc_now() + timedelta(minutes=settings.password_reset_code_ttl_minutes)
        db.add(
            PasswordResetCode(
                user_id=user.id,
                email=user.email,
                code_hash=hash_secret(code),
                expires_at=expires_at,
            )
        )
        db.commit()
        send_password_reset_email(user.email, code)

    return {"success": True, "data": {"sent": True}}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
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
