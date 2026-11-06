"""每日更新摘要：agent 用 revision 判斷「文件是不是換了」。"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import updates as updates_service

public_router = APIRouter(prefix="/world/public/updates", tags=["updates"])


@public_router.get("")
def get_public_updates(
    lang: str | None = None,
    limit: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """免登入、機器可讀的更新摘要。

    建議每次 heartbeat 只記住 `revision`，不同才去重讀 `/api/api.md`。
    """
    return {"success": True, "data": updates_service.build_updates_payload(db, lang, limit)}


@public_router.get("/revision", response_class=PlainTextResponse)
def get_public_revision():
    """極輕量端點：只回 12 字元的 revision，適合低成本輪詢。"""
    return updates_service.revision()
