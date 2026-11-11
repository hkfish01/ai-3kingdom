"""1.36.0：PvE 止血與賽季勝場積分回歸。

背景：線上一位諸侯用「零體力、無上限、必勝」的 /pve/challenge 刷出 1806 場
勝利與十萬金，霸主積分因此是第二名的 274 倍。這份測試逐條釘死修復後的規則，
並驗證舊戰報會被新的即時積分公式自動排除，不需 migration 或回沖。
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api import routes_combat
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import ActionLog, Agent, BattleLog, City, PveChallengeDaily, User
from app.rules import PVE_DAILY_LIMIT, PVE_ENERGY_COST, PVE_REWARD_DECAY, PVE_REWARD_FLOOR
from app.services import season as season_service

client = TestClient(app)

OPEN_AT = datetime(2026, 11, 6, 1, 0, tzinfo=timezone.utc)
BATTLE_AT = datetime(2026, 11, 6, 3, 0)
TROOPS = {"infantry": 200, "archer": 100, "cavalry": 50}


def _auth(username: str) -> dict:
    assert client.post(
        "/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "Aa1234!!"},
    ).status_code == 200
    token = client.post(
        "/auth/login", json={"username": username, "password": "Aa1234!!"}
    ).json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def _agent(headers: dict, name: str) -> int:
    resp = client.post("/agent/register", headers=headers, json={"name": name, "role": "武將"})
    assert resp.status_code == 200
    return resp.json()["data"]["agent_id"]


def _seed(agent_id: int, energy: int = 100) -> None:
    """給足兵力，讓連續 5 次挑戰都不會因戰損而卡在兵力不足。"""
    with SessionLocal() as db:
        agent = db.get(Agent, agent_id)
        agent.infantry = 100000
        agent.archer = 100000
        agent.cavalry = 100000
        agent.gold = 1000
        agent.food = 1000
        agent.martial = 95
        agent.energy = energy
        db.add(agent)
        db.commit()


def _refill_energy(agent_id: int) -> None:
    with SessionLocal() as db:
        agent = db.get(Agent, agent_id)
        agent.energy = 100
        db.add(agent)
        db.commit()


def _challenge(headers: dict, agent_id: int, dungeon_id: str = "huangjin", troops: dict | None = None):
    return client.post(
        "/pve/challenge",
        headers=headers,
        json={
            "agent_id": agent_id,
            "dungeon_id": dungeon_id,
            "troops": troops or TROOPS,
        },
    )


def _counter(agent_id: int, day: str | None = None) -> int | None:
    target = day or datetime.now(timezone.utc).date().isoformat()
    with SessionLocal() as db:
        row = (
            db.query(PveChallengeDaily)
            .filter(PveChallengeDaily.agent_id == agent_id, PveChallengeDaily.day == target)
            .first()
        )
        return row.count if row else None


def _battle_count() -> int:
    with SessionLocal() as db:
        return db.query(BattleLog).count()


# ---------------------------------------------------------------------------
# A：PvE 四道閘
# ---------------------------------------------------------------------------


def test_dungeons_publish_the_written_limits():
    headers = _auth("pve_rules")
    resp = client.get("/pve/dungeons", headers=headers)
    assert resp.status_code == 200
    rules = resp.json()["data"]["rules"]
    assert rules["daily_limit"] == PVE_DAILY_LIMIT == 5
    assert rules["energy_cost"] == PVE_ENERGY_COST == 20
    assert rules["reward_decay_per_attempt"] == PVE_REWARD_DECAY == 0.2
    assert rules["reward_multiplier_floor"] == PVE_REWARD_FLOOR == 0.2
    assert rules["first_clear_bonus_undiscounted"] is True
    assert rules["day_boundary"] == "UTC"
    assert rules["failed_challenge_still_costs_energy_and_attempt"] is True


def test_first_challenge_charges_energy_and_reports_remaining():
    headers = _auth("pve_energy")
    agent_id = _agent(headers, "EnergyHero")
    _seed(agent_id, energy=100)

    resp = _challenge(headers, agent_id)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["daily_used"] == 1
    assert data["daily_limit"] == 5
    assert data["daily_remaining"] == 4
    assert data["energy_cost"] == 20
    assert data["reward_multiplier"] == 1.0

    with SessionLocal() as db:
        agent = db.get(Agent, agent_id)
        assert agent.energy == 80
        log = db.query(ActionLog).filter(ActionLog.action_type == "pve_challenge").one()
        assert log.energy_cost == 20
        result = json.loads(log.result_json)
        assert result["daily_used"] == 1
        assert result["daily_limit"] == 5
    assert _counter(agent_id) == 1


def test_sixth_challenge_is_blocked_and_changes_nothing():
    headers = _auth("pve_cap")
    agent_id = _agent(headers, "CapHero")
    _seed(agent_id)

    for expected_used in range(1, PVE_DAILY_LIMIT + 1):
        _refill_energy(agent_id)
        resp = _challenge(headers, agent_id)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["daily_used"] == expected_used
    assert _counter(agent_id) == PVE_DAILY_LIMIT
    assert _battle_count() == PVE_DAILY_LIMIT

    _refill_energy(agent_id)
    with SessionLocal() as db:
        before = db.get(Agent, agent_id)
        snapshot = (before.gold, before.food, before.energy, before.infantry)

    blocked = _challenge(headers, agent_id)
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "PVE_DAILY_LIMIT_REACHED"

    with SessionLocal() as db:
        after = db.get(Agent, agent_id)
        assert (after.gold, after.food, after.energy, after.infantry) == snapshot
    assert _counter(agent_id) == PVE_DAILY_LIMIT
    assert _battle_count() == PVE_DAILY_LIMIT


def test_insufficient_energy_does_not_consume_the_attempt():
    headers = _auth("pve_low_energy")
    agent_id = _agent(headers, "TiredHero")
    _seed(agent_id, energy=10)

    resp = _challenge(headers, agent_id)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INSUFFICIENT_ENERGY"

    with SessionLocal() as db:
        assert db.get(Agent, agent_id).energy == 10
    assert _counter(agent_id) in (0, None)
    assert _battle_count() == 0


def test_failed_power_gate_does_not_consume_the_attempt():
    headers = _auth("pve_power_gate_2")
    agent_id = _agent(headers, "WeakHero")
    _seed(agent_id)

    resp = _challenge(
        headers, agent_id, dungeon_id="chibi", troops={"infantry": 1, "archer": 0, "cavalry": 0}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PVE_POWER_TOO_LOW"

    with SessionLocal() as db:
        assert db.get(Agent, agent_id).energy == 100
    assert _counter(agent_id) in (0, None)
    assert _battle_count() == 0

    # 驗證失敗不算次數，補足戰力後仍應拿到第 1 次的完整係數。
    ok = _challenge(headers, agent_id)
    assert ok.status_code == 200
    assert ok.json()["data"]["daily_used"] == 1
    assert ok.json()["data"]["reward_multiplier"] == 1.0


def test_rewards_decay_but_first_clear_bonus_is_undiscounted(monkeypatch):
    headers = _auth("pve_decay")
    agent_id = _agent(headers, "DecayHero")
    _seed(agent_id)
    # 固定隨機獎勵為 200 金／200 糧，才能精確驗證係數。
    monkeypatch.setattr(routes_combat, "random", SimpleNamespace(randint=lambda a, b: 200))

    multipliers = []
    golds = []
    for _ in range(PVE_DAILY_LIMIT):
        _refill_energy(agent_id)
        resp = _challenge(headers, agent_id)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        multipliers.append(round(data["reward_multiplier"], 2))
        golds.append(data["rewards"]["gold"])

    assert multipliers == [1.0, 0.8, 0.6, 0.4, 0.2]
    # 第 1 次 = 200×1.0 + 500 首通；之後 = 200×係數，首通不再發。
    assert golds == [700, 160, 120, 80, 40]


def test_new_utc_day_resets_the_counter(monkeypatch):
    headers = _auth("pve_new_day")
    agent_id = _agent(headers, "NewDayHero")
    _seed(agent_id)

    today = datetime.now(timezone.utc).date().isoformat()
    tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    monkeypatch.setattr(routes_combat, "_utc_day", lambda: today)
    for _ in range(PVE_DAILY_LIMIT):
        _refill_energy(agent_id)
        assert _challenge(headers, agent_id).status_code == 200
    assert _challenge(headers, agent_id).json()["error"]["code"] == "PVE_DAILY_LIMIT_REACHED"

    monkeypatch.setattr(routes_combat, "_utc_day", lambda: tomorrow)
    _refill_energy(agent_id)
    resp = _challenge(headers, agent_id)
    assert resp.status_code == 200
    assert resp.json()["data"]["daily_used"] == 1
    assert _counter(agent_id, today) == PVE_DAILY_LIMIT
    assert _counter(agent_id, tomorrow) == 1


def test_daily_counter_row_is_unique_per_agent_and_day():
    headers = _auth("pve_counter_unique")
    agent_id = _agent(headers, "CounterHero")
    _seed(agent_id)
    day = datetime.now(timezone.utc).date().isoformat()
    with SessionLocal() as db:
        first = routes_combat._get_or_create_pve_daily_counter(db, agent_id, day)
        second = routes_combat._get_or_create_pve_daily_counter(db, agent_id, day)
        assert first.id == second.id
        db.commit()


# ---------------------------------------------------------------------------
# B：賽季勝場排除 PvE、封頂，且自動溯及歷史戰報
# ---------------------------------------------------------------------------


def _seed_season() -> list[int]:
    with SessionLocal() as db:
        db.add(City(name=settings.city_name, base_url="http://localhost:8000"))
        ids = []
        for i in range(2):
            user = User(
                username=f"pve_season_owner_{i}",
                email=f"pve_season_owner_{i}@example.com",
                password_hash="x",
                is_admin=False,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            agent = Agent(
                owner_user_id=user.id,
                name=f"賽季諸侯{i}",
                role="平民",
                home_city=settings.city_name,
                current_city=settings.city_name,
                gold=1000,
                food=400,
                reputation=20,
                infantry=40,
                archer=5,
                cavalry=0,
                martial=55,
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
            ids.append(agent.id)
        return ids


def _add_battles(agent_id: int, pve: int, pvp: int) -> None:
    with SessionLocal() as db:
        for i in range(pve):
            db.add(
                BattleLog(
                    attacker_city=settings.city_name,
                    defender_city="PVE:huangjin",
                    attacker_agent_id=agent_id,
                    defender_agent_id=None,
                    attack_power=100,
                    defense_power=50,
                    outcome="attacker_win",
                    request_id=f"pve_{i}",
                    created_at=BATTLE_AT + timedelta(minutes=i),
                )
            )
        for i in range(pvp):
            db.add(
                BattleLog(
                    attacker_city=settings.city_name,
                    defender_city=settings.city_name,
                    attacker_agent_id=agent_id,
                    defender_agent_id=None,
                    attack_power=100,
                    defense_power=50,
                    outcome="attacker_win",
                    request_id=f"pvp_{i}",
                    created_at=BATTLE_AT + timedelta(minutes=pve + i),
                )
            )
        db.commit()


def test_1806_pve_wins_no_longer_buy_the_crown():
    """直接重現線上情境：1806 場副本勝利 + 3 場真實 PvP，只應計 3 場。"""
    agent_ids = _seed_season()
    with SessionLocal() as db:
        season_service.ensure_season(db, now=OPEN_AT, enabled=True)
    _add_battles(agent_ids[0], pve=1806, pvp=3)

    with SessionLocal() as db:
        rows = season_service.standings(db, season_service.load_current(db))
        top = next(r for r in rows if r["agent_id"] == agent_ids[0])
        assert top["wins"] == 3
        assert top["breakdown"]["wins"] == 120
        assert 40 * 1806 not in (top["score"], top["breakdown"]["wins"])
        assert top["score"] < 1000  # 舊規則在這裡會是七萬多分


def test_scored_wins_are_capped_even_for_real_pvp():
    agent_ids = _seed_season()
    with SessionLocal() as db:
        season_service.ensure_season(db, now=OPEN_AT, enabled=True)
    _add_battles(agent_ids[0], pve=0, pvp=40)

    with SessionLocal() as db:
        rows = season_service.standings(db, season_service.load_current(db))
        top = next(r for r in rows if r["agent_id"] == agent_ids[0])
        assert top["wins"] == season_service.SEASON_WINS_CAP == 20
        assert top["breakdown"]["wins"] == 20 * 40 == 800


def test_arena_and_legacy_pve_marker_are_both_excluded():
    agent_ids = _seed_season()
    with SessionLocal() as db:
        season_service.ensure_season(db, now=OPEN_AT, enabled=True)
        for request_id, defender_city in (
            ("arena_20261106_deadbeef", "校場:arena"),
            ("legacy_pve_no_prefix", "PVE:chibi"),
        ):
            db.add(
                BattleLog(
                    attacker_city=settings.city_name,
                    defender_city=defender_city,
                    attacker_agent_id=agent_ids[0],
                    defender_agent_id=None,
                    attack_power=100,
                    defense_power=50,
                    outcome="attacker_win",
                    request_id=request_id,
                    created_at=BATTLE_AT,
                )
            )
        db.commit()
        rows = season_service.standings(db, season_service.load_current(db))
        assert all(row["wins"] == 0 for row in rows)


def test_season_rules_publish_the_cap_and_exclusions():
    rules = season_service.season_rules()
    assert rules["wins_cap"] == 20
    assert rules["wins_points"] == 40
    assert "20" in rules["score_formula_zh"] and "20" in rules["score_formula_en"]
    assert "副本" in rules["exclusions_zh"]
    assert "PvE" in rules["exclusions_en"]


def test_ensure_schema_creates_the_counter_table_even_when_auto_schema_is_off():
    """production 的 AUTO_CREATE_SCHEMA=false，少了這層保險第一次征伐就 500。"""
    from sqlalchemy import inspect

    from app.db import engine
    from app.services import pve_limits

    PveChallengeDaily.__table__.drop(bind=engine, checkfirst=True)
    assert "pve_challenge_daily" not in inspect(engine).get_table_names()
    pve_limits.ensure_schema(engine)
    assert "pve_challenge_daily" in inspect(engine).get_table_names()
    pve_limits.ensure_schema(engine)  # 重複啟動冪等


def test_pve_bulletin_is_archived_and_every_release_stays_dual_audience():
    """1.36.0 的 PvE 規則公告即使不再是最前一則也要留著；最新版本仍須雙讀。

    不把版號釘死：之後每次升版都該由 check_release_notes.py 與
    test_release_notes.py 把關，而不是讓舊版功能測試擋住新公告。
    """
    from app.services import updates as updates_service

    entries = updates_service._entries()
    by_version = {entry["version"]: entry for entry in entries}
    archived = by_version["1.36.0"]
    for key in ("title_zh", "title_en", "detail_zh", "detail_en", "summary_zh", "summary_en", "agent_zh", "agent_en"):
        assert archived.get(key), key
    assert archived.get("tags") and archived.get("docs") and archived.get("endpoints") and archived.get("actions")
    assert any("pve" in str(x).lower() for x in archived["endpoints"])
    assert any("season" in str(x).lower() for x in archived["endpoints"])
    assert any("pve" in str(x).lower() for x in archived["actions"])

    latest = entries[0]
    assert latest["version"] == settings.app_version
    assert latest.get("summary_zh") and latest.get("summary_en")
    assert latest.get("agent_zh") and latest.get("agent_en")
    assert latest.get("endpoints") and latest.get("actions")
    assert latest["summary_zh"] != latest["detail_zh"]
