"""史記圖卡與每日發文包：公開免登入讀取、admin 手動補發。

全部是新路徑，不改動既有 `/world/public/chronicle` 的回傳結構。
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..services.chronicle_card import build_card_svg, render_card_png
from ..services.chronicle_publish import (
    current_post_package,
    current_story,
    publish_daily_post,
    publish_status,
)
from .deps import get_current_admin

public_router = APIRouter(prefix="/world/public/chronicle", tags=["chronicle-card"])
admin_router = APIRouter(prefix="/admin/chronicle", tags=["chronicle-card-admin"])


def _lang(value: str | None) -> str:
    return "en" if value == "en" else "zh"


@public_router.get("/card.png")
def get_chronicle_card_png(
    lang: str | None = None,
    date: str | None = Query(default=None, description="僅作快取辨識，內容永遠是最新史記"),
    db: Session = Depends(get_db),
):
    """1200×630 PNG，可直接貼到 X／Threads／小紅書，或當 og:image。"""
    _ = date  # URL 帶日期只是讓社群平台每天抓到新圖，內容取當日最新史記
    story = current_story(db, _lang(lang))
    try:
        png = render_card_png(story)
    except Exception:
        # 沒有 Pillow 或字型時降級為 SVG，公開端點不能因此 500
        return Response(
            build_card_svg(story),
            media_type="image/svg+xml",
            headers={"X-Card-Fallback": "svg", "Cache-Control": "public, max-age=300"},
        )
    return Response(
        png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=300"},
    )


@public_router.get("/card.svg")
def get_chronicle_card_svg(lang: str | None = None, db: Session = Depends(get_db)):
    """與前端下載圖卡同一份版式的 SVG，供網頁預覽與除錯。"""
    return Response(
        build_card_svg(current_story(db, _lang(lang))),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=300"},
    )


@public_router.get("/post")
def get_daily_post(lang: str | None = None, db: Session = Depends(get_db)):
    """每日發文包：短文案／長文案／圖卡網址／世界連結，人工貼文或自動化都吃這份。"""
    return {"success": True, "data": current_post_package(db, _lang(lang))}


@admin_router.post("/card/publish")
def admin_publish_daily_post(
    force: bool = False,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """立刻補發／重算今日發文包，不必等 08:00；force=true 可忽略當日去重。"""
    _ = current_admin
    return {"success": True, "data": publish_daily_post(db, force=force)}


@admin_router.get("/card/status")
def admin_card_status(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    _ = current_admin
    return {"success": True, "data": publish_status(db)}
