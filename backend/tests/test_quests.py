"""每日／每週任務回歸：修復前這套功能完全不可用。

涵蓋：owner_user_id 查詢、沒有 reward 欄位卻被讀、earn_gold 數學上不可能完成、
缺漏的三種事件進度、外部任意刷進度、領獎重複／越權、以及 agent 用 API key 自己領獎。
"""

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Agent, AgentDailyQuest, AgentWeeklyQuest
from app.services import quests as quest_service

client = TestClient(app)


def _auth_header(username: str) -> dict:
    register = client.post(
        "/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "Aa1234!!"},
    )
    assert register.status_code == 200
    login = client.post("/auth/login", json={"username": username, "password": "Aa1234!!"})
    return {"Authorization": f"Bearer {login.json()['data']['token']}"}


def _setup(username: str = "quest_owner") -> tuple[dict, dict, int]:
    headers = _auth_header(username)
    agent_resp = client.post("/agent/register", headers=headers, json={"name": "尋寶諸侯", "role": "文臣"})
    assert agent_resp.status_code == 200
    agent_id = agent_resp.json()["data"]["agent_id"]
    key_resp = client.post(
        "/api-keys",
        headers=headers,
        json={"name": f"key-{username}", "agent_id": agent_id, "allowed_actions": ["farm", "trade", "move"]},
    )
    assert key_resp.status_code == 200
    return headers, {"X-API-Key": key_resp.json()["data"]["key"]}, agent_id


def _daily_row(agent_id: int, quest_type: str) -> AgentDailyQuest:
    with SessionLocal() as db:
        row = (
            db.query(AgentDailyQuest)
            .filter(
                AgentDailyQuest.agent_id == agent_id,
                AgentDailyQuest.quest_type == quest_type,
                AgentDailyQuest.quest_date == quest_service.utc_date(),
            )
            .first()
        )
        assert row is not None
        db.expunge(row)
        return row


def _weekly_row(agent_id: int, quest_type: str) -> AgentWeeklyQuest:
    with SessionLocal() as db:
        row = (
            db.query(AgentWeeklyQuest)
            .filter(
                AgentWeeklyQuest.agent_id == agent_id,
                AgentWeeklyQuest.quest_type == quest_type,
                AgentWeeklyQuest.week_start == quest_service.week_start(),
            )
            .first()
        )
        assert row is not None
        db.expunge(row)
        return row


def test_daily_and_weekly_are_generated_idempotently_with_reward_fields():
    headers, _, agent_id = _setup()
    daily = client.get("/quests/daily", headers=headers)
    assert daily.status_code == 200, daily.text
    rows = daily.json()["data"]["quests"]
    assert len(rows) == 4
    assert {"id", "type", "target", "current_progress", "is_completed", "is_claimed"} <= set(rows[0])
    assert {"description", "reward_gold", "reward_food", "reward_reputation"} <= set(rows[0])
    battle = next(r for r in rows if r["type"] == "complete_battle")
    assert battle["reward_food"] == 20 and battle["reward_gold"] == 40
    assert daily.json()["data"]["date"] == quest_service.utc_date()

    again = client.get("/quests/daily", headers=headers)
    assert again.status_code == 200 and len(again.json()["data"]["quests"]) == 4

    weekly = client.get("/quests/weekly", headers=headers)
    assert weekly.status_code == 200, weekly.text
    assert len(weekly.json()["data"]["quests"]) == 3
    assert client.get("/quests/weekly", headers=headers).json()["data"]["quests"]

    with SessionLocal() as db:
        assert db.query(AgentDailyQuest).filter(AgentDailyQuest.agent_id == agent_id).count() == 4
        assert db.query(AgentWeeklyQuest).filter(AgentWeeklyQuest.agent_id == agent_id).count() == 3


def test_partially_generated_quests_are_repaired_on_next_read():
    headers, _, agent_id = _setup("quest_partial")
    client.get("/quests/daily", headers=headers)
    with SessionLocal() as db:
        victim = (
            db.query(AgentDailyQuest)
            .filter(AgentDailyQuest.agent_id == agent_id, AgentDailyQuest.quest_type == "send_messages")
            .first()
        )
        db.delete(victim)
        db.commit()
    rows = client.get("/quests/daily", headers=headers).json()["data"]["quests"]
    assert len(rows) == 4
    assert any(r["type"] == "send_messages" for r in rows)


