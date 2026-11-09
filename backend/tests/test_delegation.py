"""委任內政回歸測試：世界會動，但掛機印不出錢。

守住七道閘門：必須上線付費、預付金幣只出不進、成果是待領帳、
硬上限（7 日 / 3 日未領 / 同日一次）、不補算、刻意比商城差、
每日重置照樣扣糧；另外守住公開端點零個資、簡報可見、文件找得到。
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Agent, City, ChronicleEntry, Delegation, DelegationLedger
from app.rules import (
    DELEGATE_DAILY_WAGE_GOLD,
    DELEGATE_GOLD_GAIN_PER_DAY,
    DELEGATE_MAX_DAYS,
    DELEGATE_MAX_PENDING_DAYS,
    DELEGATE_POLICIES,
    DELEGATE_SETUP_FEE_GOLD,
    MARKET_ITEMS,
)
from app.services import daily_chronicle
from app.services import delegation as delegation_service
from app.services import updates as updates_service
from app.services.daily_reset import run_daily_reset

client = TestClient(app)


def _register(username: str) -> dict:
    assert client.post(
        "/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "Aa1234!!"},
    ).status_code == 200
    login = client.post("/auth/login", json={"username": username, "password": "Aa1234!!"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['data']['token']}"}


def _agent(headers: dict, name: str) -> int:
    resp = client.post("/agent/register", headers=headers, json={"name": name, "role": "平民"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["agent_id"]


def _key(headers: dict, agent_id: int) -> dict:
    resp = client.post(
        "/api-keys",
        headers=headers,
        json={"name": f"delegation-key-{agent_id}", "agent_id": agent_id},
    )
    assert resp.status_code == 200, resp.text
    return {"X-API-Key": resp.json()["data"]["key"]}


def _setup(name: str, gold: int = 1000):
    headers = _register(name)
    agent_id = _agent(headers, name)
    key = _key(headers, agent_id)
    with SessionLocal() as db:
        db.get(Agent, agent_id).gold = gold
        db.commit()
    return agent_id, key


def _state(agent_id: int) -> tuple[int, int, int, int, int]:
    with SessionLocal() as db:
        row = db.get(Agent, agent_id)
        return (
            row.gold,
            row.food,
            row.energy,
            row.reputation,
            row.infantry + row.archer + row.cavalry,
        )


def _day(offset: int) -> datetime:
    base = datetime.now(timezone.utc).date() + timedelta(days=offset)
    return datetime.combine(base, datetime.min.time(), tzinfo=timezone.utc).replace(hour=2)


def _settle(offset: int, *, force: bool = False) -> dict:
    with SessionLocal() as db:
        return delegation_service.settle_delegations(db, now=_day(offset), force=force)


def _appoint(key: dict, policy: str = "farm", days: int = 3):
    return client.post(
        "/agent/delegation", headers=key, json={"policy": policy, "days": days}
    )


def test_no_delegation_means_nothing_moves_and_nothing_is_written():
    """閘門 1：沒有人被自動委任；結算不寫 agent、不寫待領帳。"""
    agent_id, key = _setup("delegate_idle")
    before = _state(agent_id)
    with SessionLocal() as db:
        before_ledgers = db.query(DelegationLedger).count()
        before_delegations = db.query(Delegation).count()

    result = _settle(1)
    assert result["status"] == "no_active_households"
    assert result["active_households"] == 0
    assert _state(agent_id) == before
    with SessionLocal() as db:
        assert db.query(DelegationLedger).count() == before_ledgers
        assert db.query(Delegation).count() == before_delegations

    own = client.get("/agent/delegation", headers=key).json()["data"]
    assert own["active"] is None and own["claimable_days"] == 0
    pulse = client.get("/world/public/delegation?days=2&lang=zh").json()["data"]["today"]
    assert pulse["active_households"] == 0 and pulse["food_escrowed"] == 0


def test_setup_prepays_gold_and_credits_treasury_without_creating_coins():
    """閘門 2：費用一次預付、只出不進，同額進國庫（純移轉）。"""
    agent_id, key = _setup("delegate_fee")
    before = _state(agent_id)
    with SessionLocal() as db:
        city = db.query(City).first()
        treasury_before = city.treasury_gold if city else 0

    resp = _appoint(key, days=3)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    fee = DELEGATE_SETUP_FEE_GOLD + DELEGATE_DAILY_WAGE_GOLD * 3
    assert data["prepaid_gold"] == fee == 110
    assert data["gold_gain_per_day"] == DELEGATE_GOLD_GAIN_PER_DAY == 0

    after = _state(agent_id)
    assert after[0] == before[0] - fee
    assert after[1:] == before[1:]
    with SessionLocal() as db:
        city = db.query(City).first()
        assert city is not None
        assert city.treasury_gold == treasury_before + fee


def test_invalid_policy_days_and_insufficient_gold_change_nothing():
    agent_id, key = _setup("delegate_invalid", gold=30)
    before = _state(agent_id)

    bad_policy = _appoint(key, policy="print_money", days=3)
    assert bad_policy.status_code == 422
    assert bad_policy.json()["error"]["code"] == "INVALID_DELEGATE_POLICY"

    for days in (0, 8, -1, True, "3"):
        bad_days = _appoint(key, days=days)
        assert bad_days.status_code == 422, (days, bad_days.text)

    too_poor = _appoint(key, days=3)
    assert too_poor.status_code == 422
    assert too_poor.json()["error"]["code"] == "DELEGATION_INSUFFICIENT_GOLD"
    assert _state(agent_id) == before
    with SessionLocal() as db:
        assert db.query(Delegation).count() == 0


def test_one_active_per_agent_and_one_setup_per_utc_day():
    """閘門 5：同時只能一筆 active；同日取消後也不能再成立一次，且不退費。"""
    agent_id, key = _setup("delegate_cooldown")
    assert _appoint(key, days=2).status_code == 200
    gold_after_setup, *_ = _state(agent_id)

    again = _appoint(key, days=2)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "DELEGATION_ALREADY_ACTIVE"

    cancel = client.post("/agent/delegation/cancel", headers=key)
    assert cancel.status_code == 200
    assert cancel.json()["data"]["refund_gold"] == 0
    assert _state(agent_id)[0] == gold_after_setup

    cooldown = _appoint(key, days=2)
    assert cooldown.status_code == 429
    assert cooldown.json()["error"]["code"] == "DELEGATION_SETUP_COOLDOWN"
    assert client.post("/agent/delegation/cancel", headers=key).status_code == 404


def test_offline_settlement_is_escrow_only_and_never_prints_gold():
    """閘門 3：離線結算完全不碰 agent 的任何數值欄位，只寫待領帳。"""
    agent_id, key = _setup("delegate_escrow")
    _appoint(key, days=3)
    before = _state(agent_id)

    for offset in (1, 2, 3):
        result = _settle(offset)
        assert result["status"] == "settled"
        assert result["settled_households"] == 1
        assert _state(agent_id) == before

    with SessionLocal() as db:
        rows = db.query(DelegationLedger).filter(DelegationLedger.agent_id == agent_id).all()
        assert len(rows) == 3
        assert all(row.status == "pending" for row in rows)
        assert all(row.gold_gain == 0 for row in rows)
        assert sum(row.food_gain for row in rows) == 72
        assert db.query(ChronicleEntry).filter(ChronicleEntry.event_type == "economy").count() >= 3

    own = client.get("/agent/delegation", headers=key).json()["data"]
    assert own["claimable_days"] == 3
    assert own["claimable_food"] == 72
    assert own["claimable_gold"] == 0
    # 第 3 天正好是 end_day，委任自動到期（不是無限期續約）。
    assert own["active"] is None
    with SessionLocal() as db:
        row = db.query(Delegation).filter(Delegation.agent_id == agent_id).first()
        assert row.settled_days == 3
        assert row.status == "expired"


def test_claim_needs_an_online_request_and_is_idempotent():
    """閘門 4：本人上線才領得到；只發糧食、金幣收入 0、重複領不再入帳。"""
    agent_id, key = _setup("delegate_claim")
    before = _state(agent_id)
    _appoint(key, days=3)
    for offset in (1, 2, 3):
        _settle(offset)
    assert _state(agent_id) == (before[0] - 110, *before[1:])

    first = client.post("/agent/delegation/claim", headers=key)
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["status"] == "claimed"
    assert data["claimed_days"] == 3
    assert data["food_gained"] == 72
    assert data["gold_gained"] == 0

    after_first = _state(agent_id)
    assert after_first == (before[0] - 110, before[1] + 72, *before[2:])

    second = client.post("/agent/delegation/claim", headers=key).json()["data"]
    assert second["status"] == "nothing_to_claim"
    assert second["food_gained"] == 0
    assert _state(agent_id) == after_first

    with SessionLocal() as db:
        rows = db.query(DelegationLedger).filter(DelegationLedger.agent_id == agent_id).all()
        assert all(row.status == "claimed" for row in rows)


def test_three_unclaimed_days_is_a_hard_cap():
    """閘門 5：離開 7 天也最多累積 3 天待領；之後世界仍推進但不再加帳。"""
    agent_id, key = _setup("delegate_cap")
    assert _appoint(key, days=DELEGATE_MAX_DAYS).status_code == 200

    results = [_settle(offset) for offset in range(1, DELEGATE_MAX_DAYS + 1)]
    assert sum(row["settled_households"] for row in results) == DELEGATE_MAX_PENDING_DAYS
    assert sum(row["skipped_by_cap"] for row in results) == DELEGATE_MAX_DAYS - DELEGATE_MAX_PENDING_DAYS
    assert results[-1]["expired_households"] == 1

    with SessionLocal() as db:
        rows = db.query(DelegationLedger).filter(DelegationLedger.agent_id == agent_id).all()
        assert len(rows) == DELEGATE_MAX_PENDING_DAYS
        assert sum(row.food_gain for row in rows) == 72
        assert db.get(Delegation, rows[0].delegation_id).status == "expired"

    claimed = client.post("/agent/delegation/claim", headers=key).json()["data"]
    assert claimed["claimed_days"] == DELEGATE_MAX_PENDING_DAYS
    assert claimed["food_gained"] == 72
    assert claimed["gold_gained"] == 0


def test_missed_days_are_never_backfilled():
    """閘門 6：worker 沒跑到的日子不補算，只結算「今天」。"""
    agent_id, key = _setup("delegate_nobackfill")
    _appoint(key, days=DELEGATE_MAX_DAYS)

    result = _settle(5)
    assert result["settled_households"] == 1
    with SessionLocal() as db:
        rows = db.query(DelegationLedger).filter(DelegationLedger.agent_id == agent_id).all()
        assert len(rows) == 1
        assert rows[0].day == _day(5).date().isoformat()

    # 同一天重跑（worker 重啟）也不能重複記帳。
    again = _settle(5)
    assert again["status"] == "already_settled"
    forced = _settle(5, force=True)
    assert forced["settled_households"] == 0
    assert forced["skipped_by_cap"] == 1
    with SessionLocal() as db:
        assert db.query(DelegationLedger).filter(DelegationLedger.agent_id == agent_id).count() == 1


def test_yield_is_deliberately_worse_than_the_market():
    """閘門 7：每一種方針的糧／金效率都低於商城最便宜的糧袋。"""
    bag = MARKET_ITEMS["grain_bag"]
    market_ratio = bag["food"] / bag["gold"]
    for policy in DELEGATE_POLICIES.values():
        ratio = policy["food_per_day"] / DELEGATE_DAILY_WAGE_GOLD
        assert ratio < market_ratio, (policy, ratio, market_ratio)
    rules = client.get("/world/public/delegation?lang=zh").json()["data"]["rules"]
    assert rules["gold_gain_per_day"] == 0
    assert rules["yield_below_market"] is True
    assert rules["claim_required"] is True
    assert rules["no_backfill"] is True


def test_daily_upkeep_still_applies_during_delegation():
    """閘門 7：委任不是免死金牌，每日重置照樣扣口糧。"""
    agent_id, key = _setup("delegate_upkeep")
    _appoint(key, days=3)
    _settle(1)
    before = _state(agent_id)[1]
    with SessionLocal() as db:
        run_daily_reset(db)
    assert _state(agent_id)[1] == max(0, before - 10)  # DAILY_AGENT_FOOD_CONSUMPTION = 10
    # 委任仍可領，沒有被重置洗掉。
    assert client.post("/agent/delegation/claim", headers=key).json()["data"]["claimed_days"] == 1


def test_full_lifecycle_gold_is_strictly_non_increasing():
    """總結算：成立 → 5 天離線 → 領取，金幣只減不增、聲望兵力體力全不動。"""
    agent_id, key = _setup("delegate_ledger")
    before = _state(agent_id)
    _appoint(key, days=3)
    for offset in range(1, 6):
        _settle(offset)
    after_offline = _state(agent_id)
    assert after_offline == (before[0] - 110, *before[1:])
    client.post("/agent/delegation/claim", headers=key)
    final = _state(agent_id)
    assert final[0] == before[0] - 110
    assert final[1] == before[1] + 72
    assert final[2:] == before[2:]


def test_world_briefing_and_daily_story_show_the_offline_world_moving():
    """世界會動：史記多一行、公開簡報與公開 pulse 都看得到全城合計。"""
    agent_id, key = _setup("delegate_world")
    _appoint(key, days=3)
    # 把這筆委任改成「昨天成立」，讓今天的 worker 結算能落在當日 pulse 上。
    today = datetime.now(timezone.utc).date()
    with SessionLocal() as db:
        row = db.query(Delegation).filter(Delegation.agent_id == agent_id).first()
        row.start_day = (today - timedelta(days=1)).isoformat()
        row.end_day = (today + timedelta(days=2)).isoformat()
        db.commit()
        result = delegation_service.settle_delegations(db, now=datetime.now(timezone.utc))
    assert result["status"] == "settled"

    world = client.get("/world/public/briefing?lang=zh").json()["data"]
    assert world["delegation"]["enabled"] is True
    assert world["delegation"]["active_households"] >= 1
    assert world["delegation"]["food_escrowed_today"] >= 1

    with SessionLocal() as db:
        facts = daily_chronicle.collect_daily_facts(db)
        assert facts["delegate_lines_zh"] and facts["delegate_lines_en"]
        story = daily_chronicle.build_story(facts, lang="zh")
        assert any("管事" in line for line in story["lines"])
        assert delegation_service.story_lines(db, "en")

    pulse = client.get("/world/public/delegation?lang=zh&days=3").json()["data"]
    assert pulse["today"]["settled_households"] >= 1
    assert any(row["settled_households"] >= 1 for row in pulse["daily"])


def test_agent_briefing_carries_own_delegation_without_polluting_next_actions():
    agent_id, key = _setup("delegate_briefing")
    _appoint(key, days=2)
    _settle(1)

    body = client.get("/agent/briefing?lang=zh", headers=key).json()["data"]
    assert body["delegation"]["claimable_days"] == 1
    assert body["delegation"]["claimable_food"] > 0
    assert body["delegation"]["claimable_gold"] == 0
    assert body["delegation"]["claim_endpoint"] == "/agent/delegation/claim"
    # 委任領取不放進 next_actions：成效量測的「建議採納率」口徑不能被污染。
    assert not any("/agent/delegation" in str(row.get("path", "")) for row in body["next_actions"])
    assert body["update_revision"] == body["world"]["update_revision"]


def test_public_payload_is_aggregate_only_in_both_languages():
    resp = client.get("/world/public/delegation?days=7&lang=en")
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["type"] == "delegated_stewardship"
    assert len(body["daily"]) == 7
    assert body["privacy"] == "aggregates_only"
    assert body["machine"]["gold_gain_per_day"] == 0
    assert body["machine"]["claim_required"] is True
    assert body["machine"]["no_backfill"] is True
    assert "claim" in body["definitions"]["escrow"].lower()
    assert "pending" in body["note_en"]

    secrets = ("email", "owner_user_id", "password_hash", "claim_code", "api_key", "agent_id")
    for path in ("/world/public/delegation?days=3&lang=zh", "/world/public/delegation?days=3&lang=en"):
        text = client.get(path).text
        assert client.get(path).status_code == 200
        for secret in secrets:
            assert secret not in text, (path, secret)
        data = client.get(path).json()["data"]
        assert all(isinstance(value, str) for value in data["definitions"].values())

    assert client.get("/world/public/delegation?days=30").status_code == 200
    assert client.get("/world/public/delegation?days=0").status_code == 422
    assert client.get("/world/public/delegation?days=31").status_code == 422


def test_agent_endpoints_require_an_api_key_and_docs_are_discoverable():
    assert client.get("/agent/delegation").status_code == 401
    assert client.post("/agent/delegation", json={"policy": "farm", "days": 2}).status_code == 401
    assert client.post("/agent/delegation/claim").status_code == 401

    with SessionLocal() as db:
        assert "delegation" in updates_service.build_updates_payload(db, "zh")["docs"]
    for path in ("/skill.md?lang=zh", "/skill.md?lang=en", "/skill.md", "/api.md", "/reference.md"):
        doc = client.get(path)
        assert doc.status_code == 200, path
        assert "/agent/delegation" in doc.text, path
        assert "/world/public/delegation" in doc.text, path


def test_latest_changelog_entry_announces_the_new_contract():
    """人 + agent 共讀公告：這一版必須把新端點與動作寫進 changelog。"""
    with SessionLocal() as db:
        payload = updates_service.build_updates_payload(db, "zh")
    latest = payload["items"][0]
    assert latest["version"] == settings.app_version
    assert any("/agent/delegation" in endpoint for endpoint in latest["endpoints"])
    assert any("/agent/delegation" in action for action in latest["actions"])
    assert latest["summary"] and latest["agent_note"]
    announcement = payload["announcement"]
    assert "【給人看 / For humans】" in announcement["content"]
    assert "```agent-json" in announcement["content"]
    # human_text 保留人讀段落與 For agents 的 key-value，但裁掉純機器的 JSON fence。
    assert "```agent-json" not in announcement["human_text"]
    assert "【給 Agent 看 / For agents】" in announcement["human_text"]
    agent_payload = announcement["agent"]
    assert agent_payload["update_revision"] == payload["revision"]
    assert any("/agent/delegation" in endpoint for endpoint in agent_payload["endpoints"])
