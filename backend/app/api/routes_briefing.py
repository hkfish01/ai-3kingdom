"""每日簡報路由：一條給 agent（API key），一條給世界（免登入）。

既有端點完全不動；這裡只做「讀」，所有的寫入（購買、尋訪、領獎）仍走原路徑。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import briefing as briefing_service
from ..services import metrics as metrics_service
from .deps import AgentAuthContext, get_current_agent_auth

agent_router = APIRouter(prefix="/agent", tags=["briefing"])
public_router = APIRouter(prefix="/world/public", tags=["briefing"])


def _lang(value: str | None) -> str:
    return "en" if value == "en" else "zh"


@agent_router.get("/briefing")
def get_agent_briefing(
    lang: str | None = None,
    db: Session = Depends(get_db),
    auth: AgentAuthContext = Depends(get_current_agent_auth),
):
    """Agent 用 bootstrap 的 API key 一次讀到自身狀態、可領獎勵與今日建議動作。"""
    data = briefing_service.agent_briefing(
        db,
        auth.agent,
        _lang(lang),
        auth.effective_allowed_actions,
    )
    # 純觀察：記下「這次讀取時被建議了什麼」，供採納率量測使用。
    # 不改 agent 數值、不代做決定；metrics 內部自行隔離任何失敗。
    metrics_service.record_briefing_view(db, auth.agent.id, data.get("next_actions") or [])
    return {"success": True, "data": data}


@public_router.get("/briefing")
def get_world_briefing(lang: str | None = None, db: Session = Depends(get_db)):
    """今日天下態勢：免登入、零個資，給觀戰者與前端 `/briefing` 頁讀。"""
    return {"success": True, "data": briefing_service.world_snapshot(db, _lang(lang))}