def test_work_action_credits_actual_gold_not_one_point():
    headers, key, agent_id = _setup("quest_gold")
    client.get("/quests/daily", headers=headers)
    client.get("/quests/weekly", headers=headers)

    resp = client.post("/action/work", headers=key, json={"action_type": "trade", "payload": {}})
    assert resp.status_code == 200, resp.text
    gold_gained = resp.json()["data"]["gold_gained"]
    assert gold_gained > 1

    assert _daily_row(agent_id, "earn_gold").current_progress == gold_gained
    assert _weekly_row(agent_id, "earn_gold_weekly").current_progress == gold_gained


def test_system_events_complete_quests_and_claim_grants_food():
    headers, _, agent_id = _setup("quest_claim")
    rows = client.get("/quests/daily", headers=headers).json()["data"]["quests"]
    battle = next(r for r in rows if r["type"] == "complete_battle")

    with SessionLocal() as db:
        before = db.get(Agent, agent_id)
        gold, food, reputation = before.gold, before.food, before.reputation

    with SessionLocal() as db:
        quest_service.update_progress(db, agent_id, "complete_battle", 1)
    assert _daily_row(agent_id, "complete_battle").is_completed is True

    claimed = client.post(f"/quests/daily/{battle['id']}/claim", headers=headers)
    assert claimed.status_code == 200, claimed.text
    data = claimed.json()["data"]
    assert (data["reward_gold"], data["reward_food"], data["reward_reputation"]) == (40, 20, 10)

    with SessionLocal() as db:
        after = db.get(Agent, agent_id)
        assert after.gold == gold + 40
        assert after.food == food + 20
        assert after.reputation == reputation + 10
        assert db.get(AgentDailyQuest, battle["id"]).is_claimed is True


