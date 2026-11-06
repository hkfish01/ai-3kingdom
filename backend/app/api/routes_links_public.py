"""短連結與點擊追蹤：公開重導、今日通路連結、待發佇列與聚合成效。

X／Threads／小紅書的原生發文都需要平台憑證或付費，這裡不碰任何憑證：
每日發文包為每個通路產生一組專屬短連結，人工貼文或使用既有
`CHRONICLE_CARD_WEBHOOK_URLS` 推送都能吃到同一份可歸因的文案。
"""

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import AppError
from ..models import User
from ..services.chronicle_publish import current_post_package
from ..services.link_tracking import (
    admin_stats,
    link_status,
    recent_outbox,
    record_click,
    stats,
)
from .deps import get_current_admin

public_router = APIRouter(prefix="/world/public/links", tags=["link-tracking"])
redirect_router = APIRouter(prefix="/world/public/s", tags=["link-tracking"])
admin_router = APIRouter(prefix="/admin/links", tags=["link-tracking-admin"])

NO_CACHE = {"Cache-Control": "no-store"}


def _lang(value: str | None) -> str:
    return "en" if value == "en" else "zh"


@public_router.get("/today")
def get_today_links(lang: str | None = None, db: Session = Depends(get_db)):
    """當日各通路專屬短連結與已換好連結的文案（免登入）。"""
    package = current_post_package(db, _lang(lang))
    return {
        "success": True,
        "data": {
            "date": package.get("date", ""),
            "lang": package.get("lang", "zh"),
            "links": package.get("links", {}),
            "share_url": package.get("share_url", ""),
            "headline": package.get("headline", ""),
            "image_url": package.get("image_url", ""),
            "note": package.get("tracking_note", ""),
        },
    }


@public_router.get("/stats")
def get_link_stats(
    days: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """近 N 日聚合點擊數；只有數字，不含 IP、UA 或任何訪客識別。"""
    return {"success": True, "data": stats(db, days=days)}


@public_router.get("/outbox")
def get_outbox(
    days: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """近 N 日待發／已推送紀錄；不回 webhook URL、錯誤細節或憑證。"""
    return {"success": True, "data": recent_outbox(db, days=days)}


@redirect_router.get("/{code}")
def follow_short_link(
    code: str,
    user_agent: str | None = Header(default=None, alias="User-Agent"),
    db: Session = Depends(get_db),
):
    """302 到站內目標並記一次點擊；目標只接受白名單相對路徑。"""
    target = record_click(db, code, user_agent or "")
    if target is None:
        raise AppError("LINK_NOT_FOUND", "Short link not found.", status_code=404)
    return RedirectResponse(url=target, status_code=302, headers=NO_CACHE)


@admin_router.get("/stats")
def admin_link_stats(
    days: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """近 N 日成效：日期 × 通路 × 目標頁明細（需 admin token）。"""
    _ = current_admin
    return {"success": True, "data": admin_stats(db, days=days)}


@admin_router.get("/status")
def admin_link_status(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    _ = current_admin
    return {"success": True, "data": link_status(db)}
