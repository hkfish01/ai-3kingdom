"""唯讀資料稽核（需管理員）。不做任何清洗動作。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..services.world_data_audit import audit_world_data
from .deps import get_current_admin

router = APIRouter(prefix="/admin/data", tags=["data-audit"])


@router.get("/audit")
def get_data_audit(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    _ = current_admin
    return {"success": True, "data": audit_world_data(db)}