def test_claim_guards_reject_incomplete_duplicate_missing_and_foreign_quests():
    headers, _, agent_id = _setup("quest_guard")
    rows = client.get("/quests/daily", headers=headers).json()["data"]["quests"]
    battle = next(r for r in rows if r["type"] == "complete_battle")

    incomplete = client.post(f"/quests/daily/{battle['id']}/claim", headers=headers)
    assert incomplete.status_code == 400
    assert incomplete.json()["error"]["code"] == "QUEST_NOT_COMPLETED"

    with SessionLocal() as db:
        quest_service.update_progress(db, agent_id, "complete_battle", 1)
    assert client.post(f"/quests/daily/{battle['id']}/claim", headers=headers).status_code == 200

    duplicate = client.post(f"/quests/daily/{battle['id']}/claim", headers=headers)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "QUEST_ALREADY_CLAIMED"

    missing = client.post("/quests/daily/999999/claim", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "QUEST_NOT_FOUND"

    other_headers, _, other_agent_id = _setup("quest_other")
    client.get("/quests/daily", headers=other_headers)
    foreign = _daily_row(other_agent_id, "complete_battle")
    denied = client.post(f"/quests/daily/{foreign.id}/claim", headers=headers)
    assert denied.status_code == 403


def test_weekly_claim_grants_food_for_join_federation():
    headers, _, agent_id = _setup("quest_weekly")
    rows = client.get("/quests/weekly", headers=headers).json()["data"]["quests"]
    join = next(r for r in rows if r["type"] == "join_federation")
    assert join["reward_food"] == 50

    with SessionLocal() as db:
        before = db.get(Agent, agent_id).food
        quest_service.update_progress(db, agent_id, "join_federation", 1)
    claimed = client.post(f"/quests/weekly/{join['id']}/claim", headers=headers)
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["data"]["reward_food"] == 50
    with SessionLocal() as db:
        assert db.get(Agent, agent_id).food == before + 50


def test_legacy_update_progress_endpoint_is_read_only():
    headers, _, agent_id = _setup("quest_readonly")
    client.get("/quests/daily", headers=headers)
    resp = client.post(
        "/quests/update_progress",
        headers=headers,
        json={"agent_id": agent_id, "quest_type": "earn_gold", "progress": 1000},
    )
    assert resp.status_code == 200, resp.text
    assert _daily_row(agent_id, "earn_gold").current_progress == 0


def test_agent_api_key_can_list_and_claim_its_own_quests():
    _, key, agent_id = _setup("quest_agent_key")
    daily = client.get("/agent/quests/daily", headers=key)
    assert daily.status_code == 200, daily.text
    rows = daily.json()["data"]["quests"]
    assert len(rows) == 4 and all(r["agent_id"] == agent_id for r in rows)

    weekly = client.get("/agent/quests/weekly?lang=en", headers=key)
    assert weekly.status_code == 200 and len(weekly.json()["data"]["quests"]) == 3

    battle = next(r for r in rows if r["type"] == "complete_battle")
    unauth = client.post(f"/agent/quests/daily/{battle['id']}/claim")
    assert unauth.status_code == 401

    with SessionLocal() as db:
        before = db.get(Agent, agent_id).food
        quest_service.update_progress(db, agent_id, "complete_battle", 1)
    claimed = client.post(f"/agent/quests/daily/{battle['id']}/claim", headers=key)
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["data"]["reward_food"] == 20
    with SessionLocal() as db:
        assert db.get(Agent, agent_id).food == before + 20


def test_agent_api_key_cannot_claim_another_agents_quest():
    _, key_a, _ = _setup("quest_key_a")
    _, _, agent_b = _setup("quest_key_b")
    with SessionLocal() as db:
        quest_service.generate_daily(db, agent_b)
        quest_service.update_progress(db, agent_b, "complete_battle", 1)
    foreign = _daily_row(agent_b, "complete_battle")
    denied = client.post(f"/agent/quests/daily/{foreign.id}/claim", headers=key_a)
    assert denied.status_code == 403


def test_no_reward_columns_were_added_to_quest_progress_tables():
    """不改 DB schema：獎勵只能從模板常數查。"""
    assert not hasattr(AgentDailyQuest, "reward_food")
    assert not hasattr(AgentWeeklyQuest, "reward_gold")
    assert quest_service.reward_for("complete_battle")["reward_food"] == 20
    assert quest_service.reward_for("unknown_type") == {
        "reward_gold": 0,
        "reward_food": 0,
        "reward_reputation": 0,
    }


def test_docs_and_event_hooks_keep_the_quest_loop_wired():
    """純文字防呆：三個缺漏事件的進度來源與 agent 文件不能又被改掉。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    social = (root / "backend" / "app" / "api" / "routes_social.py").read_text(encoding="utf-8")
    combat = (root / "backend" / "app" / "api" / "routes_combat.py").read_text(encoding="utf-8")
    skill_zh = (root / "backend" / "app" / "skill_template_zh.md").read_text(encoding="utf-8")
    skill_en = (root / "backend" / "app" / "skill_template_en.md").read_text(encoding="utf-8")
    api_docs = (root / "backend" / "app" / "api_template.md").read_text(encoding="utf-8")

    assert '"send_messages"' in social and '"join_federation"' in social
    assert '"complete_dungeon"' in combat
    assert "/agent/quests/daily" in skill_zh and "/agent/quests/daily" in skill_en
    assert "/agent/quests/weekly/{quest_id}/claim" in api_docs
    assert "read-only" in api_docs


def test_social_and_dungeon_events_advance_the_previously_unwired_quests():
    headers, _, agent_id = _setup("quest_event_hooks")
    other = client.post("/agent/register", headers=headers, json={"name": "鄰國諸侯", "role": "文臣"})
    assert other.status_code == 200
    other_id = other.json()["data"]["agent_id"]
    client.get("/quests/daily", headers=headers)
    client.get("/quests/weekly", headers=headers)

    message = client.post(
        "/social/message",
        headers=headers,
        json={
            "from_agent_id": agent_id,
            "to_agent_id": other_id,
            "message_type": "greeting",
            "content": "結盟否？",
        },
    )
    assert message.status_code == 200, message.text
    assert _daily_row(agent_id, "send_messages").current_progress == 1

    joined = client.post(
        "/social/join-lord",
        headers=headers,
        json={"agent_id": agent_id, "lord_agent_id": other_id},
    )
    assert joined.status_code == 200, joined.text
    assert _weekly_row(agent_id, "join_federation").is_completed is True

    with SessionLocal() as db:
        agent = db.get(Agent, agent_id)
        agent.infantry = 200
        agent.gold = 1000
        agent.food = 1000
        db.commit()
    dungeon = client.post(
        "/pve/challenge",
        headers=headers,
        json={
            "agent_id": agent_id,
            "dungeon_id": "huangjin",
            "troops": {"infantry": 100, "archer": 0, "cavalry": 0},
        },
    )
    assert dungeon.status_code == 200, dungeon.text
    assert _weekly_row(agent_id, "complete_dungeon").current_progress == 1
