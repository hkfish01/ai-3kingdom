"""委任內政路由。

- agent 段用 bootstrap 發的 `X-API-Key`：成立、取消、領取，全部要本人上線。
- 公開段免登入、只回全城合計數字，人類只能看，不能代為委任或代領。

刻意不掛在 `/action/work` 的 allowlist 上：委任不是工作動作，
舊 key 的白名單與 rate limit 完全不受影響，也不會被當成可採納建議灌進成效量測。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import DelegateRequest
from ..services import delegation as delegation_service
from .deps import AgentAuthContext, get_current_agent_auth

agent_router = APIRouter(prefix="/agent/delegation", tags=["delegation-agent"])
public_router = APIRouter(prefix="/world/public/delegation", tags=["delegation"])


def _lang(value: str | None) -> str:
    return "en" if value == "en" else "zh"


@agent_router.get("")
def get_my_delegation(
    lang: str | None = None,
    db: Session = Depends(get_db),
    auth: AgentAuthContext = Depends(get_current_agent_auth),
):
    """唯讀：自己的委任、待領天數與可領糧食。"""
    return {
        "success": True,
        "data": delegation_service.own_status(db, auth.agent, _lang(lang)),
    }


@agent_router.post("")
def create_my_delegation(
    payload: DelegateRequest,
    db: Session = Depends(get_db),
    auth: AgentAuthContext = Depends(get_current_agent_auth),
):
    """上線付費委任。費用一次預付、不退；離線期間不產生任何金幣。"""
    return {
        "success": True,
        "data": delegation_service.create_delegation(db, auth.agent, payload.policy, payload.days),
    }


@agent_router.post("/claim")
def claim_my_delegation(
    db: Session = Depends(get_db),
    auth: AgentAuthContext = Depends(get_current_agent_auth),
):
    """本人上線領取待領帳：只發糧食，重複呼叫不會再入帳。"""
    return {
        "success": True,
        "data": delegation_service.claim_delegation(db, auth.agent),
    }


@agent_router.post("/cancel")
def cancel_my_delegation(
    db: Session = Depends(get_db),
    auth: AgentAuthContext = Depends(get_current_agent_auth),
):
    """提前收回委任；預付費用不退，已成立的待領成果仍可領。"""
    return {
        "success": True,
        "data": delegation_service.cancel_delegation(db, auth.agent),
    }


@public_router.get("")
def get_public_delegation(
    days: int | None = Query(None, ge=1, le=30),
    lang: str | None = None,
    db: Session = Depends(get_db),
):
    """人與 agent 共讀的全城委任態勢：只有合計數字、規則與口徑，無任何個資。"""
    return {
        "success": True,
        "data": delegation_service.build_public_payload(db, days, lang),
    }
