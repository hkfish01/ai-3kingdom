from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_login_returns_refresh_token_and_refresh_rotates_token_pair():
    register = client.post(
        "/auth/register",
        json={"username": "refresh_user", "email": "refresh_user@example.com", "password": "Aa1234!!"},
    )
    assert register.status_code == 200

    login = client.post("/auth/login", json={"username": "refresh_user", "password": "Aa1234!!"})
    assert login.status_code == 200
    login_data = login.json()["data"]

    assert isinstance(login_data.get("token"), str)
    assert isinstance(login_data.get("refresh_token"), str)
    assert login_data.get("expires_in") == 15 * 60
    assert login_data.get("refresh_expires_in") == 30 * 24 * 60 * 60

    refreshed = client.post("/auth/refresh", json={"refresh_token": login_data["refresh_token"]})
    assert refreshed.status_code == 200
    refreshed_data = refreshed.json()["data"]

    assert refreshed_data["refresh_token"] != login_data["refresh_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {refreshed_data['token']}"})
    assert me.status_code == 200
    assert me.json()["data"]["username"] == "refresh_user"

    reused_old = client.post("/auth/refresh", json={"refresh_token": login_data["refresh_token"]})
    assert reused_old.status_code == 401
    assert reused_old.json()["error"]["code"] == "REFRESH_TOKEN_INVALID"
