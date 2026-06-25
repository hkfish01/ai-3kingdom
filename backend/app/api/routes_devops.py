"""
AI DevOps API Routes

提供 AI DevOps 系統的管理接口
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..services.ai_devops import (
    get_devops_report_history,
    get_latest_devops_report,
    run_ai_devops_daily,
)
from .deps import get_current_admin

router = APIRouter(prefix="/admin/devops", tags=["devops"])


class ReportHistoryItem(BaseModel):
    report_id: str
    timestamp: str
    health_status: str
    summary: str


@router.get("/report")
def get_devops_report(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """
    獲取最新的 AI DevOps 報告
    """
    report = get_latest_devops_report(db)

    if not report:
        return {
            "success": True,
            "data": {
                "message": "No report available yet. The daily check runs at 02:00 UTC.",
                "manual_trigger_available": True,
            },
        }

    return {
        "success": True,
        "data": report,
    }


@router.get("/report/history", response_model=list[ReportHistoryItem])
def get_devops_report_history_endpoint(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
    limit: int = 10,
):
    """
    獲取歷史報告列表
    """
    history = get_devops_report_history(db, limit=limit)
    return history


@router.post("/trigger")
async def trigger_devops_check(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """
    手動觸發 AI DevOps 每日檢查

    這會立即執行完整的系統健康檢查、遊戲數據分析和功能規劃。
    結果會保存為最新報告，可通過 GET /admin/devops/report 查看。
    """
    try:
        report = await run_ai_devops_daily(db)
        return {
            "success": True,
            "data": {
                "message": "AI DevOps check completed successfully",
                "report_id": report["report_id"],
                "summary": report["summary"],
            },
        }
    except Exception as e:
        return {
            "success": False,
            "error": {
                "code": "DEVOPS_CHECK_FAILED",
                "message": f"DevOps check failed: {str(e)}",
            },
        }
