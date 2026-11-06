"""商城的公開目錄與營運者的開倉賑濟。

購買本身走 `POST /action/work`（action_type=buy），因為那條路徑才有 API key
授權、allowlist、rate limit、事件佇列與冪等重試；這裡只提供「讀」與「止血」。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..services import market as market_service
from .deps import get_current_admin

public_router = APIRouter(prefix="/world/public/market", tags=["market"])
admin_router = APIRouter(prefix="/admin/market", tags=["market-admin"])


@public_router.get("")
def get_public_market(lang: str | None = None):
    """商品目錄：免登入，人類與 agent 都能讀；人類不能代買。"""
    return {"success": True, "data": market_service.catalog_payload(lang)}


@admin_router.post("/relief")
def run_relief(
    floor: int = Query(default=60, ge=1, le=10000),
    dry_run: bool = Query(default=True),
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """把低於底線的 agent 補到底線。

    預設 `dry_run=true` 只試算；確認後帶 `dry_run=false` 才真的寫入。
    同一天重複執行會回 `already_applied`，必要時用 `force=true` 補發。
    """
    _ = current_admin
    result = market_service.run_market_relief(
        db,
        floor,
        dry_run=dry_run,
        force=force,
    )
    return {"success": True, "data": result}
