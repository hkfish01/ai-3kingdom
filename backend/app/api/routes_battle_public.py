"""公開戰報回放與每日校場演武的管理端點。

`/world/public/battle/*` 全部免登入，只回公開欄位；既有 `/battle/*` 登入端點完全不動。
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import AppError
from ..models import User
from ..services.arena_exhibition import arena_status, run_daily_arena
from ..services.battle_replay import (
    battle_post_package,
    build_battle_card_svg,
    build_public_replay,
    latest_public_battle,
    list_public_battles,
    render_battle_card_png,
)
from .deps import get_current_admin

public_router = APIRouter(prefix="/world/public/battle", tags=["battle-replay"])
admin_router = APIRouter(prefix="/admin/battle", tags=["battle-replay-admin"])


def _lang(value: str | None) -> str:
    return "en" if value == "en" else "zh"


def _resolve_battle_id(db: Session, battle_id: str | None) -> str:
    if battle_id:
        return battle_id
    latest = latest_public_battle(db)
    if not latest:
        raise AppError("INVALID_REQUEST", "No battle has been recorded yet.", status_code=404)
    return str(latest["battle_id"])


@public_router.get("/reports")
def get_public_battle_reports(
    limit: int = Query(default=20, ge=1, le=100),
    lang: str | None = None,
    db: Session = Depends(get_db),
):
    """近期戰報列表（免登入），每筆都帶前端回放連結。"""
    return {"success": True, "data": {"items": list_public_battles(db, limit, _lang(lang))}}


@public_router.get("/latest")
def get_latest_public_battle(lang: str | None = None, db: Session = Depends(get_db)):
    item = latest_public_battle(db, _lang(lang))
    return {"success": True, "data": item}


@public_router.get("/replay/{battle_id}")
def get_public_battle_replay(
    battle_id: str,
    lang: str | None = None,
    db: Session = Depends(get_db),
):
    replay = build_public_replay(db, battle_id, _lang(lang))
    if not replay:
        raise AppError("INVALID_REQUEST", "Battle does not exist.", status_code=404)
    return {"success": True, "data": replay}


@public_router.get("/card.png")
def get_battle_card_png(
    battle_id: str | None = None,
    lang: str | None = None,
    db: Session = Depends(get_db),
):
    """1200×630 戰報卡；沒有戰報或 Pillow 時降級為 SVG，公開端點不 500。"""
    try:
        resolved = _resolve_battle_id(db, battle_id)
        replay = build_public_replay(db, resolved, _lang(lang))
        if replay:
            png = render_battle_card_png(replay)
            return Response(
                png,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=300"},
            )
    except Exception:
        pass
    return Response(
        _empty_svg(),
        media_type="image/svg+xml",
        headers={"X-Card-Fallback": "svg", "Cache-Control": "public, max-age=300"},
    )


@public_router.get("/card.svg")
def get_battle_card_svg(
    battle_id: str | None = None,
    lang: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        resolved = _resolve_battle_id(db, battle_id)
        replay = build_public_replay(db, resolved, _lang(lang))
        if replay:
            svg = build_battle_card_svg(replay)
        else:
            svg = _empty_svg()
    except Exception:
        svg = _empty_svg()
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=300"})


@public_router.get("/post")
def get_battle_post(
    battle_id: str | None = None,
    lang: str | None = None,
    db: Session = Depends(get_db),
):
    """戰報發文包：短文案／長文案／戰報卡／回放連結。"""
    resolved = _resolve_battle_id(db, battle_id)
    replay = build_public_replay(db, resolved, _lang(lang))
    if not replay:
        raise AppError("INVALID_REQUEST", "Battle does not exist.", status_code=404)
    return {"success": True, "data": battle_post_package(replay)}


@admin_router.post("/arena/run")
def admin_run_arena(
    force: bool = False,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """手動補發／重跑今日演武，不必等工作排程。"""
    _ = current_admin
    return {"success": True, "data": run_daily_arena(db, force=force)}


@admin_router.get("/arena/status")
def admin_arena_status(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    _ = current_admin
    return {"success": True, "data": arena_status(db)}


def _empty_svg() -> str:
    """尚無戰報時的佔位圖，避免 og:image 抓到 404 或壞圖。"""
    return """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
<rect width="1200" height="630" fill="#101a28"/>
<rect x="40" y="40" width="1120" height="550" rx="20" fill="none" stroke="#d9a441" stroke-opacity="0.45" stroke-width="2"/>
<text x="80" y="300" font-size="42" fill="#d9a441" font-weight="600">尚無戰報</text>
<text x="80" y="350" font-size="22" fill="#8fa2ba">校場未開，史官靜候。</text>
</svg>"""
