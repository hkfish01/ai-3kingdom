"""每日簡報路由：一條給 agent（API key），一條給世界（免登入）。

既有端點完全不動；這裡只做「讀」，所有的寫入（購買、尋訪、領獎）仍走原路徑。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import briefing as briefing_service
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
    return {
        "success": True,
        "data": briefing_service.agent_briefing(
            db,
            auth.agent,
            _lang(lang),
            auth.effective_allowed_actions,
        ),
    }


@public_router.get("/briefing")
def get_world_briefing(lang: str | None = None, db: Session = Depends(get_db)):
    """今日天下態勢：免登入、零個資，給觀戰者與前端 `/briefing` 頁讀。"""
    return {"success": True, "data": briefing_service.world_snapshot(db, _lang(lang))}
