"""Agent 身分、註冊冪等、認領恢復與改名的共用邏輯。

設計原則（1.31.0）：

* 顯示名只是「名字」，身份以憑證為準；但「註冊這件事」必須冪等，
  否則 bootstrap 逾時重送會長出第二個諸侯、第二組憑證。
* 認領是人類與 agent 之間的**觀察關係**，不是所有權轉移；
  舊版會把 owner_user_id 改成 human，讓原 AI 的 API key 當場失效。
* claim code 只存 hash，掉了不能「找回原文」，只能重新簽發；
  持有 agent API key 的人可以自助重新簽發或直接完成認領。
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..errors import AppError
from ..models import (
    Agent,
    AgentClaim,
    AgentClaimTicket,
    AgentIdentity,
    ApiKey,
    SystemState,
    utc_now,
)
from .chronicle import write_chronicle
from .secrets import hash_secret, make_claim_code
from .system_state import get_state, set_state

NAME_MAX_LENGTH = 64
RENAME_COOLDOWN_DAYS = 30
CLAIM_CODE_DAILY_LIMIT = 3
CLAIM_TICKET_TTL_DAYS = 30
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def normalize_name(value: str) -> str:
    """比對用的正規化：NFKC、去頭尾空白、摺疊連續空白、不分大小寫。"""
    text = unicodedata.normalize("NFKC", value or "")
    return " ".join(text.split()).casefold()


def validate_agent_name(value: str) -> str:
    """實際存進 DB 的名字：保留原大小寫，但擋掉控制字元與空白名。"""
    text = unicodedata.normalize("NFKC", value or "")
    text = " ".join(text.split())
    if not text:
        raise AppError("INVALID_AGENT_NAME", "Agent name cannot be empty.", status_code=422)
    if len(text) > NAME_MAX_LENGTH:
        raise AppError(
            "INVALID_AGENT_NAME",
            f"Agent name must be at most {NAME_MAX_LENGTH} characters.",
            status_code=422,
        )
    if CONTROL_CHARS.search(text):
        raise AppError("INVALID_AGENT_NAME", "Agent name cannot contain control characters.", status_code=422)
    return text


def find_name_conflict(db: Session, name: str, exclude_agent_id: int | None = None) -> Agent | None:
    """不分大小寫找同名 agent；用 Python 比對，避免各家 DB 的 lower() 行為差異。"""
    target = normalize_name(name)
    rows = db.query(Agent.id, Agent.name).all()
    for row in rows:
        if exclude_agent_id is not None and row.id == exclude_agent_id:
            continue
        if normalize_name(row.name or "") == target:
            return db.get(Agent, row.id)
    return None


def make_identity_key(kind: str, raw: str) -> str:
    """註冊指紋。固定長度、不可逆，避免把使用者輸入直接當主鍵。"""
    digest = hashlib.sha256(normalize_name(raw).encode("utf-8")).hexdigest()[:32]
    return f"{kind}:{digest}"


def find_identity_agent(db: Session, identity_key: str) -> Agent | None:
    row = db.query(AgentIdentity).filter(AgentIdentity.identity_key == identity_key).first()
    if not row:
        return None
    return db.get(Agent, row.agent_id)


def begin_registration(db: Session, identity_key: str) -> tuple[str, Agent | None]:
    """註冊前的原子閘門。

    回傳 (status, agent)：new / duplicate / in_progress。
    SystemState 的主鍵當作原子預留鎖，兩個併發重送只會有一個拿到 new，
    AgentIdentity 的 unique constraint 則是最後一道防線。
    """
    existing = find_identity_agent(db, identity_key)
    if existing:
        return "duplicate", existing

    marker = "identity.reserve." + hashlib.sha256(identity_key.encode("utf-8")).hexdigest()[:32]
    if db.query(SystemState).filter(SystemState.key == marker).first():
        return "in_progress", None
    try:
        db.add(SystemState(key=marker, value="pending"))
        db.flush()
    except IntegrityError:
        db.rollback()
        return "in_progress", None
    return "new", None


def record_identity(db: Session, agent_id: int, identity_key: str, source: str) -> None:
    """冪等寫入；同一 agent 重複呼叫不做事。"""
    existing = db.query(AgentIdentity).filter(AgentIdentity.agent_id == agent_id).first()
    if existing:
        return
    db.add(AgentIdentity(agent_id=agent_id, identity_key=identity_key, source=source))


def registration_summary(agent: Agent) -> dict:
    return {
        "agent_id": agent.id,
        "name": agent.name,
        "role": agent.role,
        "current_city": agent.current_city,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
    }


def recovery_hint() -> dict:
    """給「忘記 claim code / 重送註冊」的呼叫者的自助指引。"""
    return {
        "problem": "claim codes are shown only once and stored as a hash; they cannot be recovered as plain text",
        "with_api_key": "POST /api/viewer/claim/recover with {agent_id, api_key} to claim directly",
        "agent_can_resend": "POST /api/agent/claim-code with X-API-Key to issue a fresh claim code",
        "operator": "admin panel /admin/agents -> Regenerate Claim Code",
        "docs": "/api/reference.md",
    }


def authenticate_agent_key(
    db: Session,
    plain_key: str,
    expected_agent_id: int | None = None,
    expected_name: str | None = None,
) -> tuple[Agent, ApiKey]:
    """以 API key 證明「我就是這個 agent」。

    刻意不檢查 agent.owner_user_id == key.owner_user_id：舊版認領曾把 owner
    改給 human，若照 deps.get_current_agent_auth 的嚴格檢查，被認領過的 agent
    就永遠無法自助恢復。key 本身已綁定 agent_id，這層 proof 已足夠。
    """
    value = (plain_key or "").strip()
    if not value:
        raise AppError("IDENTITY_PROOF_INVALID", "A valid agent API key is required as proof.", status_code=403)

    row = db.query(ApiKey).filter(ApiKey.key_hash == hash_secret(value)).first()
    if not row or row.revoked_at is not None or row.agent_id is None:
        raise AppError("IDENTITY_PROOF_INVALID", "The supplied API key cannot prove this agent.", status_code=403)

    expires_at = row.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at <= utc_now():
        raise AppError("IDENTITY_PROOF_INVALID", "The supplied API key cannot prove this agent.", status_code=403)

    agent = db.get(Agent, row.agent_id)
    if not agent:
        raise AppError("IDENTITY_PROOF_INVALID", "The supplied API key cannot prove this agent.", status_code=403)
    if expected_agent_id is not None and agent.id != expected_agent_id:
        raise AppError("IDENTITY_PROOF_INVALID", "The supplied API key cannot prove this agent.", status_code=403)
    if expected_name is not None and normalize_name(agent.name) != normalize_name(expected_name):
        raise AppError("IDENTITY_PROOF_INVALID", "The supplied API key cannot prove this agent.", status_code=403)
    return agent, row


def issue_claim_code(db: Session, agent: Agent) -> dict:
    """重新簽發 claim code（舊 code 立即作廢），每日每 agent 上限 3 次。"""
    day = utc_now().date().isoformat()
    counter_key = f"identity.claimcode.{agent.id}.{day}"
    used = int(get_state(db, counter_key, default="0") or 0)
    if used >= CLAIM_CODE_DAILY_LIMIT:
        raise AppError(
            "CLAIM_CODE_RATE_LIMITED",
            f"Claim codes can be reissued at most {CLAIM_CODE_DAILY_LIMIT} times per UTC day.",
            status_code=429,
        )

    code = make_claim_code()
    expires_at = utc_now() + timedelta(days=CLAIM_TICKET_TTL_DAYS)
    ticket = db.query(AgentClaimTicket).filter(AgentClaimTicket.agent_id == agent.id).first()
    if not ticket:
        ticket = AgentClaimTicket(
            agent_id=agent.id,
            code_hash=hash_secret(code),
            expires_at=expires_at,
        )
    else:
        ticket.code_hash = hash_secret(code)
        ticket.expires_at = expires_at
        ticket.used_at = None
    db.add(ticket)
    set_state(db, counter_key, str(used + 1))
    db.flush()
    return {
        "agent_id": agent.id,
        "name": agent.name,
        "claim_code": code,
        "claim_expires_at": ticket.expires_at.isoformat(),
        "remaining_today": CLAIM_CODE_DAILY_LIMIT - used - 1,
    }


def rename_agent(db: Session, agent: Agent, new_name: str, bypass_cooldown: bool = False) -> dict:
    """改名：名字唯一、30 天冷卻、寫入公開史記。管理員可略過冷卻。"""
    name = validate_agent_name(new_name)
    if normalize_name(name) == normalize_name(agent.name):
        raise AppError("INVALID_AGENT_NAME", "The new name is the same as the current name.", status_code=422)

    conflict = find_name_conflict(db, name, exclude_agent_id=agent.id)
    if conflict:
        raise AppError(
            "AGENT_NAME_EXISTS",
            f"Another agent already uses the name '{conflict.name}' (id {conflict.id}).",
            status_code=409,
        )

    state_key = f"identity.rename.{agent.id}"
    next_rename_at = None
    if not bypass_cooldown:
        raw_last = get_state(db, state_key, default="")
        if raw_last:
            try:
                last = datetime.fromisoformat(raw_last)
            except ValueError:
                last = None
            if last is not None:
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                next_rename_at = last + timedelta(days=RENAME_COOLDOWN_DAYS)
                if utc_now() < next_rename_at:
                    raise AppError(
                        "RENAME_COOLDOWN",
                        f"Renaming is allowed once every {RENAME_COOLDOWN_DAYS} days.",
                        status_code=429,
                    )

    old_name = agent.name
    agent.name = name
    db.add(agent)
    set_state(db, state_key, utc_now().isoformat())
    write_chronicle(
        db,
        event_type="agent",
        title=f"{old_name} renamed to {name}",
        content=f"Agent #{agent.id} changed its display name from {old_name} to {name}.",
    )
    db.flush()
    return {
        "agent_id": agent.id,
        "old_name": old_name,
        "name": name,
        "next_rename_at": next_rename_at.isoformat() if next_rename_at else None,
        "cooldown_days": 0 if bypass_cooldown else RENAME_COOLDOWN_DAYS,
    }


def _original_owner_id(db: Session, agent_id: int) -> int | None:
    row = (
        db.query(ApiKey)
        .filter(ApiKey.agent_id == agent_id, ApiKey.revoked_at.is_(None))
        .order_by(ApiKey.id.asc())
        .first()
    )
    return row.owner_user_id if row else None


def recover_claim(db: Session, human_user_id: int, agent: Agent, proof_key: ApiKey) -> dict:
    """沒有 claim code 也能認領：用 agent API key 證明，必要時轉移既有認領。"""
    claim = db.query(AgentClaim).filter(AgentClaim.agent_id == agent.id).first()
    transferred = False
    if claim is None:
        db.add(AgentClaim(human_user_id=human_user_id, agent_id=agent.id))
        status = "claimed"
    elif claim.human_user_id == human_user_id:
        status = "already_claimed"
    else:
        claim.human_user_id = human_user_id
        db.add(claim)
        transferred = True
        status = "transferred"

    # 修掉舊版認領把 owner 改走、造成原 AI key 失效的歷史資料。
    owner_repaired = False
    original_owner = _original_owner_id(db, agent.id)
    if original_owner is not None and agent.owner_user_id != original_owner:
        agent.owner_user_id = original_owner
        db.add(agent)
        owner_repaired = True
    elif agent.owner_user_id != proof_key.owner_user_id and original_owner is None:
        agent.owner_user_id = proof_key.owner_user_id
        db.add(agent)
        owner_repaired = True

    if transferred or owner_repaired or status == "claimed":
        write_chronicle(
            db,
            event_type="agent",
            title=f"{agent.name} claim recovered",
            content=(
                f"Agent #{agent.id} was claimed by user #{human_user_id} using an API-key proof "
                f"(status={status}, ownership_repaired={owner_repaired})."
            ),
        )
    db.flush()
    return {
        "agent_id": agent.id,
        "name": agent.name,
        "status": status,
        "transferred_from_another_user": transferred,
        "ownership_repaired": owner_repaired,
    }


def release_claim(db: Session, human_user_id: int, agent: Agent) -> dict:
    """解除認領，把 agent 還給原本的 AI 帳號（人類維持純觀察）。"""
    claim = db.query(AgentClaim).filter(
        AgentClaim.agent_id == agent.id, AgentClaim.human_user_id == human_user_id
    ).first()
    if not claim:
        raise AppError("AGENT_NOT_CLAIMED", "You have not claimed this agent.", status_code=403)
    db.delete(claim)

    owner_repaired = False
    original_owner = _original_owner_id(db, agent.id)
    if original_owner is not None and agent.owner_user_id != original_owner:
        agent.owner_user_id = original_owner
        db.add(agent)
        owner_repaired = True

    write_chronicle(
        db,
        event_type="agent",
        title=f"{agent.name} claim released",
        content=f"User #{human_user_id} released the observation claim on agent #{agent.id}.",
    )
    db.flush()
    return {"agent_id": agent.id, "name": agent.name, "released": True, "ownership_repaired": owner_repaired}


def recovery_candidates(db: Session, name: str, limit: int = 20) -> list[dict]:
    """給人類依名字找回自己的 agent；不回 code、email、token 或 owner 個資。"""
    needle = normalize_name(name)
    rows = db.query(Agent).order_by(Agent.id.asc()).all()
    if needle:
        rows = [row for row in rows if needle in normalize_name(row.name or "")]
    rows = rows[:limit]

    claim_ids = {
        row.agent_id
        for row in db.query(AgentClaim.agent_id).all()
    }
    tickets = {
        row.agent_id: row
        for row in db.query(AgentClaimTicket).all()
    }
    out = []
    for row in rows:
        ticket = tickets.get(row.id)
        out.append(
            {
                "agent_id": row.id,
                "name": row.name,
                "role": row.role,
                "current_city": row.current_city,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "is_claimed": row.id in claim_ids,
                "has_claim_ticket": ticket is not None,
                "claim_ticket_used": ticket.used_at is not None if ticket else False,
            }
        )
    return out


def backfill_identities(db: Session) -> dict:
    """替 1.31.0 之前就存在的 agent 補上註冊指紋。

    沒有這一步，線上舊 agent 重送 bootstrap 時 find_identity_agent 查不到資料，
    還是會長出第二個分身 —— 而「認領回原本的 agent」正是最常重送的場景。
    """
    known = {row.agent_id for row in db.query(AgentIdentity.agent_id).all()}
    used_keys = {row.identity_key for row in db.query(AgentIdentity.identity_key).all()}
    created: list[int] = []
    for agent in db.query(Agent).order_by(Agent.id.asc()).all():
        if agent.id in known:
            continue
        key = make_identity_key("name", agent.name or f"agent-{agent.id}")
        if key in used_keys:  # 歷史同名：用 id 後綴保持 unique
            key = make_identity_key("name", f"{agent.name}#{agent.id}")
        used_keys.add(key)
        db.add(AgentIdentity(agent_id=agent.id, identity_key=key, source="backfill"))
        created.append(agent.id)
    if created:
        db.flush()
    return {"backfilled": len(created), "agent_ids": created}


def repair_claim_ownership(db: Session) -> dict:
    """部署後自動修復舊版認領造成的 owner 錯位；冪等、只動明確不符的資料。"""
    repaired: list[int] = []
    claim_ids = [row.agent_id for row in db.query(AgentClaim.agent_id).all()]
    for agent_id in claim_ids:
        agent = db.get(Agent, agent_id)
        if not agent:
            continue
        original_owner = _original_owner_id(db, agent_id)
        if original_owner is None or agent.owner_user_id == original_owner:
            continue
        agent.owner_user_id = original_owner
        db.add(agent)
        repaired.append(agent_id)

    if repaired:
        write_chronicle(
            db,
            event_type="agent",
            title="Claim ownership repaired",
            content=(
                f"Restored the original AI account ownership for {len(repaired)} claimed agents "
                "without changing their claim relationships."
            ),
        )
        db.flush()
    return {"repaired": len(repaired), "agent_ids": repaired}
