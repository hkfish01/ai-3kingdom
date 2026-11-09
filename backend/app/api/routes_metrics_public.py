"""成效量測的公開唯讀端點：只回聚合數字，沒有任何單筆或個資。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import metrics as metrics_service

public_router = APIRouter(prefix="/world/public/metrics", tags=["metrics"])


@public_router.get("")
def get_public_metrics(
    days: int | None = Query(None, ge=1, le=30),
    lang: str | None = None,
    db: Session = Depends(get_db),
):
    """人與 agent 都能讀的匿名成效報表（簡報讀取、採納率、註冊漏斗）。"""
    return {
        "success": True,
        "data": metrics_service.build_metrics_payload(db, days, lang),
    }
