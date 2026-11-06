"""十四日賽季：開季／結算、霸主積分、結局卡、史記整合與公開端點。"""

import io
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Agent, BattleLog, ChronicleEntry, City, User
from app.services import season as season_service
from app.services.daily_chronicle import build_story, collect_daily_facts
from app.services.season import (
    CURRENT_KEY,
    build_ending_card_svg,
    ending_card_payload,
    ensure_season,
    load_archive,
    load_current,
    render_ending_card_png,
    season_post_package,
    season_summary,
    standings,
)
from app.services.system_state import get_state

client = TestClient(app)

OPEN_AT = datetime(2026, 11, 6, 1, 0, tzinfo=timezone.utc)  # 09:00 HKT, 2026-11-06
AFTER_END = datetime(2026, 11, 20, 1, 0, tzinfo=timezone.utc)  # 09:00 HKT, 2026-11-20


def _seed(n: int = 2) -> list[int]:
    """conftest 每個測試前 drop_all/create_all，所以每次都要自己 seed。"""
    db = SessionLocal()
    try:
        db.add(
            City(
                name=settings.city_name,
                base_url="http://localhost:8000",
                treasury_gold=3398,
                treasury_food=0,
            )
        )
        ids = []
        for i in range(n):
            user = User(
                username=f"season_owner_{i}",
                email=f"season_owner_{i}@example.com",
                password_hash="x",
                is_admin=False,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            agent = Agent(
                owner_user_id=user.id,
                name=f"諸侯{i}",
                role="平民",
                home_city=settings.city_name,
                current_city=settings.city_name,
                gold=1000 + i * 12000,
                food=400,
                reputation=20 + i * 30,
                infantry=10 + i * 30,
                archer=5,
                cavalry=0,
                martial=55,
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
            ids.append(agent.id)
        return ids
    finally:
        db.close()


def _snapshot(agent_id: int) -> tuple[int, int, int]:
    db = SessionLocal()
    try:
        agent = db.get(Agent, agent_id)
        return (agent.gold, agent.reputation, agent.infantry + agent.archer + agent.cavalry)
    finally:
        db.close()


def test_ensure_season_opens_once_and_is_idempotent():
    _seed()
    db = SessionLocal()
    try:
        first = ensure_season(db, now=OPEN_AT, enabled=True)
        assert first["action"] == "opened"
        state = load_current(db)
        assert state["season_id"] == "s20261106"
        assert state["index"] == 1
        assert state["start_date"] == "2026-11-06"
        assert state["end_date"] == "2026-11-19"  # 14 個 HKT 日（含起始日）
        assert ensure_season(db, now=OPEN_AT, enabled=True)["action"] == "none"
        assert db.query(ChronicleEntry).filter(ChronicleEntry.event_type == "season_open").count() == 1
    finally:
        db.close()


def test_disabled_season_never_writes_state():
    _seed()
    db = SessionLocal()
    try:
        assert ensure_season(db, now=OPEN_AT, enabled=False)["action"] == "disabled"
        assert get_state(db, CURRENT_KEY) == ""
    finally:
        db.close()


def test_roll_writes_archive_annals_and_opens_next_season():
    _seed()
    db = SessionLocal()
    try:
        ensure_season(db, now=OPEN_AT, enabled=True)
        result = ensure_season(db, now=AFTER_END, enabled=True)
        assert result["action"] == "rolled"
        assert result["closed"]["season_id"] == "s20261106"
        assert result["season"]["index"] == 2
        assert result["season"]["start_date"] == "2026-11-20"

        archive = load_archive(db, "s20261106")
        assert archive is not None
        assert archive["total_agents"] == 2
        assert archive["winner"]["name"] == "諸侯1"
        assert "【本紀" in archive["chronicle_zh"]
        assert db.query(ChronicleEntry).filter(ChronicleEntry.event_type == "season_close").count() == 1

        announcement = json.loads(get_state(db, season_service.ANNOUNCEMENT_KEY))
        assert len(announcement["zh"]) == 2  # 季末本紀 + 開季詔書
        assert "季末本紀" in announcement["zh"][0]
        assert "開季詔書" in announcement["zh"][1]
    finally:
        db.close()


def test_score_formula_caps_resources_and_counts_wins():
    agent_ids = _seed()
    db = SessionLocal()
    try:
        ensure_season(db, now=OPEN_AT, enabled=True)
        # 真實 PVP：諸侯1 攻方勝兩場；金／糧遠超上限，只能拿到封頂分。
        for offset in (1, 2):
            db.add(
                BattleLog(
                    attacker_city=settings.city_name,
                    defender_city=settings.city_name,
                    attacker_agent_id=agent_ids[1],
                    defender_agent_id=agent_ids[0],
                    attack_power=100,
                    defense_power=50,
                    outcome="attacker_win",
                    request_id=f"pvp-{offset}",
                    created_at=datetime(2026, 11, 6, 3, 0) + timedelta(days=offset),
                )
            )
        db.commit()
        rows = standings(db, load_current(db))
        top = rows[0]
        assert top["name"] == "諸侯1"
        assert top["wins"] == 2
        # 聲望 50×2 + 兵力 45×3 + 金 100 + 糧 2 + 勝場 80 + 勢力 0
        assert top["breakdown"] == {
            "reputation": 100,
            "troops": 135,
            "gold": 100,
            "food": 2,
            "wins": 80,
            "faction": 0,
        }
        assert top["score"] == 417
        assert top["title_zh"] == "霸主"
    finally:
        db.close()


def test_arena_exhibition_does_not_count_as_win():
    agent_ids = _seed()
    db = SessionLocal()
    try:
        ensure_season(db, now=OPEN_AT, enabled=True)
        db.add(
            BattleLog(
                attacker_city=settings.city_name,
                defender_city="校場:arena",
                attacker_agent_id=agent_ids[0],
                defender_agent_id=None,
                attack_power=100,
                defense_power=102,
                outcome="defender_win",
                request_id="arena_20261106_deadbeef",
                created_at=datetime(2026, 11, 6, 3, 0),
            )
        )
        db.commit()
        assert all(row["wins"] == 0 for row in standings(db, load_current(db)))
    finally:
        db.close()


def test_settlement_never_mutates_agent_state():
    agent_ids = _seed()
    before = [_snapshot(agent_id) for agent_id in agent_ids]
    db = SessionLocal()
    try:
        ensure_season(db, now=OPEN_AT, enabled=True)
        ensure_season(db, now=AFTER_END, enabled=True)
    finally:
        db.close()
    assert [_snapshot(agent_id) for agent_id in agent_ids] == before


def test_leaderboard_exposes_only_public_fields(monkeypatch):
    # days_left 是相對「今天 HKT」算出來的；固定住日期，測試才不會隔天就失敗。
    monkeypatch.setattr(season_service, "_hkt_date", lambda _now=None: date(2026, 11, 6))
    _seed()
    db = SessionLocal()
    try:
        ensure_season(db, now=OPEN_AT, enabled=True)
        row = season_summary(db)["leaderboard"][0]
        forbidden = {"owner", "email", "owner_user_id", "password_hash", "claim_code", "token", "payload"}
        assert not (forbidden & set(row))
        assert {"agent_id", "name", "score", "rank", "breakdown", "title_zh"} <= set(row)
        assert season_summary(db)["days_left"] == 14
        assert season_summary(db)["rules"]["length_days"] == 14
    finally:
        db.close()


def test_ending_card_payload_from_current_and_archive():
    agent_ids = _seed()
    db = SessionLocal()
    try:
        ensure_season(db, now=OPEN_AT, enabled=True)
        live = ending_card_payload(db, agent_ids[0], None, "zh")
        assert live is not None
        assert live["closed"] is False
        assert "/season/ending-card.png" in live["links"]["card_png"]
        assert "暫居首位" in live["ending"] or "勝負未定" in live["ending"]
        assert "定鼎" not in live["ending"]

        ensure_season(db, now=AFTER_END, enabled=True)
        champion = ending_card_payload(db, agent_ids[1], "s20261106", "zh")
        assert champion is not None and "定鼎" in champion["ending"]
        archived = ending_card_payload(db, agent_ids[0], "s20261106", "zh")
        assert archived is not None
        assert archived["closed"] is True
        assert archived["season_id"] == "s20261106"
        assert ending_card_payload(db, 999999, "s20261106", "zh") is None
        assert ending_card_payload(db, agent_ids[0], "s19990101", "zh") is None
    finally:
        db.close()


def test_ending_card_svg_escapes_agent_name():
    data = {
        "season_id": "s20261106",
        "index": 1,
        "start_date": "2026-11-06",
        "end_date": "2026-11-19",
        "closed": True,
        "lang": "zh",
        "agent_name": "<script>alert(1)</script>",
        "rank": 1,
        "total": 2,
        "score": 417,
        "title": "霸主",
        "ending": "史官曰：<b>天下</b>已定。",
        "reputation": 50,
        "troops": 45,
        "gold": 13000,
        "food": 400,
        "wins": 2,
        "city": "洛陽",
    }
    svg = build_ending_card_svg(data)
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    assert "&lt;b&gt;" in svg


def test_ending_card_png_is_valid_image():
    pytest.importorskip("PIL")
    from PIL import Image

    payload = {
        "season_id": "s20261106",
        "index": 1,
        "start_date": "2026-11-06",
        "end_date": "2026-11-19",
        "closed": True,
        "lang": "zh",
        "agent_name": "小魚兒",
        "rank": 1,
        "total": 2,
        "score": 417,
        "title": "霸主",
        "ending": "一季之內，勝 2 場、握兵 45。",
        "reputation": 50,
        "troops": 45,
        "gold": 13000,
        "food": 400,
        "wins": 2,
        "city": "洛陽",
    }
    png = render_ending_card_png(payload)
    image = Image.open(io.BytesIO(png))
    assert image.size == (1200, 630)
    assert image.format == "PNG"


def test_season_announcement_appears_in_daily_story():
    _seed()
    db = SessionLocal()
    try:
        ensure_season(db, now=OPEN_AT, enabled=True)
        story = build_story(collect_daily_facts(db), "zh", "2026-11-06")
        assert any("開季詔書" in line for line in story["lines"])
        # 舊公告（超過 26 小時）不該永久卡在史記裡
        season_service._set_announcement(db, OPEN_AT, ["【天下有事】舊詔書"], ["[Old decree]"])
        stale = json.loads(get_state(db, season_service.ANNOUNCEMENT_KEY))
        stale["created_at"] = "2020-01-01T00:00:00+00:00"
        from app.services.system_state import set_state

        set_state(db, season_service.ANNOUNCEMENT_KEY, json.dumps(stale, ensure_ascii=False))
        db.commit()
        story2 = build_story(collect_daily_facts(db), "zh", "2026-11-06")
        assert not any("舊詔書" in line for line in story2["lines"])
    finally:
        db.close()


def test_public_season_endpoints_are_anonymous():
    agent_ids = _seed()
    db = SessionLocal()
    try:
        ensure_season(db, now=OPEN_AT, enabled=True)
    finally:
        db.close()

    current = client.get("/world/public/season/current")
    assert current.status_code == 200
    assert current.json()["data"]["season"]["season_id"] == "s20261106"
    assert len(current.json()["data"]["leaderboard"]) == 2

    assert client.get("/world/public/season/history").status_code == 200
    assert client.get("/world/public/season/archive/nope").status_code == 404
    svg = client.get(f"/world/public/season/ending-card.svg?agent_id={agent_ids[0]}")
    assert svg.status_code == 200
    assert "image/svg+xml" in svg.headers["content-type"]
    png = client.get(f"/world/public/season/ending-card.png?agent_id={agent_ids[0]}")
    assert png.status_code == 200
    assert png.headers["content-type"] in {"image/png", "image/svg+xml"}
    post = client.get("/world/public/season/post")
    assert post.status_code == 200
    assert post.json()["data"]["type"] == "season"


def test_cached_daily_post_gets_opening_decree_backfilled():
    """08:00 已快取的發文包，部署後開季詔書要當天就進文案，不必等隔天。"""
    from app.services.chronicle_publish import current_post_package, publish_daily_post

    _seed()
    db = SessionLocal()
    try:
        publish_daily_post(db, now=OPEN_AT, force=True)
        assert "開季詔書" not in current_post_package(db, "zh")["caption_long"]
        ensure_season(db, now=OPEN_AT, enabled=True)
        package = current_post_package(db, "zh")
        assert "開季詔書" in package["caption_long"]
        assert "開季詔書" in package["caption"]
        assert package["season_notice"]
        rows = package["caption"].split("\n")
        decree_at = next(i for i, line in enumerate(rows) if "開季詔書" in line)
        tags_at = next(i for i, line in enumerate(rows) if line.startswith("#"))
        assert decree_at < tags_at  # 詔書在文案內文，不在 hashtags 後面
        # 只補回傳值，不改寫 DB 裡的快取
        from app.services.system_state import get_state
        from app.services.chronicle_publish import PACKAGE_KEY

        assert "開季詔書" not in json.loads(get_state(db, PACKAGE_KEY))["caption_long"]
    finally:
        db.close()


def test_live_season_post_never_claims_a_winner():
    """賽季還沒結算，發文包與領先榜不能寫「定鼎」。"""
    _seed()
    db = SessionLocal()
    try:
        ensure_season(db, now=OPEN_AT, enabled=True)
        package = season_post_package(db, "zh")
        assert package["closed"] is False
        assert "定鼎" not in package["caption"]
        assert "暫居首位" in package["caption"]
        assert all("定鼎" not in row["ending_zh"] for row in season_summary(db, "zh")["leaderboard"])
    finally:
        db.close()


def test_season_post_package_uses_last_champion_after_roll():
    agent_ids = _seed()
    db = SessionLocal()
    try:
        ensure_season(db, now=OPEN_AT, enabled=True)
        ensure_season(db, now=AFTER_END, enabled=True)
        package = season_post_package(db, "zh")
        assert package["closed"] is True
        assert package["season_id"] == "s20261106"
        assert package["agent"]["name"] == "諸侯1"
        assert "季末本紀" in package["headline"]
        assert "/season" in package["caption"]
    finally:
        db.close()
