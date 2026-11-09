"""匿名成效量測回歸測試。

守住：簡報讀取有被記錄但不改遊戲數值、採納率只算「被建議且當天稍後成功」的動作、
漏斗的隔日 cohort 未到期要是 null 不是 0、公開端點零個資、agent 文件找得到它。
"""

import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Agent, AgentActionEvent, AgentDailyQuest, BriefingView
from app.services import metrics as metrics_service
from app.services import updates as updates_service

client = TestClient(app)


def _naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
        json={"name": f"metrics-key-{agent_id}", "agent_id": agent_id},
    )
    assert resp.status_code == 200, resp.text
    return {"X-API-Key": resp.json()["data"]["key"]}


def _owner(agent_id: int) -> int:
    with SessionLocal() as db:
        return db.get(Agent, agent_id).owner_user_id


def _view(agent_id: int, keys: list[str], stamp: datetime) -> None:
    with SessionLocal() as db:
        db.add(
            BriefingView(
                agent_id=agent_id,
                day=stamp.date().isoformat(),
                suggested_json=json.dumps(keys),
                created_at=stamp,
            )
        )
        db.commit()


def _event(agent_id: int, action_type: str, stamp: datetime, status: str = "completed") -> None:
    owner_id = _owner(agent_id)
    with SessionLocal() as db:
        db.add(
            AgentActionEvent(
                agent_id=agent_id,
                api_key_id=0,
                owner_user_id=owner_id,
                action_type=action_type,
                status=status,
                created_at=stamp,
            )
        )
        db.commit()


def test_normalize_suggestions_ignores_version_check():
    actions = [
        {"path": "/action/work", "body": {"action_type": "buy"}},
        {"path": "/agent/quests/daily/7/claim"},
        {"path": "/world/public/updates"},
        {"path": "/action/work", "body": {"action_type": "buy"}},
        {"path": "/action/work", "body": {}},
    ]
    assert metrics_service.normalize_suggestions(actions) == ["buy", "claim"]


def test_briefing_read_is_recorded_without_changing_game_state():
    headers = _register("metrics_reader")
    agent_id = _agent(headers, "MetricsReader")
    key = _key(headers, agent_id)

    with SessionLocal() as db:
        before = db.get(Agent, agent_id)
        snapshot = (before.gold, before.food, before.energy, before.reputation)

    resp = client.get("/agent/briefing?lang=zh", headers=key)
    assert resp.status_code == 200, resp.text

    with SessionLocal() as db:
        after = db.get(Agent, agent_id)
        assert (after.gold, after.food, after.energy, after.reputation) == snapshot
        rows = db.query(BriefingView).filter(BriefingView.agent_id == agent_id).all()
        assert len(rows) == 1
        assert isinstance(json.loads(rows[0].suggested_json), list)
        assert rows[0].day == _naive_now().date().isoformat()

    public = client.get("/world/public/metrics?days=3")
    assert public.status_code == 200, public.text
    assert public.json()["data"]["overview"]["briefing_views"] >= 1


def test_adoption_counts_only_suggested_actions_that_succeeded_later():
    headers = _register("metrics_adoption")
    a = _agent(headers, "AdoptBuy")
    b = _agent(headers, "AdoptWrong")
    c = _agent(headers, "AdoptFailed")
    stamp = _naive_now().replace(hour=8, minute=0, second=0, microsecond=0)
    later = stamp + timedelta(hours=2)

    _view(a, ["buy"], stamp)
    _event(a, "buy", later)                       # 建議過、成功 → 採納
    _view(b, ["farm"], stamp)
    _event(b, "trade", later)                     # 動作成功但不是被建議的 → 不算
    _view(c, ["scout"], stamp)
    _event(c, "scout", later, status="failed")    # 失敗事件 → 不算

    with SessionLocal() as db:
        payload = metrics_service.build_metrics_payload(db, 1, "zh", today=stamp.date())

    overview = payload["overview"]
    assert overview["suggested_agents"] == 3
    assert overview["adopted_agents"] == 1
    assert overview["adoption_rate"] == round(1 / 3, 3)
    assert overview["adopted_suggestions"] == 1
    assert payload["machine"]["adoption_rate"] == overview["adoption_rate"]


def test_claimed_quest_suggestion_counts_as_adopted():
    headers = _register("metrics_claim")
    agent_id = _agent(headers, "ClaimAdopt")
    stamp = _naive_now().replace(hour=9, minute=0, second=0, microsecond=0)
    _view(agent_id, ["claim"], stamp)
    with SessionLocal() as db:
        db.add(
            AgentDailyQuest(
                agent_id=agent_id,
                quest_type="earn_gold",
                target=1,
                current_progress=1,
                is_completed=True,
                is_claimed=True,
                quest_date=stamp.date().isoformat(),
            )
        )
        db.commit()
        payload = metrics_service.build_metrics_payload(db, 1, "zh", today=stamp.date())
    assert payload["overview"]["adopted_agents"] == 1


def test_funnel_pending_cohort_is_null_not_zero():
    headers = _register("metrics_funnel")
    a = _agent(headers, "FunnelA")
    b = _agent(headers, "FunnelB")
    today = _naive_now().date()
    yesterday = today - timedelta(days=1)
    y_stamp = datetime.combine(yesterday, datetime.min.time()).replace(hour=10)
    t_stamp = datetime.combine(today, datetime.min.time()).replace(hour=10)

    with SessionLocal() as db:
        for agent_id in (a, b):
            db.get(Agent, agent_id).created_at = y_stamp
        db.commit()
    _event(a, "farm", y_stamp)     # 註冊當日首次動作
    _event(a, "trade", t_stamp)    # 隔日回訪
    _event(b, "farm", y_stamp)     # 註冊當日首次動作，但隔日沒回來

    with SessionLocal() as db:
        payload = metrics_service.build_metrics_payload(db, 2, "zh", today=today)

    rows = {row["date"]: row for row in payload["daily"]}
    assert rows[yesterday.isoformat()]["registrations"] == 2
    assert rows[yesterday.isoformat()]["first_actions"] == 2
    assert rows[yesterday.isoformat()]["next_day_returns"] == 1
    assert rows[today.isoformat()]["next_day_returns"] is None   # D+1 還沒到
    assert payload["funnel"]["registrations"] == 2
    assert payload["funnel"]["first_action_rate"] == 1.0
    assert payload["funnel"]["next_day_return_rate"] == 0.5
    assert payload["funnel"]["pending_cohorts"] >= 1


def test_public_metrics_is_aggregate_only_and_discoverable():
    resp = client.get("/world/public/metrics?days=7&lang=en")
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["type"] == "adoption_metrics"
    assert len(body["daily"]) == 7
    assert body["window"]["days"] == 7
    assert body["privacy"] == "aggregates_only"
    assert "pending" in body["note_en"]
    for secret in ("email", "owner_user_id", "password_hash", "claim_code", "api_key", "agent_id"):
        assert secret not in resp.text
    assert client.get("/world/public/metrics?days=30").status_code == 200
    assert client.get("/world/public/metrics?days=0").status_code == 422

    with SessionLocal() as db:
        assert "metrics" in updates_service.build_updates_payload(db, "zh")["docs"]
    for path in ("/skill.md?lang=zh", "/api.md", "/reference.md"):
        doc = client.get(path)
        assert doc.status_code == 200
        assert "/world/public/metrics" in doc.text
