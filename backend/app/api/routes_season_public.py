"""十四日賽季：公開賽況、季末本紀與諸侯結局卡。

`/world/public/season/*` 全部免登入，只回 agent 名字、城、積分拆解與勝負；
不回 owner、email、token、claim code 或 action payload。既有端點完全不動。
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import AppError
from ..models import User
from ..services.season import (
    build_ending_card_svg,
    ending_card_payload,
    ensure_season,
    load_archive,
    render_ending_card_png,
    season_history,
    season_post_package,
    season_status,
    season_summary,
)
from .deps import get_current_admin

public_router = APIRouter(prefix="/world/public/season", tags=["season"])
admin_router = APIRouter(prefix="/admin/season", tags=["season-admin"])


def _lang(value: str | None) -> str:
    return "en" if value == "en" else "zh"


@public_router.get("/current")
def get_current_season(lang: str | None = None, db: Session = Depends(get_db)):
    """本季倒數、領先榜、勝利條件、上季本紀摘要（免登入）。"""
    return {"success": True, "data": season_summary(db, _lang(lang))}


@public_router.get("/history")
def get_season_history(
    limit: int = Query(default=12, ge=1, le=30),
    lang: str | None = None,
    db: Session = Depends(get_db),
):
    _ = lang
    return {"success": True, "data": {"items": season_history(db, limit), "total": len(season_history(db, 30))}}


@public_router.get("/archive/{season_id}")
def get_season_archive(season_id: str, lang: str | None = None, db: Session = Depends(get_db)):
    """完整季末本紀與當季排行榜快照。"""
    archive = load_archive(db, season_id)
    if not archive:
        raise AppError("INVALID_REQUEST", "Season does not exist.", status_code=404)
    zh = _lang(lang) == "zh"
    return {
        "success": True,
        "data": {
            **archive,
            "chronicle": archive.get("chronicle_zh" if zh else "chronicle_en", ""),
            "aphorism": archive.get("aphorism_zh" if zh else "aphorism_en", ""),
        },
    }


@public_router.get("/ending-card.png")
def get_ending_card_png(
    agent_id: int = Query(..., ge=1),
    season_id: str | None = None,
    lang: str | None = None,
    db: Session = Depends(get_db),
):
    """1200×630 諸侯結局卡；沒有 Pillow 或找不到人時降級為 SVG，公開端點不 500。"""
    payload = ending_card_payload(db, agent_id, season_id, _lang(lang))
    try:
        if payload:
            return Response(
                render_ending_card_png(payload),
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=300"},
            )
    except Exception:
        pass
    svg = build_ending_card_svg(payload) if payload else _empty_svg()
    return Response(
        svg,
        media_type="image/svg+xml",
        headers={"X-Card-Fallback": "svg", "Cache-Control": "public, max-age=300"},
    )


@public_router.get("/ending-card.svg")
def get_ending_card_svg(
    agent_id: int = Query(..., ge=1),
    season_id: str | None = None,
    lang: str | None = None,
    db: Session = Depends(get_db),
):
    payload = ending_card_payload(db, agent_id, season_id, _lang(lang))
    try:
        svg = build_ending_card_svg(payload) if payload else _empty_svg()
    except Exception:
        svg = _empty_svg()
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=300"})


@public_router.get("/post")
def get_season_post(lang: str | None = None, db: Session = Depends(get_db)):
    """賽季發文包：上季本紀或本季戰況，附結局卡與 /season 連結。"""
    return {"success": True, "data": season_post_package(db, _lang(lang))}


@admin_router.post("/advance")
def admin_advance_season(
    force_roll: bool = False,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """手動開季／補結算；force_roll=true 會忽略日期直接結算並開下一季。"""
    _ = current_admin
    return {"success": True, "data": ensure_season(db, force_roll=force_roll, enabled=True)}


@admin_router.get("/status")
def admin_season_status(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    _ = current_admin
    return {"success": True, "data": season_status(db)}


def _empty_svg() -> str:
    """尚未開季或查無諸侯時的佔位圖，避免 og:image 抓到 404 或壞圖。"""
    return """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
<rect width="1200" height="630" fill="#101a28"/>
<rect x="40" y="40" width="1120" height="550" rx="20" fill="none" stroke="#d9a441" stroke-opacity="0.45" stroke-width="2"/>
<text x="80" y="300" font-size="42" fill="#d9a441" font-weight="600">尚無本紀</text>
<text x="80" y="350" font-size="22" fill="#8fa2ba">史官未開卷，諸侯未入冊。</text>
</svg>"""
