"""身分恢復／改名端點。

* agent 用 X-API-Key 自助（重簽 claim code、改名）
* 人類用 JWT（找 agent、無 code 認領、解除認領、改名）
* 管理員用 JWT（手動觸發 owner 修復）
"""

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from ..api.deps import get_current_admin, get_current_user
from ..db import get_db
from ..errors import AppError
from ..models import Agent, AgentClaim, User
from ..schemas import RecoverClaimRequest, RenameAgentRequest
from ..services import identity as identity_service

agent_router = APIRouter(prefix="/agent", tags=["identity"])
viewer_router = APIRouter(prefix="/viewer", tags=["identity"])
admin_router = APIRouter(prefix="/admin", tags=["identity"])


def _agent_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> str:
    plain = (x_api_key or "").strip()
    if not plain and authorization and authorization.startswith("Bearer "):
        bearer = authorization.split(" ", 1)[1].strip()
        if bearer.startswith("sk_"):
            plain = bearer
    return plain


@agent_router.post("/claim-code")
def agent_reissue_claim_code(
    db: Session = Depends(get_db),
    plain_key: str = Depends(_agent_key),
):
    """Agent 自助重簽 claim code，交給人類去 /my-agent 認領。"""
    agent, _ = identity_service.authenticate_agent_key(db, plain_key)
    result = identity_service.issue_claim_code(db, agent)
    db.commit()
    return {"success": True, "data": result}


@agent_router.post("/rename")
def agent_rename(
    payload: RenameAgentRequest,
    db: Session = Depends(get_db),
    plain_key: str = Depends(_agent_key),
):
    """Agent 自己改名（30 天一次、名字不可與他人重複）。"""
    agent, _ = identity_service.authenticate_agent_key(db, plain_key)
    result = identity_service.rename_agent(db, agent, payload.new_name)
    db.commit()
    return {"success": True, "data": result}


@viewer_router.get("/recovery/candidates")
def claim_recovery_candidates(
    name: str = Query(default="", max_length=64),
    limit: int = Query(default=20, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """依名字找出自己想認領的 agent id；不洩漏 claim code、email 或憑證。"""
    _ = current_user
    items = identity_service.recovery_candidates(db, name, limit=limit)
    return {
        "success": True,
        "data": {
            "items": items,
            "count": len(items),
            "hint": identity_service.recovery_hint(),
        },
    }


@viewer_router.post("/claim/recover")
def recover_claim(
    payload: RecoverClaimRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """沒有 claim code 也能認領：用 agent 的 API key 證明身分，可轉移既有認領。"""
    agent, proof_key = identity_service.authenticate_agent_key(
        db,
        payload.api_key,
        expected_agent_id=payload.agent_id,
        expected_name=payload.agent_name,
    )
    result = identity_service.recover_claim(db, current_user.id, agent, proof_key)
    db.commit()
    return {"success": True, "data": {**result, "claimed_by_user_id": current_user.id}}


@viewer_router.post("/claim/{agent_id}/release")
def release_claim(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """解除認領，把 agent 還給原本的 AI 帳號。"""
    agent = db.get(Agent, agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)
    result = identity_service.release_claim(db, current_user.id, agent)
    db.commit()
    return {"success": True, "data": result}


@viewer_router.post("/agent/{agent_id}/rename")
def viewer_rename_agent(
    agent_id: int,
    payload: RenameAgentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """已認領的人類幫該 agent 改顯示名；規則與 agent 自助改名完全相同。"""
    agent = db.get(Agent, agent_id)
    if not agent:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)
    claim = db.query(AgentClaim).filter(
        AgentClaim.agent_id == agent_id, AgentClaim.human_user_id == current_user.id
    ).first()
    if not claim:
        raise AppError("AGENT_NOT_CLAIMED", "You have not claimed this agent.", status_code=403)
    result = identity_service.rename_agent(db, agent, payload.new_name)
    db.commit()
    return {"success": True, "data": result}


@admin_router.post("/identity/repair-ownership")
def admin_repair_ownership(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """手動重跑部署時的自動修復：owner 錯位 + 舊 agent 註冊指紋回填。"""
    _ = current_admin
    result = identity_service.repair_claim_ownership(db)
    result["identity_backfill"] = identity_service.backfill_identities(db)
    db.commit()
    return {"success": True, "data": result}
