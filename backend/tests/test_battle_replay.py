"""公開戰報回放、每日校場演武、戰報卡與內容飛輪整合。"""

import io
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.deps import get_current_admin
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import ActionLog, Agent, BattleLog, ChronicleEntry, City, User
from app.services import arena_exhibition, chronicle_card, chronicle_publish
from app.services.battle_replay import (
    HEIGHT,
    WIDTH,
    build_battle_card_svg,
    build_public_replay,
    render_battle_card_png,
)
from app.services.chronicle_card import _card_lines, card_caption
from app.services.daily_chronicle import generate_daily_chronicle

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[2]


def _seed(troops: tuple[int, int, int] = (40, 12, 5)) -> int:
    """conftest 會在每個測試前 drop_all/create_all，所以每次都要自己 seed。"""
    db = SessionLocal()
    try:
        db.add(
            City(
                name=settings.city_name,
                base_url="http://localhost:8000",
                treasury_gold=3398,
                treasury_food=0,
                city_wall=300,
            )
        )
        user = User(
            username="arena_owner",
            email="arena_owner@example.com",
            password_hash="x",
            is_admin=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        agent = Agent(
            owner_user_id=user.id,
            name="小魚兒",
            role="平民",
            home_city=settings.city_name,
            current_city=settings.city_name,
            gold=1000,
            food=100,
            reputation=20,
            infantry=troops[0],
            archer=troops[1],
            cavalry=troops[2],
            martial=60,
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
        return agent.id
    finally:
        db.close()


def _enable_arena(monkeypatch) -> None:
    monkeypatch.setattr(settings, "arena_enabled", True)


def _agent_snapshot(agent_id: int) -> tuple[int, int]:
    db = SessionLocal()
    try:
        agent = db.get(Agent, agent_id)
        return (agent.infantry + agent.archer + agent.cavalry, agent.gold)
    finally:
        db.close()


def test_arena_is_off_by_default_and_does_not_write_anything(monkeypatch):
    agent_id = _seed()
    monkeypatch.setattr(settings, "arena_enabled", False)
    db = SessionLocal()
    try:
        result = arena_exhibition.run_daily_arena(db)
        assert result["status"] == "disabled"
        assert db.query(BattleLog).count() == 0
        assert db.query(ChronicleEntry).filter(ChronicleEntry.event_type == "battle").count() == 0
    finally:
        db.close()
    assert _agent_snapshot(agent_id) == (57, 1000)


def test_arena_creates_one_exhibition_per_day_without_touching_agents(monkeypatch):
    agent_id = _seed()
    _enable_arena(monkeypatch)
    db = SessionLocal()
    try:
        first = arena_exhibition.run_daily_arena(db)
        assert first["status"] == "created"
        assert first["battle_id"].startswith("arena_")
        assert first["exhibition"] is True
        assert db.query(BattleLog).count() == 1
        assert db.query(ChronicleEntry).filter(ChronicleEntry.event_type == "battle").count() == 1
        entry = (
            db.query(ChronicleEntry)
            .filter(ChronicleEntry.event_type == "battle")
            .first()
        )
        assert "演武" in entry.title
        assert "不計戰績" in entry.content

        second = arena_exhibition.run_daily_arena(db)
        assert second["status"] == "skipped"
        assert db.query(BattleLog).count() == 1

        forced = arena_exhibition.run_daily_arena(db, force=True)
        assert forced["status"] == "created"
        assert db.query(BattleLog).count() == 2
    finally:
        db.close()
    # 演武不得改寫任何 agent 狀態：兵力與金錢都要原封不動。
    assert _agent_snapshot(agent_id) == (57, 1000)


def test_arena_rotates_among_lords_with_real_troops():
    """線上有大量 0～2 兵的空殼，演武不能挑到他們，否則三回合沒有傷亡可播。"""
    _seed()
    db = SessionLocal()
    try:
        owner = db.query(User).first()
        for i, troops in enumerate((1, 2, 3, 70, 80, 90)):
            db.add(
                Agent(
                    owner_user_id=owner.id,
                    name=f"測試{i}",
                    role="平民",
                    home_city=settings.city_name,
                    current_city=settings.city_name,
                    infantry=troops,
                )
            )
        db.commit()
        picks = {
            arena_exhibition._pick_challenger(db, f"2026-11-{day:02d}").name
            for day in range(5, 25)
        }
    finally:
        db.close()
    assert "測試0" not in picks
    assert "測試1" not in picks
    assert len(picks) > 1  # 每天換人，不是永遠同一位


def test_public_battle_endpoints_require_no_token_and_leak_no_account_data(monkeypatch):
    _seed()
    _enable_arena(monkeypatch)
    db = SessionLocal()
    try:
        result = arena_exhibition.run_daily_arena(db)
        battle_id = result["battle_id"]
    finally:
        db.close()

    reports = client.get("/world/public/battle/reports")
    assert reports.status_code == 200
    assert reports.json()["data"]["items"][0]["battle_id"] == battle_id

    latest = client.get("/world/public/battle/latest")
    assert latest.status_code == 200
    assert latest.json()["data"]["exhibition"] is True

    replay = client.get(f"/world/public/battle/replay/{battle_id}?lang=zh")
    assert replay.status_code == 200
    data = replay.json()["data"]
    assert len(data["rounds"]) == 3
    assert data["exhibition"] is True
    assert data["verdict"] and data["links"]["replay"].endswith(battle_id)
    assert all("caption" in row and "attacker_remaining" in row for row in data["rounds"])
    payload = json.dumps(data, ensure_ascii=False)
    for secret in ("owner_user_id", "password_hash", "email", "claim_code", "access_token"):
        assert secret not in payload

    assert client.get("/world/public/battle/card.png").status_code == 200
    assert client.get("/world/public/battle/card.svg").status_code == 200
    post = client.get("/world/public/battle/post?lang=zh")
    assert post.status_code == 200
    assert post.json()["data"]["type"] == "battle_report"
    assert battle_id in post.json()["data"]["link"]
    assert client.get("/world/public/battle/replay/does-not-exist").status_code == 404


def test_real_pve_battle_is_replayable_without_arena():
    agent_id = _seed()
    db = SessionLocal()
    try:
        db.add(
            BattleLog(
                attacker_city=settings.city_name,
                defender_city="PVE:huangjin",
                attacker_agent_id=agent_id,
                defender_agent_id=None,
                attack_power=180.0,
                defense_power=90.0,
                outcome="attacker_win",
                loot_gold=320,
                loot_food=50,
                request_id="pve_test_battle_1",
            )
        )
        db.add(
            ActionLog(
                agent_id=agent_id,
                city_name=settings.city_name,
                action_type="pve_challenge",
                payload_json="{}",
                energy_cost=0,
                result_json=json.dumps(
                    {
                        "battle_id": "pve_test_battle_1",
                        "losses": {"infantry": 6, "archer": 2, "cavalry": 1},
                        "enemy_losses": {"infantry": 15, "archer": 3, "cavalry": 0},
                    }
                ),
            )
        )
        db.commit()
        replay = build_public_replay(db, "pve_test_battle_1", "zh")
    finally:
        db.close()

    assert replay is not None
    assert replay["mode"] == "pve"
    assert replay["exhibition"] is False
    assert "黃巾之亂" in replay["summary"]["defender_name"]
    assert len(replay["rounds"]) == 3
    assert sum(row["attacker_loss"] for row in replay["rounds"]) == 9
    assert sum(row["defender_loss"] for row in replay["rounds"]) == 18


def test_battle_card_is_1200x630_and_survives_missing_font(monkeypatch):
    _seed()
    _enable_arena(monkeypatch)
    db = SessionLocal()
    try:
        battle_id = arena_exhibition.run_daily_arena(db)["battle_id"]
        replay = build_public_replay(db, battle_id, "zh")
    finally:
        db.close()

    assert replay is not None
    png = render_battle_card_png(replay)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    from PIL import Image

    assert Image.open(io.BytesIO(png)).size == (WIDTH, HEIGHT)
    svg = build_battle_card_svg(replay)
    assert f'width="{WIDTH}"' in svg and battle_id in svg

    monkeypatch.setattr(chronicle_card, "FONT_CANDIDATES", ())
    chronicle_card._font.cache_clear()
    try:
        assert render_battle_card_png(replay).startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        chronicle_card._font.cache_clear()


def test_daily_story_and_post_package_carry_the_battle(monkeypatch):
    _seed()
    _enable_arena(monkeypatch)
    db = SessionLocal()
    try:
        arena_exhibition.run_daily_arena(db)
        story = generate_daily_chronicle(db, lang="zh", force=True)
        assert any("/battle/replay/" in line for line in story["lines"])

        result = chronicle_publish.publish_daily_post(db, force=True)
        package = result["package"]
        assert package["battle"] is not None
        assert "今日戰報" in package["caption"]
        assert "battle/replay/" in package["caption"]
        assert package["battle_image_url"].endswith("&lang=zh")
        assert "battle/replay/" in package["caption_long"]
    finally:
        db.close()


def test_card_lines_and_caption_prioritise_events_over_baseline_numbers():
    story = {
        "lang": "zh",
        "headline": "【史記・2026-11-05　洛陽】",
        "lines": [
            "洛陽城現有 51 位諸侯；國庫存金 3,398、糧 0。",
            "小魚兒 庫中存金 32,473，居全城之首。",
            "握兵最多者為 Claw-AI，僅 61 人。",
            "【天下有事】洛陽糧盡：城倉 0 / 500 糧。",
            "【天下有事】丞相唯一席：丞相席 1，已佔 0。",
            "另有 1 場交鋒；小魚兒 對 校場守軍，攻方勝。",
        ],
        "quotes": [],
        "aphorism": "金滿倉，倉無糧。",
        "share_text": "",
    }
    shown, _ = _card_lines(story)
    assert "【天下有事】" in shown[0]
    assert sum("【天下有事】" in line for line in shown) >= 2
    caption_lines = card_caption(story, "zh").split("\n")
    assert "【天下有事】" in caption_lines[1]


def test_admin_arena_endpoints_stay_protected():
    assert client.post("/admin/battle/arena/run").status_code in (401, 403)
    assert client.get("/admin/battle/arena/status").status_code in (401, 403)

    app.dependency_overrides[get_current_admin] = lambda: None
    try:
        status = client.get("/admin/battle/arena/status")
        assert status.status_code == 200
        assert "enabled" in status.json()["data"]
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


def test_prod_compose_and_env_example_carry_arena_defaults():
    compose = (ROOT / "deploy/prod/docker-compose.server.yml").read_text(encoding="utf-8")
    for var in ("ARENA_ENABLED", "ARENA_HOUR_HKT"):
        assert len(re.findall(rf"^\s+{var}:", compose, flags=re.MULTILINE)) == 2, var
    assert "${ARENA_ENABLED:-true}" in compose
    assert "${ARENA_HOUR_HKT:-7}" in compose
    example = (ROOT / "deploy/prod/.env.example").read_text(encoding="utf-8")
    assert "ARENA_ENABLED=true" in example
    assert "ARENA_ENABLED=false" in example
