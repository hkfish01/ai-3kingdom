"""Login identifiers must match the email-based password-reset flow.

Regression for: a user resets their password with an email address and then
types that same address into the login form; the old code only looked up
`users.username` and returned INVALID_CREDENTIALS even though the reset
succeeded.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

USERNAME = "terry_lord"
EMAIL = "terry@onlyoneledger.com"
PASSWORD = "Aa1234!!"
NEW_PASSWORD = "Bb5678@@"


def _register(username: str = USERNAME, email: str = EMAIL, password: str = PASSWORD):
    response = client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    assert response.status_code == 200, response.text


def _login(identifier: str, password: str = PASSWORD):
    return client.post("/auth/login", json={"username": identifier, "password": password})


def test_username_login_is_unchanged():
    _register()
    response = _login(USERNAME)
    assert response.status_code == 200
    assert response.json()["data"]["token"]


def test_email_login_works():
    _register()
    assert _login(EMAIL).status_code == 200


def test_email_login_ignores_case_and_surrounding_whitespace():
    _register()
    assert _login("  Terry@OnlyOneLedger.com  ").status_code == 200


def test_wrong_password_and_unknown_identifier_are_still_401():
    _register()
    for identifier, password in ((EMAIL, "Wrong123!"), ("nobody@example.com", PASSWORD)):
        response = _login(identifier, password)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_exact_username_wins_over_another_accounts_email():
    _register()
    other = client.post(
        "/auth/register",
        json={"username": EMAIL, "email": "other@example.com", "password": PASSWORD},
    )
    assert other.status_code == 200, other.text

    response = _login(EMAIL)
    assert response.status_code == 200
    token = response.json()["data"]["token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["data"]["username"] == EMAIL


def test_legacy_mixed_case_email_rows_can_log_in():
    """Rows written before email normalization must still be reachable."""
    from app.db import SessionLocal
    from app.models import User

    _register()
    with SessionLocal() as session:
        row = session.query(User).filter(User.username == USERNAME).first()
        row.email = "Terry@OnlyOneLedger.com"
        session.commit()

    assert _login(EMAIL).status_code == 200


def test_duplicate_email_registration_is_rejected_regardless_of_case():
    _register()
    duplicate = client.post(
        "/auth/register",
        json={"username": "another_lord", "email": "TERRY@ONLYONELEDGER.COM", "password": PASSWORD},
    )
    assert duplicate.status_code == 409


def test_reset_with_mixed_case_email_then_login_with_email(monkeypatch):
    """End-to-end reproduction of the reported bug."""
    _register()
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        "app.api.routes_auth.delivery_health",
        lambda: {"configured": True, "degraded": False},
    )

    def fake_send(address: str, code: str) -> None:
        captured["code"] = code
        return None

    monkeypatch.setattr("app.api.routes_auth.send_password_reset_email", fake_send)

    forgot = client.post("/auth/forgot-password", json={"email": "Terry@OnlyOneLedger.com"})
    assert forgot.status_code == 200
    assert forgot.json()["data"]["sent"] is True
    assert len(captured["code"]) == 6

    reset = client.post(
        "/auth/reset-password",
        json={"email": EMAIL, "code": captured["code"], "new_password": NEW_PASSWORD},
    )
    assert reset.status_code == 200, reset.text

    assert _login(EMAIL, PASSWORD).status_code == 401
    assert _login(EMAIL, NEW_PASSWORD).status_code == 200
    assert _login(USERNAME, NEW_PASSWORD).status_code == 200
