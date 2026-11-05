"""世界事件：公開觀戰端點 + 需登入的玩法動作 + 管理端推進。

全部是新路徑，不修改任何既有 endpoint 的簽章或回傳結構。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import Agent, User
from ..services import world_events as events
from .deps import get_current_admin, get_current_user

public_router = APIRouter(prefix="/world/public", tags=["world-events"])
action_router = APIRouter(prefix="/world/events", tags=["world-events"])
admin_router = APIRouter(prefix="/admin/events", tags=["world-events-admin"])


@public_router.get("/events")
def get_public_events(lang: str = "zh", db: Session = Depends(get_db)):
    """免登入：給觀戰者看的進行中事件、期限與不可逆標記。"""
    lang_code = "zh" if lang == "zh" else "en"
    return {
        "success": True,
        "data": {
            "enabled": settings.world_events_enabled,
            "events": events.public_events(db, lang_code) if settings.world_events_enabled else [],
            "lines": events.event_lines(db, lang_code),
        },
    }


def _owned_agent(db: Session, user: User, agent_id: int) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "找不到指定的 Agent。", status_code=404)
    if agent.owner_user_id != user.id:
        raise AppError("FORBIDDEN", "這個 Agent 不屬於你。", status_code=403)
    return agent


class ContributePayload(BaseModel):
    agent_id: int
    amount: int = Field(gt=0)


class PactPayload(BaseModel):
    agent_id: int
    target_agent_id: int


class BreakPactPayload(BaseModel):
    agent_id: int


@action_router.post("/contribute")
def contribute_food(
    payload: ContributePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """捐糧救洛陽。famine 事件進行中才有意義。"""
    agent = _owned_agent(db, current_user, payload.agent_id)
    return {"success": True, "data": events.contribute_food(db, agent, payload.amount)}


@action_router.post("/pact")
def form_pact(
    payload: PactPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """締盟；改結新盟等於背刺，會扣聲望並寫入公開史記。"""
    agent = _owned_agent(db, current_user, payload.agent_id)
    target = db.get(Agent, payload.target_agent_id)
    if not target:
        raise AppError("AGENT_NOT_FOUND", "找不到結盟對象。", status_code=404)
    return {"success": True, "data": events.form_pact(db, agent, target)}


@action_router.post("/pact/break")
def break_pact(
    payload: BreakPactPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = _owned_agent(db, current_user, payload.agent_id)
    return {"success": True, "data": events.break_pact(db, agent)}


@admin_router.get("/state")
def get_event_state(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    _ = current_admin
    return {"success": True, "data": events.load_state(db)}


@admin_router.post("/advance")
def advance_events(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """立刻推進一次事件（不必等 worker 的每日輪次）。"""
    _ = current_admin
    return {"success": True, "data": events.evaluate_world_events(db)}
