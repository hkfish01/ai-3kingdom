"""每日更新通知：agent 每天都能比對 revision，變動時自動補一則公告。"""

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.services import updates as updates_service

client = TestClient(app)


def _register(username: str) -> None:
    assert client.post(
        "/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "Aa1234!!"},
    ).status_code == 200


def test_public_updates_payload_and_revision_endpoint():
    resp = client.get("/world/public/updates?lang=zh")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["revision"]) == 12
    assert data["app_version"] == settings.app_version
    assert data["count"] >= 1
    assert data["items"][0]["title"]
    # 最新一筆 changelog 必須跟著版本號走，避免改版忘了寫更新摘要。
    assert data["items"][0]["version"] == settings.app_version
    assert data["items"][0]["detail"]
    assert data["docs"]["skill"].startswith(settings.public_site_url)

    plain = client.get("/world/public/updates/revision")
    assert plain.status_code == 200
    assert plain.text.strip() == data["revision"]


def test_skill_md_carries_the_daily_update_bulletin():
    text = client.get("/skill.md?lang=zh").text
    assert "# 系統更新 / System Updates" in text
    assert f"`{updates_service.revision()}`" in text
    assert "GET /world/public/updates" in text
    # 更新區塊要放在公告之前，agent 一打開就看得到。
    assert text.index("# 系統更新") < text.index("# Announcements")


def test_daily_check_announces_once_and_stays_idempotent():
    _register("updates_admin")
    db = SessionLocal()
    try:
        first = updates_service.daily_update_check(db, now=datetime(2026, 11, 7, 2, tzinfo=timezone.utc))
        assert first["status"] == "announced"
        assert first["date"] == "2026-11-07"
        second = updates_service.daily_update_check(db, now=datetime(2026, 11, 7, 3, tzinfo=timezone.utc))
        assert second["status"] == "unchanged"
        assert updates_service.build_updates_payload(db)["last_checked_at"] == "2026-11-07"
    finally:
        db.close()

    announcements = client.get("/world/public/announcements").json()["data"]
    blob = json.dumps(announcements, ensure_ascii=False)
    assert "系統更新" in blob
    assert "GET /world/public/updates" in blob
    assert "系統更新" in client.get("/skill.md?lang=zh").text


def test_same_day_revision_change_still_announces(monkeypatch, tmp_path):
    """同日二次部署：每日節流不能把新版本的公告擋到隔天。"""
    _register("updates_sameday")
    db = SessionLocal()
    try:
        first = updates_service.daily_update_check(db, now=datetime(2026, 11, 7, 2, tzinfo=timezone.utc))
        assert first["status"] == "announced"
        assert updates_service.announce_latest_update(db)["status"] == "unchanged"

        # 模擬當天又部署一版：changelog 與 app_version 都換了。
        changelog = tmp_path / "changelog.json"
        changelog.write_text(
            json.dumps(
                {"entries": [{
                    "date": "2026-11-07", "version": "1.29.1",
                    "title_zh": "同日改版", "detail_zh": "buy 規則更新",
                }]}
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(updates_service, "CHANGELOG_PATH", changelog)
        monkeypatch.setattr(settings, "app_version", "1.29.1")

        # worker 在「今天已檢查」的分支走的就是這一條。
        second = updates_service.announce_latest_update(db)
        assert second["status"] == "announced"
        assert second["revision"] != first["revision"]
        assert updates_service.announce_latest_update(db)["status"] == "unchanged"
    finally:
        db.close()


def test_revision_changes_when_changelog_changes(monkeypatch, tmp_path):
    original = updates_service.revision()
    changelog = tmp_path / "changelog.json"
    changelog.write_text(
        json.dumps({"entries": [{"date": "2026-12-01", "version": "9.9.9", "title_zh": "測試"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(updates_service, "CHANGELOG_PATH", changelog)
    assert updates_service.revision() != original
    db = SessionLocal()
    try:
        payload = updates_service.build_updates_payload(db)
    finally:
        db.close()
    assert payload["items"][0]["date"] == "2026-12-01"
