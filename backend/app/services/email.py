"""Password-reset email delivery.

SMTP is optional for local development but REQUIRED for the public
forgot-password flow. Delivery health is tracked globally (never per account)
so the API can tell a visitor "mail is unavailable" without leaking whether
a given email address is registered.

Security notes:
- When SMTP is not configured we never send AND never print the reset code to
  logs. The old dev fallback printed the code, which would let anyone with log
  access reset any account on a production node.
- The reset code and the recipient address are never logged.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import logging
import smtplib
import threading

from ..config import settings

logger = logging.getLogger(__name__)

DELIVERY_SENT = "sent"
DELIVERY_NOT_CONFIGURED = "not_configured"
DELIVERY_FAILED = "failed"

DEGRADED_TTL = timedelta(minutes=5)

_state_lock = threading.Lock()
_last_failure_at: datetime | None = None
_last_success_at: datetime | None = None


def smtp_configured() -> bool:
    """Both host and From are required; an empty From means undeliverable."""
    return bool(settings.smtp_host and settings.smtp_from)


def _mark_failure() -> None:
    global _last_failure_at
    with _state_lock:
        _last_failure_at = datetime.now(timezone.utc)


def _mark_success() -> None:
    global _last_success_at
    with _state_lock:
        _last_success_at = datetime.now(timezone.utc)


def reset_delivery_state() -> None:
    """Test helper: clear in-process delivery health between test cases."""
    global _last_failure_at, _last_success_at
    with _state_lock:
        _last_failure_at = None
        _last_success_at = None


def delivery_health() -> dict[str, bool]:
    """Global mail health, safe to expose publicly (contains no account data)."""
    with _state_lock:
        failure_at = _last_failure_at
        success_at = _last_success_at
    degraded = (
        failure_at is not None
        and datetime.now(timezone.utc) - failure_at < DEGRADED_TTL
        and (success_at is None or failure_at > success_at)
    )
    return {"configured": smtp_configured(), "degraded": degraded}


def _build_message(to_email: str, reset_code: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "AI 3Kingdom Password Reset Code"
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.set_content(
        "【中文】\n"
        "你的密碼重設驗證碼是："
        f"{reset_code}\n"
        "此驗證碼將於 "
        f"{settings.password_reset_code_ttl_minutes} 分鐘後失效。\n\n"
        "[English]\n"
        "Your password reset code is: "
        f"{reset_code}\n"
        "This code expires in "
        f"{settings.password_reset_code_ttl_minutes} minutes.\n"
    )
    return msg


def _authenticate(smtp: smtplib.SMTP | smtplib.SMTP_SSL) -> None:
    if settings.smtp_user:
        smtp.login(settings.smtp_user, settings.smtp_password)


def send_password_reset_email(to_email: str, reset_code: str) -> str:
    """Send a reset code and return one of DELIVERY_SENT / NOT_CONFIGURED / FAILED.

    This function never raises: SMTP outages must not turn a forgot-password
    request into a 500. A falsy/None return (used by older test doubles) is
    treated as success by the caller.
    """
    if not smtp_configured():
        logger.warning("SMTP is not configured; password reset delivery is disabled (code not sent, not logged).")
        return DELIVERY_NOT_CONFIGURED

    msg = _build_message(to_email, reset_code)
    timeout = max(1, settings.smtp_timeout_sec)
    try:
        if settings.smtp_use_ssl or settings.smtp_port == 465:
            # Implicit TLS (typically port 465).
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout) as smtp:
                _authenticate(smtp)
                smtp.send_message(msg)
        else:
            # Plain SMTP, optionally upgraded with STARTTLS (typically port 587).
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                _authenticate(smtp)
                smtp.send_message(msg)
    except Exception as exc:  # noqa: BLE001 - any SMTP failure is a delivery failure
        logger.warning("Password reset email delivery failed (%s): %s", type(exc).__name__, exc)
        _mark_failure()
        return DELIVERY_FAILED

    _mark_success()
    return DELIVERY_SENT
