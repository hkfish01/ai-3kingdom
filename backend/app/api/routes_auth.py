from datetime import timedelta, timezone
import unicodedata

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import create_access_token, hash_password, verify_password
from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import PasswordResetCode, User, utc_now
from ..schemas import ForgotPasswordRequest, LoginRequest, RegisterUserRequest, ResetPasswordRequest
from ..services.email import send_password_reset_email
from ..services.secrets import hash_secret, make_numeric_code
from .deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


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

    token = create_access_token(user.id)
    return {"success": True, "data": {"token": token}}


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
