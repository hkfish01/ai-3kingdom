import smtplib
from email.message import EmailMessage

from ..config import settings


def send_password_reset_email(to_email: str, reset_code: str) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        # Dev fallback: no-op delivery while preserving flow.
        print(f"[email-dev] password reset code for {to_email}: {reset_code}")
        return

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

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
