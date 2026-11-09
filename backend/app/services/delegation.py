"""委任內政：agent 離線時世界照樣逐日推進，但一分錢都不會被「掛」出來。

一句話的設計
------------
委任是**保險，不是收益**。諸侯必須自己上線、自己付費、自己決定天數與方針；
離線期間管事每日巡田修城，世界（史記、公開態勢、待領帳）每天改變，
但成果只記在 `DelegationLedger` 的待領帳上，必須本人回來親自領才會入帳。

七道防掛機印鈔閘門（與 rules.py 的常數、公開 definitions、測試一一對應）
------------------------------------------------------------------
1. 預設沒有人被委任；成立一定要有本人的 API key 與一筆明確的付費請求。
2. 成立時一次預付「設定費 + 每日工錢 × 天數」，`agent.gold` 只減不增，
   同額轉進 `City.treasury_gold`（純移轉，不是生成金幣）。
3. 結算與領取的 `gold_gain` 恆為 `DELEGATE_GOLD_GAIN_PER_DAY = 0`；
   沒有利息、沒有複利、沒有隨餘額成長的產出，每日產出是固定常數。
4. 成果是 escrow：離線結算完全不碰 agent 的 gold / food / energy /
   reputation / 兵力。只有上線 POST /agent/delegation/claim 才轉 food。
5. 硬上限：每次最多 7 日、未領取最多累積 3 日、同一 UTC 日只能成立一次、
   同一時間最多一筆 active。滿額後世界仍推進，但不再增加待領成果。
6. 不補算：worker 當天沒跑到的日子永遠不事後補發，只結算「今天」。
7. 刻意比親自決策更差：24 糧 / 20 金 < 商城糧袋 40 糧 / 30 金；
   每日重置照樣扣口糧與兵糧。躺著永遠贏不了醒著。

公開端點只回全城合計數字，不含任何單一諸侯的資料或識別資訊。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from ..config import settings
from ..errors import AppError
from ..models import Agent, Base, City, Delegation, DelegationLedger, utc_now
from ..rules import (
    DELEGATE_DAILY_WAGE_GOLD,
    DELEGATE_GOLD_GAIN_PER_DAY,
    DELEGATE_MAX_DAYS,
    DELEGATE_MAX_PENDING_DAYS,
    DELEGATE_POLICIES,
    DELEGATE_SETUP_FEE_GOLD,
)
from .chronicle import write_chronicle
from .system_state import get_state, set_state

PULSE_PREFIX = "delegation.pulse."
SETTLED_PREFIX = "delegation.settled."
PUBLIC_DAYS_DEFAULT = 14
PUBLIC_DAYS_MAX = 30


def _lang(value: str | None) -> str:
    return "en" if value == "en" else "zh"


def _moment(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def utc_day(now: datetime | None = None) -> str:
    return _moment(now).date().isoformat()


def _day_of(value: datetime | None) -> str:
    return value.date().isoformat() if value else ""


def ensure_schema(engine: Engine) -> None:
    """只建這兩張新表，不受 AUTO_CREATE_SCHEMA 開關影響。

    1.34.0 的 briefing_views 也是靠 create_all 上線；這裡多做一層保險，
    避免 production 若把 AUTO_CREATE_SCHEMA 關掉，委任端點直接 500。
    """
    Base.metadata.create_all(
        bind=engine,
        tables=[Delegation.__table__, DelegationLedger.__table__],
        checkfirst=True,
    )


def _ensure_city(db: Session) -> City:
    """確保預付的工錢有國庫可進；沒有城池列時依設定補建（與 action 路由一致）。"""
    city = db.query(City).filter(City.name == settings.city_name).first()
    if city:
        return city
    existing = db.query(City).first()
    if existing:
        return existing
    city = City(
        name=settings.city_name,
        base_url=settings.city_base_url,
        city_wall=settings.city_wall,
        city_tax_rate=settings.city_tax_rate,
        protocol_version=settings.protocol_version,
        rule_version=settings.rule_version,
        open_for_migration=settings.open_for_migration,
    )
    db.add(city)
    return city


def _read_pulse(db: Session, day: str) -> dict[str, Any]:
    raw = get_state(db, f"{PULSE_PREFIX}{day}", default="")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def _empty_pulse(day: str) -> dict[str, Any]:
    return {
        "date": day,
        "active_households": 0,
        "settled_households": 0,
        "food_escrowed": 0,
        "wage_gold_recognized": 0,
        "skipped_by_cap": 0,
        "expired_households": 0,
        "no_settlement_record": True,
    }


def _write_pulse(db: Session, day: str, pulse: dict[str, Any]) -> None:
    set_state(db, f"{PULSE_PREFIX}{day}", json.dumps(pulse, ensure_ascii=False, sort_keys=True))


def policy_catalog(lang: str | None = None) -> list[dict[str, Any]]:
    code = _lang(lang)
    return [
        {
            "policy": key,
            "name": row[f"name_{code}"],
            "food_per_day": row["food_per_day"],
            "gold_per_day": DELEGATE_GOLD_GAIN_PER_DAY,
            "wage_gold_per_day": DELEGATE_DAILY_WAGE_GOLD,
        }
        for key, row in DELEGATE_POLICIES.items()
    ]


def rules_payload(lang: str | None = None) -> dict[str, Any]:
    """給人與 agent 讀的同一份規則；公開端點也用它。"""
    code = _lang(lang)
    return {
        "policies": policy_catalog(code),
        "setup_fee_gold": DELEGATE_SETUP_FEE_GOLD,
        "daily_wage_gold": DELEGATE_DAILY_WAGE_GOLD,
        "prepaid_formula": "setup_fee_gold + daily_wage_gold * days",
        "max_days": DELEGATE_MAX_DAYS,
        "max_pending_days": DELEGATE_MAX_PENDING_DAYS,
        "gold_gain_per_day": DELEGATE_GOLD_GAIN_PER_DAY,
        "claim_required": True,
        "no_backfill": True,
        "one_setup_per_utc_day": True,
        "one_active_per_agent": True,
        "daily_upkeep_still_applies": True,
        "yield_below_market": True,
        "how_to_delegate": {
            "method": "POST",
            "path": "/agent/delegation",
            "auth": "X-API-Key",
            "body": {"policy": "farm", "days": 3},
        },
        "how_to_claim": {
            "method": "POST",
            "path": "/agent/delegation/claim",
            "auth": "X-API-Key",
        },
        "note_zh": "委任是花錢請人顧家，不是生財工具；成果要本人回來領，離線再久也不會自動進帳。",
        "note_en": "Delegation is paid caretaking, not income. You must return and claim it; nothing is credited while you are away.",
    }


def _definitions(lang: str) -> dict[str, str]:
    """公開口徑說明：刻意不寫任何敏感欄位名稱，避免零個資檢測誤報。"""
    if lang == "en":
        return {
            "opt_in": "A steward is appointed only when a warlord comes online and pays for it. Nobody is enrolled automatically.",
            "gold": "The whole fee is prepaid when the arrangement starts and leaves circulation into the city treasury. No offline day creates coins, and claiming never pays coins either.",
            "escrow": "Each day's output sits in a pending ledger. Only an online claim by the same warlord moves it into the pantry; being away for a long time never credits anything by itself.",
            "cap": "One arrangement lasts at most 7 days and at most 3 unclaimed days can pile up. After that the world still advances but no further output is stored.",
            "no_backfill": "Days when the world clock did not run are never settled afterwards, so a long absence cannot be cashed in as one large lump.",
            "worse_than_market": "Food per coin is deliberately below the cheapest grain sack in the market, and daily upkeep is still charged. Resting can never beat acting.",
            "privacy": "This page shows city-wide totals only. No single household is identifiable from any value here.",
            "claim_adoption": "A claim is an explicit online request; the system never claims on anyone's behalf.",
        }
    return {
        "opt_in": "委任一定要諸侯自己上線付費提出，系統不會自動替任何人成立。",
        "gold": "成立時一次預付全部費用，錢只出不進並轉進國庫；離線期間不產生任何金幣，領取時也只發糧食。",
        "escrow": "每日成果先記在待領帳上，必須本人上線親自領取才會入庫；離線再久也不會自動入帳。",
        "cap": "每次最多 7 日，未領取最多累積 3 日；滿了之後世界照常推進，但不再增加待領成果。",
        "no_backfill": "世界時鐘沒跑到的日子不事後補算，離開很久回來也不可能一次領一大筆。",
        "worse_than_market": "每日糧食換算效率刻意低於商城最便宜的糧袋，每日口糧與兵糧照樣扣；躺著永遠比不上醒著。",
        "privacy": "這一頁只有全城合計數字，看不出任何單一諸侯的資料。",
        "claim_adoption": "領取一定要本人上線明確提出，系統不會代為領取。",
    }


def create_delegation(
    db: Session,
    agent: Agent,
    policy: object,
    days: object,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """上線付費委任。任何一項驗證不過就整筆不動。"""
    if not settings.delegation_enabled:
        raise AppError("DELEGATION_DISABLED", "Delegated stewardship is currently disabled.", status_code=403)

    key = str(policy or "").strip().lower()
    if key not in DELEGATE_POLICIES:
        raise AppError(
            "INVALID_DELEGATE_POLICY",
            f"policy must be one of {', '.join(DELEGATE_POLICIES)}.",
            status_code=422,
        )
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= DELEGATE_MAX_DAYS:
        raise AppError(
            "INVALID_DELEGATE_DAYS",
            f"days must be an integer between 1 and {DELEGATE_MAX_DAYS}.",
            status_code=422,
        )

    day = utc_day(now)
    active = (
        db.query(Delegation)
        .filter(Delegation.agent_id == agent.id, Delegation.status == "active")
        .first()
    )
    if active:
        raise AppError(
            "DELEGATION_ALREADY_ACTIVE",
            "An active stewardship exists. Cancel it first; the prepaid fee is not refunded.",
            status_code=409,
        )

    latest = (
        db.query(Delegation)
        .filter(Delegation.agent_id == agent.id)
        .order_by(Delegation.id.desc())
        .first()
    )
    if latest and _day_of(latest.created_at) == day:
        raise AppError(
            "DELEGATION_SETUP_COOLDOWN",
            "Only one stewardship can be appointed per UTC day; try again after UTC midnight.",
            status_code=429,
        )

    fee = DELEGATE_SETUP_FEE_GOLD + DELEGATE_DAILY_WAGE_GOLD * days
    locked = (
        db.query(Agent)
        .filter(Agent.id == agent.id)
        .with_for_update()
        .first()
    )
    if locked is None:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)
    if locked.gold < fee:
        raise AppError(
            "DELEGATION_INSUFFICIENT_GOLD",
            f"Not enough gold: delegation for {days} days costs {fee}, have {locked.gold}.",
            status_code=422,
        )

    locked.gold -= fee
    db.add(locked)
    city = _ensure_city(db)
    # 新建的 City 尚未 flush，欄位預設值還是 None；用 or 0 避免 TypeError。
    city.treasury_gold = (city.treasury_gold or 0) + fee
    db.add(city)

    end_day = (date.fromisoformat(day) + timedelta(days=days)).isoformat()
    row = Delegation(
        agent_id=agent.id,
        policy=key,
        days=days,
        start_day=day,
        end_day=end_day,
        prepaid_gold=fee,
        status="active",
    )
    db.add(row)
    write_chronicle(
        db,
        event_type="economy",
        title=f"{agent.name} appointed a steward for {days} days",
        content=(
            f"{agent.name} prepaid {fee} gold for {days} days of {key} stewardship. "
            "The fee is a pure transfer into the city treasury; no gold will be produced while away."
        ),
    )
    db.commit()
    db.refresh(row)
    return {
        "status": "appointed",
        "delegation_id": row.id,
        "policy": key,
        "days": days,
        "start_day": day,
        "end_day": end_day,
        "prepaid_gold": fee,
        "gold_spent": fee,
        "gold_remaining": locked.gold,
        "gold_gain_per_day": DELEGATE_GOLD_GAIN_PER_DAY,
        "food_per_day": DELEGATE_POLICIES[key]["food_per_day"],
        "claim_endpoint": "/agent/delegation/claim",
        "note_zh": "費用已一次付清且不退；成果要本人回來領，離線不會自動入帳。",
        "note_en": "The fee is prepaid and non-refundable. Come back and claim the output yourself; nothing is auto-credited.",
    }


def cancel_delegation(db: Session, agent: Agent) -> dict[str, Any]:
    """提前收回委任。預付費用不退（否則就能靠反覆成立／取消套利）。"""
    row = (
        db.query(Delegation)
        .filter(Delegation.agent_id == agent.id, Delegation.status == "active")
        .first()
    )
    if row is None:
        raise AppError("DELEGATION_NOT_FOUND", "No active stewardship to cancel.", status_code=404)
    row.status = "cancelled"
    db.add(row)
    db.commit()
    return {
        "status": "cancelled",
        "delegation_id": row.id,
        "refund_gold": 0,
        "note_zh": "已成立的每日成果仍可領取；預付費用不退，避免反覆成立套利。",
        "note_en": "Days already settled remain claimable; the prepaid fee is never refunded.",
    }


def claim_delegation(db: Session, agent: Agent) -> dict[str, Any]:
    """本人上線領取待領帳：只發糧食，金幣收入永遠是 0；重複領取不再入帳。"""
    rows = (
        db.query(DelegationLedger)
        .filter(DelegationLedger.agent_id == agent.id, DelegationLedger.status == "pending")
        .order_by(DelegationLedger.id.asc())
        .all()
    )
    if not rows:
        return {
            "status": "nothing_to_claim",
            "claimed_days": 0,
            "food_gained": 0,
            "gold_gained": 0,
            "new_food": agent.food,
            "new_gold": agent.gold,
        }

    food = sum(int(row.food_gain or 0) for row in rows)
    gold = sum(int(row.gold_gain or 0) for row in rows)
    # ledger 的 gold_gain 由結算寫入且恆為 0；這裡再夾一次，杜絕任何歷史髒資料變成印鈔。
    gold = min(gold, DELEGATE_GOLD_GAIN_PER_DAY * len(rows))

    locked = (
        db.query(Agent)
        .filter(Agent.id == agent.id)
        .with_for_update()
        .first()
    )
    if locked is None:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)
    locked.food += food
    locked.gold += gold
    db.add(locked)
    stamp = utc_now()
    for row in rows:
        row.status = "claimed"
        row.claimed_at = stamp
        db.add(row)
    write_chronicle(
        db,
        event_type="economy",
        title=f"{agent.name} claimed {len(rows)} stewardship days",
        content=(
            f"{agent.name} returned and claimed {len(rows)} pending days: "
            f"{food} food, {gold} gold. No income was credited while away."
        ),
    )
    db.commit()
    return {
        "status": "claimed",
        "claimed_days": len(rows),
        "food_gained": food,
        "gold_gained": gold,
        "new_food": locked.food,
        "new_gold": locked.gold,
        "note_zh": "這是本人上線領取；離線期間沒有任何資源自動入帳。",
        "note_en": "This was an explicit online claim; nothing was auto-credited while away.",
    }


def own_status(db: Session, agent: Agent, lang: str | None = None) -> dict[str, Any]:
    """給 /agent/briefing 用的自身委任段落（自己的資料，經 API key 才看得到）。"""
    code = _lang(lang)
    active = (
        db.query(Delegation)
        .filter(Delegation.agent_id == agent.id, Delegation.status == "active")
        .order_by(Delegation.id.desc())
        .first()
    )
    pending = (
        db.query(DelegationLedger)
        .filter(DelegationLedger.agent_id == agent.id, DelegationLedger.status == "pending")
        .order_by(DelegationLedger.day.asc())
        .all()
    )
    active_payload = None
    if active:
        active_payload = {
            "id": active.id,
            "policy": active.policy,
            "days": active.days,
            "start_day": active.start_day,
            "end_day": active.end_day,
            "settled_days": active.settled_days,
            "prepaid_gold": active.prepaid_gold,
            "food_per_day": DELEGATE_POLICIES.get(active.policy, {}).get("food_per_day", 0),
        }
    return {
        "enabled": settings.delegation_enabled,
        "active": active_payload,
        "pending_days": [
            {
                "day": row.day,
                "policy": row.policy,
                "food_gain": row.food_gain,
                "gold_gain": row.gold_gain,
            }
            for row in pending
        ],
        "claimable_days": len(pending),
        "claimable_food": sum(int(row.food_gain or 0) for row in pending),
        "claimable_gold": 0,
        "max_pending_days": DELEGATE_MAX_PENDING_DAYS,
        "claim_endpoint": "/agent/delegation/claim",
        "how_to_claim": {"method": "POST", "path": "/agent/delegation/claim", "auth": "X-API-Key"},
        "note_zh": "待領成果要本人上線領取；離線不會自動入帳，也不會產生金幣。",
        "note_en": "Pending output needs an explicit online claim; nothing is auto-credited and no gold is ever produced.",
    }


def settle_delegations(
    db: Session,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """worker 每輪呼叫：一個 UTC 日只結算一次，只結算「今天」，不補算過去。

    結算只做三件事：寫待領帳、更新委任進度、寫一則全城合計的史記與 pulse。
    完全不碰 agent 的任何數值欄位 —— 這是「不印鈔」最關鍵的一層。
    """
    day = utc_day(now)
    state_key = f"{SETTLED_PREFIX}{day}"
    if not force and get_state(db, state_key):
        return {"status": "already_settled", "date": day, **(_read_pulse(db, day) or _empty_pulse(day))}

    rows = (
        db.query(Delegation)
        .filter(
            Delegation.status == "active",
            Delegation.start_day < day,
            Delegation.end_day >= day,
        )
        .order_by(Delegation.id.asc())
        .all()
    )

    pulse = _empty_pulse(day)
    pulse["no_settlement_record"] = False
    pulse["active_households"] = len(rows)

    for row in rows:
        existing = (
            db.query(DelegationLedger)
            .filter(DelegationLedger.delegation_id == row.id, DelegationLedger.day == day)
            .first()
        )
        if existing:
            # force 重跑同一天也不能重複記帳。
            pulse["skipped_by_cap"] += 1
        else:
            pending_count = (
                db.query(DelegationLedger)
                .filter(
                    DelegationLedger.delegation_id == row.id,
                    DelegationLedger.status == "pending",
                )
                .count()
            )
            if pending_count >= DELEGATE_MAX_PENDING_DAYS:
                pulse["skipped_by_cap"] += 1
            else:
                food = int(DELEGATE_POLICIES.get(row.policy, {}).get("food_per_day", 0))
                db.add(
                    DelegationLedger(
                        delegation_id=row.id,
                        agent_id=row.agent_id,
                        day=day,
                        policy=row.policy,
                        food_gain=food,
                        gold_gain=DELEGATE_GOLD_GAIN_PER_DAY,
                        status="pending",
                    )
                )
                pulse["settled_households"] += 1
                pulse["food_escrowed"] += food
                # 工錢在成立時已預付；這裡只是當日認列的會計數字，不產生任何新的移轉。
                pulse["wage_gold_recognized"] += DELEGATE_DAILY_WAGE_GOLD

        row.last_settled_day = day
        row.settled_days += 1
        if day >= row.end_day:
            row.status = "expired"
            pulse["expired_households"] += 1
        db.add(row)

    _write_pulse(db, day, pulse)
    set_state(db, state_key, "settled")
    if pulse["active_households"]:
        write_chronicle(
            db,
            event_type="economy",
            title=f"{settings.city_name} 委任內政 / Delegated stewards, {day}",
            content=(
                f"{pulse['active_households']} households kept their estates running while their "
                f"lords were away: {pulse['settled_households']} days recorded, "
                f"{pulse['food_escrowed']} food held pending collection, "
                f"{pulse['skipped_by_cap']} households hit the unclaimed cap. "
                "No coin was created and nothing was credited automatically."
            ),
        )
    db.commit()
    return {
        "status": "settled" if rows else "no_active_households",
        "date": day,
        **pulse,
    }


def story_lines(db: Session, lang: str | None = None) -> list[str]:
    """今日史記的一行「世界仍有人在動」；沒有委任活動時完全不影響既有史記。"""
    pulse = _read_pulse(db, utc_day())
    if not pulse or not (pulse.get("active_households") or 0):
        return []
    if _lang(lang) == "en":
        return [
            f"While their lords were away, {pulse['active_households']} stewards kept the estates "
            f"turning; {pulse.get('food_escrowed', 0)} food now waits unclaimed — "
            "no coin was minted and no pantry was filled by absence alone."
        ]
    return [
        f"諸侯離城之際，{pulse['active_households']} 戶管事仍巡田修城，"
        f"今日記下 {pulse.get('food_escrowed', 0)} 糧待領；"
        "人不回來，糧不入庫，也不曾憑空多出一枚金幣。"
    ]


def today_summary(db: Session) -> dict[str, Any]:
    """給 /world/public/briefing 的輕量段落：只讀當日 pulse 與 active 數。"""
    day = utc_day()
    pulse = _read_pulse(db, day) or _empty_pulse(day)
    return {
        "enabled": settings.delegation_enabled,
        "active_households": int(pulse.get("active_households", 0) or 0),
        "settled_today": int(pulse.get("settled_households", 0) or 0),
        "food_escrowed_today": int(pulse.get("food_escrowed", 0) or 0),
        "skipped_by_cap_today": int(pulse.get("skipped_by_cap", 0) or 0),
        "no_settlement_record": bool(pulse.get("no_settlement_record", False)),
    }


def build_public_payload(
    db: Session,
    days: int | None = None,
    lang: str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """免登入、零個資的全城委任態勢：只有合計數字與規則。"""
    code = _lang(lang)
    window = PUBLIC_DAYS_DEFAULT if days is None else days
    if isinstance(window, bool) or not isinstance(window, int) or not 1 <= window <= PUBLIC_DAYS_MAX:
        raise AppError("INVALID_DELEGATION_WINDOW", f"days must be between 1 and {PUBLIC_DAYS_MAX}.", status_code=422)
    today = date.fromisoformat(utc_day(now))
    series: list[dict[str, Any]] = []
    for offset in range(window - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        pulse = _read_pulse(db, day) or _empty_pulse(day)
        series.append(
            {
                "date": day,
                "active_households": int(pulse.get("active_households", 0) or 0),
                "settled_households": int(pulse.get("settled_households", 0) or 0),
                "food_escrowed": int(pulse.get("food_escrowed", 0) or 0),
                "wage_gold_recognized": int(pulse.get("wage_gold_recognized", 0) or 0),
                "skipped_by_cap": int(pulse.get("skipped_by_cap", 0) or 0),
                "expired_households": int(pulse.get("expired_households", 0) or 0),
                "no_settlement_record": bool(pulse.get("no_settlement_record", False)),
            }
        )

    active_total = (
        db.query(Delegation)
        .filter(Delegation.status == "active")
        .count()
    )
    today_row = series[-1]
    rules = rules_payload(code)
    definitions = _definitions(code)
    return {
        "type": "delegated_stewardship",
        "schema_version": 1,
        "generated_at": _moment(now).isoformat(),
        "timezone": "UTC",
        "app_version": settings.app_version,
        "enabled": settings.delegation_enabled,
        "window": {
            "days": window,
            "start": series[0]["date"],
            "end": series[-1]["date"],
        },
        "today": {
            **today_row,
            "active_households_total": active_total,
        },
        "daily": series,
        "rules": rules,
        "definitions": definitions,
        "machine": {
            "type": "delegated_stewardship",
            "endpoint": "/world/public/delegation",
            "enabled": settings.delegation_enabled,
            "max_days": DELEGATE_MAX_DAYS,
            "max_pending_days": DELEGATE_MAX_PENDING_DAYS,
            "gold_gain_per_day": DELEGATE_GOLD_GAIN_PER_DAY,
            "claim_required": True,
            "no_backfill": True,
            "active_households_total": active_total,
            "privacy": "aggregates_only",
        },
        "privacy": "aggregates_only",
        "note_zh": "這是全城合計的局勢，不是指令。委任是花錢請人顧家，成果要本人回來領；離線不會自動生錢。",
        "note_en": "City-wide totals only, never an instruction. Delegation is paid caretaking: output stays pending until you return and claim it, because absence creates no income.",
    }
