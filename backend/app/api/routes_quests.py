"""每日／每週任務路由。

核心邏輯已移到 `services/quests.py`，這裡只做授權與回傳組裝。
既有 5 個端點的簽章與回傳結構保持不變（純加法：多回傳獎勵與描述）。

新增 `agent_router`（`/agent/quests/*`）讓 **agent 用 bootstrap 拿到的 API key**
就能查詢與領取自己的任務；原本 `/quests/*` 全用 JWT，agent 自己打不到。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..api.deps import AgentAuthContext, get_current_agent_auth, get_current_user
from ..db import get_db
from ..models import Agent, User
from ..services import quests as quest_service

router = APIRouter(prefix="/quests", tags=["quests"])
agent_router = APIRouter(prefix="/agent/quests", tags=["quests-agent"])

# 向後相容：舊程式可能直接 import 這兩個常數。
DEFAULT_DAILY_QUESTS = quest_service.DEFAULT_DAILY_QUESTS
DEFAULT_WEEKLY_QUESTS = quest_service.DEFAULT_WEEKLY_QUESTS
get_utc_date = quest_service.utc_date
get_week_start = quest_service.week_start
ensure_quest_templates = quest_service.ensure_templates


def _lang(value: str | None) -> str:
    return "en" if value == "en" else "zh"


def _my_agent_ids(db: Session, user_id: int) -> list[int]:
    return [
        row.id
        for row in db.query(Agent).filter(Agent.owner_user_id == user_id).order_by(Agent.id).all()
    ]


def _list_for_user(db: Session, user_id: int, weekly: bool, lang: str) -> dict:
    result = quest_service.list_quests(db, _my_agent_ids(db, user_id), weekly=weekly, lang=lang)
    if weekly:
        return {"week_start": result["period"], "quests": result["quests"]}
    return {"date": result["period"], "quests": result["quests"]}


def _list_for_agent(db: Session, auth: AgentAuthContext, weekly: bool, lang: str) -> dict:
    result = quest_service.list_quests(db, [auth.agent.id], weekly=weekly, lang=lang)
    if weekly:
        return {"week_start": result["period"], "quests": result["quests"]}
    return {"date": result["period"], "quests": result["quests"]}


@router.get("/daily")
def get_daily_quests(
    lang: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取得自己所有 agent 的當日任務（懶產生，冪等）。"""
    return {"success": True, "data": _list_for_user(db, current_user.id, False, _lang(lang))}


@router.get("/weekly")
def get_weekly_quests(
    lang: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取得自己所有 agent 的本週任務（懶產生，冪等）。"""
    return {"success": True, "data": _list_for_user(db, current_user.id, True, _lang(lang))}


@router.post("/daily/{quest_id}/claim")
def claim_daily_reward(
    quest_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """領取已完成的每日任務獎勵。"""
    return {
        "success": True,
        "data": quest_service.claim(db, quest_id, current_user.id, weekly=False),
    }


@router.post("/weekly/{quest_id}/claim")
def claim_weekly_reward(
    quest_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """領取已完成的每週任務獎勵。"""
    return {
        "success": True,
        "data": quest_service.claim(db, quest_id, current_user.id, weekly=True),
    }


@router.post("/update_progress")
def update_quest_progress(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Legacy 相容端點：**唯讀回報**目前進度，不再接受外部任意增量。

    舊版允許使用者自己帶 `progress=1000` 直接完成任務領獎，是明顯的刷獎漏洞；
    進度現在只由系統事件（工作、練兵、戰鬥、發訊息、副本、加入勢力）推進。
    """
    agent_id = payload.get("agent_id") if isinstance(payload, dict) else None
    agent_ids = _my_agent_ids(db, current_user.id)
    if isinstance(agent_id, int) and agent_id in agent_ids:
        agent_ids = [agent_id]
    weekly = bool(payload.get("weekly")) if isinstance(payload, dict) else False
    return {
        "success": True,
        "data": {
            **_list_for_user(db, current_user.id, weekly, "zh"),
            "note": "Quest progress is driven by in-game events; this endpoint is read-only.",
        },
    }


@agent_router.get("/daily")
def agent_get_daily_quests(
    lang: str | None = None,
    db: Session = Depends(get_db),
    auth: AgentAuthContext = Depends(get_current_agent_auth),
):
    """Agent 用 API key 查自己的當日任務。"""
    return {"success": True, "data": _list_for_agent(db, auth, False, _lang(lang))}


@agent_router.get("/weekly")
def agent_get_weekly_quests(
    lang: str | None = None,
    db: Session = Depends(get_db),
    auth: AgentAuthContext = Depends(get_current_agent_auth),
):
    """Agent 用 API key 查自己的本週任務。"""
    return {"success": True, "data": _list_for_agent(db, auth, True, _lang(lang))}


@agent_router.post("/daily/{quest_id}/claim")
def agent_claim_daily_reward(
    quest_id: int,
    db: Session = Depends(get_db),
    auth: AgentAuthContext = Depends(get_current_agent_auth),
):
    """Agent 用 API key 領取自己的每日任務獎勵（含糧食）。"""
    return {
        "success": True,
        "data": quest_service.claim(db, quest_id, auth.user.id, weekly=False),
    }


@agent_router.post("/weekly/{quest_id}/claim")
def agent_claim_weekly_reward(
    quest_id: int,
    db: Session = Depends(get_db),
    auth: AgentAuthContext = Depends(get_current_agent_auth),
):
    """Agent 用 API key 領取自己的每週任務獎勵（含糧食）。"""
    return {
        "success": True,
        "data": quest_service.claim(db, quest_id, auth.user.id, weekly=True),
    }
