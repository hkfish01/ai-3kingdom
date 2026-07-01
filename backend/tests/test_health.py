from fastapi.testclient import TestClient

try:
    from app.main import app
except ImportError:
    from main import app

client = TestClient(app)


def test_health_check_returns_200_and_expected_status():
    """驗證 /health 回傳 200 與預期狀態。"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert payload.get("success") is True
    data = payload.get("data", {})
    assert data.get("status") == "ok"
