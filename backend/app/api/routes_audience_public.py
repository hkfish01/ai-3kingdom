"""觀眾席：免登入助威、押陣、人望榜與分享卡。

`/world/public/audience/*` 全部免登入，只回 agent 名字、城、兵力與票數；
不回 owner、email、token、claim code，也不回任何訪客識別碼。
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..errors import AppError
from ..models import Agent, User
from ..schemas import AudienceCheerRequest, AudienceVoteRequest
from ..services.audience import (
    audience_post_package,
    audience_status,
    build_audience_card_svg,
    card_payload,
    public_agents,
    record_cheer,
    record_vote,
    render_audience_card_png,
    today_snapshot,
)
from .deps import get_current_admin

public_router = APIRouter(prefix="/world/public/audience", tags=["audience"])
admin_router = APIRouter(prefix="/admin/audience", tags=["audience-admin"])

CACHE_HEADER = {"Cache-Control": "public, max-age=60"}


def _lang(value: str | None) -> str:
    return "en" if value == "en" else "zh"


def _enabled() -> None:
    if not settings.audience_enabled:
        raise AppError(
            "AUDIENCE_DISABLED",
            "Audience participation is currently disabled.",
            status_code=403,
        )


@public_router.get("/today")
def get_today(
    lang: str | None = None,
    visitor_id: str | None = Query(default=None, max_length=64),
    db: Session = Depends(get_db),
):
    """下一場演武的助威榜、押陣比、士氣與訪客當日狀態（免登入）。"""
    return {
        "success": True,
        "data": today_snapshot(db, _lang(lang), visitor_id=visitor_id),
    }


@public_router.get("/agents")
def get_agents(limit: int = Query(default=100, ge=1, le=200), db: Session = Depends(get_db)):
    return {"success": True, "data": {"items": public_agents(db, limit), "total": len(public_agents(db, 200))}}


@public_router.post("/cheer")
def post_cheer(payload: AudienceCheerRequest, db: Session = Depends(get_db)):
    """為一位諸侯助威；同一訪客同一 HKT 日只算一次（冪等，不視為錯誤）。"""
    _enabled()
    if db.query(Agent).filter(Agent.id == payload.agent_id).first() is None:
        raise AppError("INVALID_REQUEST", "Agent does not exist.", status_code=404)
    result = record_cheer(db, payload.visitor_id, payload.agent_id)
    return {
        "success": True,
        "data": {
            "recorded": result["ok"],
            "reason": "ALREADY_CHEERED" if result["reason"] == "already_recorded" else result.get("reason"),
            "target_date": result["date"],
        },
    }


@public_router.post("/vote")
def post_vote(payload: AudienceVoteRequest, db: Session = Depends(get_db)):
    """押下一場校場演武的勝方；同一訪客同一 HKT 日只算一次。"""
    _enabled()
    result = record_vote(db, payload.visitor_id, payload.side)
    return {
        "success": True,
        "data": {
            "recorded": result["ok"],
            "reason": "ALREADY_VOTED" if result["reason"] == "already_recorded" else result.get("reason"),
            "target_date": result["date"],
            "side": payload.side,
        },
    }


@public_router.get("/card.png")
def get_card_png(lang: str | None = None, db: Session = Depends(get_db)):
    """1200×630 人望榜分享卡；沒有 Pillow 或字型時降級為 SVG，公開端點不 500。"""
    payload = card_payload(db, _lang(lang))
    try:
        return Response(
            render_audience_card_png(payload),
            media_type="image/png",
            headers=CACHE_HEADER,
        )
    except Exception:
        return Response(
            build_audience_card_svg(payload),
            media_type="image/svg+xml",
            headers={**CACHE_HEADER, "X-Card-Fallback": "svg"},
        )


@public_router.get("/card.svg")
def get_card_svg(lang: str | None = None, db: Session = Depends(get_db)):
    payload = card_payload(db, _lang(lang))
    try:
        svg = build_audience_card_svg(payload)
    except Exception:
        svg = """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630"><rect width="1200" height="630" fill="#101a28"/></svg>"""
    return Response(svg, media_type="image/svg+xml", headers=CACHE_HEADER)


@public_router.get("/post")
def get_post(lang: str | None = None, db: Session = Depends(get_db)):
    """零憑證發文包：短文案、長文案、hashtags 與分享卡網址。"""
    return {"success": True, "data": audience_post_package(db, _lang(lang))}


@admin_router.get("/status")
def admin_audience_status(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    _ = current_admin
    return {"success": True, "data": audience_status(db)}
