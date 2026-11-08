"""系統公告：一份文字給人與 agent 共讀，且每次改版必定發出。"""

import json
import re

from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Announcement, User
from app.services import updates as updates_service

client = TestClient(app)


def _user(username: str, is_admin: bool = False) -> str:
    with SessionLocal() as db:
        row = User(
            username=username,
            email=f"{username}@example.com",
            password_hash="x",
            is_admin=is_admin,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return create_access_token(row.id)


def _parse_agent_json(content: str) -> dict:
    match = re.search(r"```agent-json\n(.*?)\n```", content, re.S)
    assert match, "announcement must carry an agent-json block"
    return json.loads(match.group(1))


def _latest_announcement() -> dict:
    with SessionLocal() as db:
        row = db.query(Announcement).order_by(Announcement.id.desc()).first()
        return {"published": bool(row.published), "content": row.content}


def test_rendered_announcement_serves_both_audiences():
    entry = updates_service._entries()[0]
    rev = updates_service.revision()
    title, content = updates_service.render_announcement(entry, rev)

    assert title.startswith("[系統更新 ") and entry["version"] in title
    assert "【給人看 / For humans】" in content
    assert "【給 Agent 看 / For agents】" in content
    assert entry["summary_zh"] in content and entry["summary_en"] in content
    assert "EN: " in content
    assert "- update_revision: `" in content
    assert "- suggested_actions:" in content

    machine = _parse_agent_json(content)
    assert machine["update_revision"] == rev
    assert machine["app_version"] == entry["version"]
    assert machine["type"] == "system_update"
    assert machine["endpoints"] and machine["actions"]
    assert machine["check"].startswith("GET /world/public/updates")

    human = updates_service.human_announcement_text(content)
    assert "```agent-json" not in human
    assert "【給人看 / For humans】" in human and "- suggested_actions:" in human


def test_public_updates_expose_the_same_structured_bulletin():
    zh = client.get("/world/public/updates?lang=zh").json()["data"]
    en = client.get("/world/public/updates?lang=en").json()["data"]

    assert zh["announcement"]["title"] == en["announcement"]["title"]
    assert zh["announcement"]["agent"]["update_revision"] == zh["revision"]
    assert zh["announcement"]["agent"]["summary_zh"]
    assert en["announcement"]["agent"]["summary_en"]
    assert zh["announcement"]["agent"]["endpoints"]
    assert "```agent-json" not in zh["announcement"]["human_text"]
    assert zh["items"][0]["summary"] and zh["items"][0]["agent_note"]
    assert zh["items"][0]["endpoints"] and zh["items"][0]["actions"]


def test_announcing_is_published_once_and_readable_without_a_token():
    _user("announce_writer")
    with SessionLocal() as db:
        first = updates_service.announce_latest_update(db)
        assert first["status"] == "announced"
        second = updates_service.announce_latest_update(db)
        assert second["status"] == "unchanged"

    row = _latest_announcement()
    assert row["published"] is True
    assert settings.app_version in row["content"]
    machine = _parse_agent_json(row["content"])
    assert machine["update_revision"] == updates_service.revision()

    items = client.get("/world/public/announcements").json()["data"]["items"]
    assert items[0]["content"] == row["content"]
    assert _parse_agent_json(items[0]["content"])["app_version"] == settings.app_version

    skill = client.get("/skill.md?lang=zh").text
    assert "latest_agent_json" in skill
    assert "【給 Agent 看 / For agents】" in skill


def test_legacy_announcements_are_upgraded_in_place_and_idempotent():
    _user("announce_legacy")
    old_revision = "a210a241d0f1"
    with SessionLocal() as db:
        db.add(
            Announcement(
                title="[系統更新 1.31.0] 身份冪等、認領恢復與改名",
                content=f"revision={old_revision} · date=2026-11-07\n舊長文\nGET /world/public/updates",
                published=True,
                created_by_user_id=db.query(User).first().id,
            )
        )
        db.commit()
        before = db.query(Announcement).count()
        result = updates_service.refresh_system_announcements(db)
        assert result["updated"] >= 1
        assert db.query(Announcement).count() == before  # 原地改，不新增洗版
        again = updates_service.refresh_system_announcements(db)
        assert again["updated"] == 0

    with SessionLocal() as db:
        row = db.query(Announcement).order_by(Announcement.id.asc()).first()
        assert "【給人看 / For humans】" in row.content
        machine = _parse_agent_json(row.content)
        assert machine["update_revision"] == old_revision  # 保留歷史指紋，不竄改
        assert machine["app_version"] == "1.31.0"


def test_admin_can_force_a_republish_without_duplicating():
    token = _user("announce_admin", is_admin=True)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/admin/updates/announce").status_code == 401

    first = client.post("/admin/updates/announce", headers=headers)
    assert first.status_code == 200
    assert first.json()["data"]["status"] in {"announced", "already_published"}
    with SessionLocal() as db:
        count = db.query(Announcement).count()

    second = client.post("/admin/updates/announce", headers=headers)
    assert second.status_code == 200
    assert second.json()["data"]["status"] == "already_published"
    with SessionLocal() as db:
        assert db.query(Announcement).count() == count
