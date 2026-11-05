"""SMTP / forgot-password delivery contract tests.

Key invariant: the forgot-password response must not reveal whether an email
is registered, even when mail is unavailable. Any failure reason is derived
from GLOBAL mail health, never from the account lookup.
"""

import logging
import smtplib

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import PasswordResetCode
from app.services import email as email_service

client = TestClient(app)


class _FakeSMTP:
    """Minimal SMTP stand-in that records what a real relay would receive."""

    instances = []

    def __init__(self, host, port, timeout=10):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args = None
        self.messages = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, msg):
        self.messages.append(msg)


@pytest.fixture(autouse=True)
def _clean_mail_state():
    email_service.reset_delivery_state()
    _FakeSMTP.instances = []
    yield
    email_service.reset_delivery_state()
    _FakeSMTP.instances = []


@pytest.fixture
def smtp_off(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "smtp_from", "")


@pytest.fixture
def smtp_on(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "noreply@example.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "mailer")
    monkeypatch.setattr(settings, "smtp_password", "mail-secret")
    monkeypatch.setattr(settings, "smtp_use_tls", True)
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    monkeypatch.setattr(settings, "smtp_timeout_sec", 10)


def _register(username: str) -> str:
    addr = f"{username}@example.com"
    resp = client.post(
        "/auth/register",
        json={"username": username, "email": addr, "password": "Aa1234!!"},
    )
    assert resp.status_code == 200
    return addr


def _ticket_count() -> int:
    db = SessionLocal()
    try:
        return db.query(PasswordResetCode).count()
    finally:
        db.close()


def _smtp_boom(*args, **kwargs):
    raise OSError("smtp relay unreachable")


def test_password_reset_status_reflects_smtp_configuration(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "smtp_from", "")
    off = client.get("/auth/password-reset/status")
    assert off.status_code == 200
    assert off.json()["data"]["email_enabled"] is False

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "noreply@example.com")
    on = client.get("/auth/password-reset/status")
    assert on.status_code == 200
    assert on.json()["data"] == {"email_enabled": True, "delivery_degraded": False}


def test_email_without_smtp_never_sends_or_logs_code(smtp_off, monkeypatch, caplog):
    monkeypatch.setattr(smtplib, "SMTP", _smtp_boom)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _smtp_boom)
    with caplog.at_level(logging.WARNING):
        result = email_service.send_password_reset_email("someone@example.com", "654321")
    assert result == email_service.DELIVERY_NOT_CONFIGURED
    assert "654321" not in caplog.text
    assert "someone@example.com" not in caplog.text


def test_email_uses_implicit_tls_on_port_465(smtp_on, monkeypatch):
    monkeypatch.setattr(settings, "smtp_port", 465)
    monkeypatch.setattr(settings, "smtp_use_ssl", True)
    monkeypatch.setattr(settings, "smtp_use_tls", False)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
    result = email_service.send_password_reset_email("player@example.com", "123456")
    assert result == email_service.DELIVERY_SENT
    assert len(_FakeSMTP.instances) == 1
    assert _FakeSMTP.instances[0].port == 465
    assert "123456" in _FakeSMTP.instances[0].messages[0].get_content()
    assert email_service.delivery_health()["degraded"] is False


def test_email_starTTLS_and_login_on_port_587(smtp_on, monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    result = email_service.send_password_reset_email("player@example.com", "123456")
    assert result == email_service.DELIVERY_SENT
    smtp = _FakeSMTP.instances[0]
    assert smtp.started_tls is True
    assert smtp.login_args == ("mailer", "mail-secret")


def test_email_failure_is_reported_not_raised(smtp_on, monkeypatch, caplog):
    monkeypatch.setattr(smtplib, "SMTP", _smtp_boom)
    with caplog.at_level(logging.WARNING):
        result = email_service.send_password_reset_email("player@example.com", "123456")
    assert result == email_service.DELIVERY_FAILED
    assert email_service.delivery_health()["degraded"] is True
    assert "123456" not in caplog.text


def test_forgot_password_not_configured_reports_failure_and_issues_no_ticket(smtp_off):
    addr = _register("mail_noconfig")
    resp = client.post("/auth/forgot-password", json={"email": addr})
    assert resp.status_code == 200
    assert resp.json()["data"] == {"sent": False, "reason": "EMAIL_NOT_CONFIGURED"}
    assert _ticket_count() == 0


def test_forgot_password_response_is_identical_for_unknown_email(smtp_off):
    addr = _register("mail_noconfig_uniform")
    known = client.post("/auth/forgot-password", json={"email": addr})
    unknown = client.post("/auth/forgot-password", json={"email": "not-registered@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


def test_forgot_password_delivery_failure_is_uniform_and_cleans_ticket(smtp_on, monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _smtp_boom)
    addr = _register("mail_fail")
    known = client.post("/auth/forgot-password", json={"email": addr})
    assert known.json()["data"] == {"sent": False, "reason": "EMAIL_DELIVERY_FAILED"}
    unknown = client.post("/auth/forgot-password", json={"email": "not-registered@example.com"})
    assert unknown.json() == known.json()
    assert _ticket_count() == 0


def test_forgot_password_success_issues_ticket_and_clears_degraded(smtp_on, monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _smtp_boom)
    _register("mail_recover")
    failed = client.post("/auth/forgot-password", json={"email": "mail_recover@example.com"})
    assert failed.json()["data"]["sent"] is False

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    ok = client.post("/auth/forgot-password", json={"email": "mail_recover@example.com"})
    assert ok.json()["data"] == {"sent": True}
    assert _ticket_count() == 1
    assert email_service.delivery_health()["degraded"] is False
