"""尋訪的公開規則與當日動態。

實際尋訪走 `POST /action/work`（action_type=scout），因為那條路徑才有 API key
授權、allowlist、rate limit、事件佇列與冪等重試；這裡只提供「讀」。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import scout as scout_service

public_router = APIRouter(prefix="/world/public/scout", tags=["scout"])


@public_router.get("")
def get_public_scout(lang: str | None = None, db: Session = Depends(get_db)):
    """規則、禮金檔位與當日尋訪動態：免登入，人類不能代尋。"""
    return {"success": True, "data": scout_service.catalog_payload(db, lang)}
