"""商城（超市）與糧荒止血。

設計重點：
1. 購買是「扣款 → 發貨」的單一交易，扣款前先檢查餘額，餘額不足不發貨、不扣錢。
2. 用 row lock 讀取 agent，避免兩個請求同時通過餘額檢查而把金幣扣成負數。
   SQLite 會自動忽略 FOR UPDATE（測試環境），PostgreSQL 會真的上鎖。
3. 冪等由 `AgentActionEvent` 負責：事件已 completed 就直接回傳原結果，不重複扣款。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..config import settings
from ..errors import AppError
from ..models import Agent
from ..rules import MARKET_ITEMS, MARKET_MAX_QUANTITY
from .chronicle import write_chronicle
from .positions import DAILY_AGENT_FOOD_CONSUMPTION
from .system_state import get_state, set_state


def _lang(value: str | None) -> str:
    return "en" if value == "en" else "zh"


def catalog_payload(lang: str | None = None) -> dict:
    """公開商品目錄：免登入，給 agent 與觀戰者讀。"""
    code = _lang(lang)
    items = []
    for item_id, item in MARKET_ITEMS.items():
        items.append(
            {
                "item_id": item_id,
                "name": item[f"name_{code}"],
                "description": item[f"desc_{code}"],
                "unit_price_gold": item["gold"],
                "food_per_unit": item["food"],
                "energy_per_unit": item["energy"],
            }
        )
    return {
        "items": items,
        "max_quantity_per_purchase": MARKET_MAX_QUANTITY,
        "currency": "gold",
        "how_to_buy": {
            "method": "POST",
            "path": "/action/work",
            "auth": "X-API-Key (the same key issued at bootstrap)",
            "body": {"action_type": "buy", "payload": {"item": "grain_bag", "quantity": 1}},
        },
        "note_zh": "商城由你的 Agent 自行決定是否採買；人類只能觀看，不能代買。",
        "note_en": "Only your agent decides whether to buy; humans can watch, not purchase.",
    }


def quote(item_id: object, quantity: object) -> dict:
    """驗證商品與數量，回傳不含 DB 狀態的報價。"""
    if not isinstance(item_id, str) or item_id.strip().lower() not in MARKET_ITEMS:
        raise AppError(
            "MARKET_ITEM_NOT_FOUND",
            "Unknown market item. Read /world/public/market for the catalog.",
            status_code=404,
        )
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MARKET_MAX_QUANTITY:
        raise AppError(
            "INVALID_MARKET_QUANTITY",
            f"quantity must be an integer between 1 and {MARKET_MAX_QUANTITY}.",
            status_code=422,
        )
    key = item_id.strip().lower()
    item = MARKET_ITEMS[key]
    return {
        "item_id": key,
        "quantity": quantity,
        "unit_price_gold": item["gold"],
        "gold_cost": item["gold"] * quantity,
        "food_gain": item["food"] * quantity,
        "energy_gain": item["energy"] * quantity,
    }


def purchase(db: Session, agent: Agent, item_id: object, quantity: object) -> dict:
    """在同一個交易內先檢查餘額、再扣款、再發貨。

    呼叫者（action event processor）負責 commit / rollback。
    """
    deal = quote(item_id, quantity)

    # 重新以列鎖讀取，避免併發請求各自看到舊餘額。
    locked = (
        db.query(Agent)
        .filter(Agent.id == agent.id)
        .with_for_update()
        .first()
    )
    if locked is None:
        raise AppError("AGENT_NOT_FOUND", "The specified agent does not exist.", status_code=404)

    if locked.gold < deal["gold_cost"]:
        raise AppError(
            "INSUFFICIENT_RESOURCES",
            f"Not enough gold: need {deal['gold_cost']}, have {locked.gold}.",
            status_code=422,
        )

    locked.gold -= deal["gold_cost"]
    locked.food += deal["food_gain"]
    locked.energy += deal["energy_gain"]
    db.add(locked)

    return {
        **deal,
        "gold_spent": deal["gold_cost"],
        "food_gained": deal["food_gain"],
        "energy_gained": deal["energy_gain"],
        "new_gold": locked.gold,
        "new_food": locked.food,
        "new_energy": locked.energy,
    }


def relief_preview(db: Session, floor: int) -> dict:
    """試算開倉賑濟：哪些 agent 低於底線、總共要補多少糧。"""
    if floor < 1 or floor > 10000:
        raise AppError("INVALID_MARKET_RELIEF_FLOOR", "floor must be between 1 and 10000.", status_code=422)
    rows = (
        db.query(Agent)
        .filter(Agent.food < floor)
        .order_by(Agent.id.asc())
        .all()
    )
    return {
        "floor": floor,
        "agents": len(rows),
        "food_to_grant": sum(floor - row.food for row in rows),
        "sample": [
            {"agent_id": row.id, "name": row.name, "food": row.food, "grant": floor - row.food}
            for row in rows[:10]
        ],
    }


def run_market_relief(
    db: Session,
    floor: int,
    *,
    day: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """把低於底線的 agent 補到底線（不是加到底線之上）。

    每天最多一次，冪等記錄在 system_state；`dry_run` 只試算不寫入。
    `force=True` 可忽略當日已執行的紀錄（營運者手動補發用）。
    """
    preview = relief_preview(db, floor)
    if dry_run:
        return {"status": "preview", "applied": False, **preview}

    date_key = day or datetime.now(timezone.utc).date().isoformat()
    state_key = f"market.relief.{date_key}"
    if not force and get_state(db, state_key):
        return {"status": "already_applied", "applied": False, "date": date_key, **preview}

    rows = (
        db.query(Agent)
        .filter(Agent.food < floor)
        .order_by(Agent.id.asc())
        .all()
    )
    if not rows:
        # 沒有人低於底線時不要刷一則「0 人受賑」的史記，也不要重複寫入。
        set_state(db, state_key, "no_starving_agents")
        db.commit()
        return {"status": "no_starving_agents", "applied": False, "date": date_key, **preview}

    for row in rows:
        row.food = floor
        db.add(row)

    write_chronicle(
        db,
        event_type="economy",
        title=f"{settings.city_name} 開倉賑濟 / Market relief",
        content=(
            f"Food floor {floor}: {len(rows)} agents topped up, "
            f"{preview['food_to_grant']} food granted in total."
        ),
    )
    set_state(db, state_key, f"floor={floor};agents={len(rows)};food={preview['food_to_grant']}")
    db.commit()
    return {"status": "applied", "applied": True, "date": date_key, **preview}


def famine_snapshot(db: Session, floor: int) -> dict:
    """只讀糧食欄位，判斷是不是「全城一起餓到付不起明日口糧」。

    觸發線（基本口糧 `DAILY_AGENT_FOOD_CONSUMPTION`）與賑濟目標（`floor`）故意
    分開：若拿 floor 當觸發線，補到 60 後隔日重置扣 10 又會達標，等於天天白送，
    商城經濟會被架空。food=50 這種「還活得下去」的狀態不該觸發開倉。
    """
    rows = db.query(Agent.food).all()
    total = len(rows)
    trigger = DAILY_AGENT_FOOD_CONSUMPTION
    starving = sum(1 for row in rows if row[0] < trigger)
    zero = sum(1 for row in rows if row[0] <= 0)
    return {
        "floor": floor,
        "trigger_food": trigger,
        "total_agents": total,
        "starving_agents": starving,
        "zero_food_agents": zero,
        "starving_ratio": round(starving / total, 4) if total else 0.0,
    }


def ensure_famine_relief(
    db: Session,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> dict:
    """全城饑荒才開倉；正常年景不寫入任何 agent 資料，商城仍是主要自救路徑。

    每天只檢查一次（system_state `market.famine.checked.<date>`），重複呼叫不會
    重複補糧；真正的補糧交給 `run_market_relief`，它自己還有第二層日期冪等。
    """
    day = (now or datetime.now(timezone.utc)).date().isoformat()
    floor = settings.market_famine_relief_floor
    if floor < 1:
        return {"status": "disabled", "date": day, "applied": False}

    check_key = f"market.famine.checked.{day}"
    if not force and get_state(db, check_key):
        return {"status": "already_checked", "date": day, "applied": False}

    snapshot = famine_snapshot(db, floor)
    ratio = min(1.0, max(0.01, settings.market_famine_starving_ratio))
    triggered = (
        snapshot["total_agents"] >= settings.market_famine_min_agents
        and snapshot["starving_ratio"] >= ratio
    )

    if not triggered:
        set_state(db, check_key, f"healthy;ratio={snapshot['starving_ratio']}")
        db.commit()
        return {"status": "healthy", "date": day, "applied": False, **snapshot}

    relief = run_market_relief(db, floor, day=day)
    set_state(db, check_key, f"relief;{relief['status']};floor={floor}")
    db.commit()
    return {
        "status": "relief_applied" if relief["applied"] else "relief_already_applied",
        "date": day,
        "applied": relief["applied"],
        **snapshot,
        "relief": relief,
    }
