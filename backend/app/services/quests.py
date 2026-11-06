"""每日／每週任務：模板、進度與領獎。

修復前這套功能實際上完全不可用：
- 路由查 `Agent.user_id`，但模型欄位是 `owner_user_id` → 500
- 領獎讀 `AgentDailyQuest.reward_gold/food/reputation`，模型沒有這些欄位 → AttributeError
- `earn_gold` 目標 100，但每次工作只 +1（每日能量上限使其不可能完成）
- `send_messages` / `complete_dungeon` / `join_federation` 沒有任何進度來源

設計原則（沿用專案既有決策）：
- **不改 DB schema**：獎勵一律從模板常數查，不加 reward 欄位、不加新表。
- **不改既有 endpoint 回傳結構**：列表只新增獎勵與描述欄位。
- **不開放外部任意增量**：進度只由系統事件（`update_progress`）驅動，
  讓 `/quests/update_progress` 變成唯讀回報，避免任何人自己洗進度領獎。
- **不替 agent 做決定**：領獎要 agent（或其擁有者）主動呼叫。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..errors import AppError
from ..models import Agent, AgentDailyQuest, AgentWeeklyQuest, DailyQuestTemplate

logger = logging.getLogger(__name__)

DEFAULT_DAILY_QUESTS: list[dict[str, Any]] = [
    {
        "quest_type": "earn_gold",
        "target": 100,
        "reward_gold": 50,
        "reward_food": 0,
        "reward_reputation": 0,
        "description_zh": "賺取 100 金幣",
        "description_en": "Earn 100 gold",
    },
    {
        "quest_type": "train_troops",
        "target": 50,
        "reward_gold": 30,
        "reward_food": 0,
        "reward_reputation": 0,
        "description_zh": "訓練 50 兵力",
        "description_en": "Train 50 troops",
    },
    {
        "quest_type": "send_messages",
        "target": 3,
        "reward_gold": 20,
        "reward_food": 0,
        "reward_reputation": 0,
        "description_zh": "發送 3 條訊息",
        "description_en": "Send 3 messages",
    },
    {
        "quest_type": "complete_battle",
        "target": 1,
        "reward_gold": 40,
        "reward_food": 20,
        "reward_reputation": 10,
        "description_zh": "完成 1 次戰鬥",
        "description_en": "Complete 1 battle",
    },
]

DEFAULT_WEEKLY_QUESTS: list[dict[str, Any]] = [
    {
        "quest_type": "earn_gold_weekly",
        "target": 1000,
        "reward_gold": 200,
        "reward_food": 0,
        "reward_reputation": 0,
        "description_zh": "累積 1000 金幣",
        "description_en": "Accumulate 1000 gold",
    },
    {
        "quest_type": "complete_dungeon",
        "target": 5,
        "reward_gold": 150,
        "reward_food": 100,
        "reward_reputation": 50,
        "description_zh": "挑戰 5 次副本",
        "description_en": "Challenge 5 dungeons",
    },
    {
        "quest_type": "join_federation",
        "target": 1,
        "reward_gold": 100,
        "reward_food": 50,
        "reward_reputation": 30,
        "description_zh": "加入聯盟",
        "description_en": "Join a federation",
    },
]

QUEST_TEMPLATES = {
    str(row["quest_type"]): row
    for row in (*DEFAULT_DAILY_QUESTS, *DEFAULT_WEEKLY_QUESTS)
}
# 只有這些系統事件可以推進進度。
EVENT_TYPES = frozenset(
    {
        "earn_gold",
        "train_troops",
        "send_messages",
        "complete_battle",
        "complete_dungeon",
        "join_federation",
    }
)
# earn_gold 事件同時推進每週的 earn_gold_weekly。
WEEKLY_ALIAS = {"earn_gold": "earn_gold_weekly"}


def utc_date(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).strftime("%Y-%m-%d")


def week_start(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    monday = current.astimezone(timezone.utc) - timedelta(days=current.weekday())
    return monday.strftime("%Y-%m-%d")


def reward_for(quest_type: str) -> dict[str, int]:
    """獎勵永遠從模板常數查：AgentDailyQuest / AgentWeeklyQuest 沒有 reward 欄位。"""
    row = QUEST_TEMPLATES.get(quest_type, {})
    return {
        "reward_gold": int(row.get("reward_gold", 0)),
        "reward_food": int(row.get("reward_food", 0)),
        "reward_reputation": int(row.get("reward_reputation", 0)),
    }


def ensure_templates(db: Session) -> None:
    """維持 daily_quest_templates 的既有用途；獎勵不從這裡讀，避免兩份資料不一致。"""
    existing = {
        row.quest_type
        for row in db.query(DailyQuestTemplate).filter(DailyQuestTemplate.is_active.is_(True)).all()
    }
    dirty = False
    for row in DEFAULT_DAILY_QUESTS:
        if row["quest_type"] in existing:
            continue
        db.add(
            DailyQuestTemplate(
                quest_type=row["quest_type"],
                target=row["target"],
                reward_gold=row["reward_gold"],
                reward_food=row["reward_food"],
                reward_reputation=row["reward_reputation"],
                description_zh=row["description_zh"],
                description_en=row["description_en"],
            )
        )
        dirty = True
    if dirty:
        db.commit()


def _ensure_rows(
    db: Session,
    model: type[AgentDailyQuest] | type[AgentWeeklyQuest],
    period_field: str,
    period_value: str,
    agent_id: int,
    definitions: list[dict[str, Any]],
) -> None:
    """逐筆冪等產生；原本只檢查「任一筆存在」就 return，部分產生時會永久漏任務。"""
    rows = (
        db.query(model)
        .filter(model.agent_id == agent_id, getattr(model, period_field) == period_value)
        .all()
    )
    present = {row.quest_type for row in rows}
    dirty = False
    for definition in definitions:
        if definition["quest_type"] in present:
            continue
        db.add(
            model(
                agent_id=agent_id,
                quest_type=definition["quest_type"],
                target=definition["target"],
                current_progress=0,
                is_completed=False,
                is_claimed=False,
                **{period_field: period_value},
            )
        )
        dirty = True
    if dirty:
        db.commit()


def generate_daily(db: Session, agent_id: int, date_str: str | None = None) -> str:
    value = date_str or utc_date()
    _ensure_rows(db, AgentDailyQuest, "quest_date", value, agent_id, DEFAULT_DAILY_QUESTS)
    return value


def generate_weekly(db: Session, agent_id: int, week_str: str | None = None) -> str:
    value = week_str or week_start()
    _ensure_rows(db, AgentWeeklyQuest, "week_start", value, agent_id, DEFAULT_WEEKLY_QUESTS)
    return value


def list_quests(
    db: Session,
    agent_ids: list[int],
    weekly: bool = False,
    lang: str = "zh",
    now: datetime | None = None,
) -> dict[str, Any]:
    """產生當期任務並回傳列表；欄位與舊版相容，只新增獎勵與描述。"""
    ensure_templates(db)
    period = week_start(now) if weekly else utc_date(now)
    model = AgentWeeklyQuest if weekly else AgentDailyQuest
    period_field = "week_start" if weekly else "quest_date"
    definitions = DEFAULT_WEEKLY_QUESTS if weekly else DEFAULT_DAILY_QUESTS
    items: list[dict[str, Any]] = []
    for agent_id in agent_ids:
        _ensure_rows(db, model, period_field, period, agent_id, definitions)
        agent = db.get(Agent, agent_id)
        rows = (
            db.query(model)
            .filter(model.agent_id == agent_id, getattr(model, period_field) == period)
            .order_by(model.id)
            .all()
        )
        for quest in rows:
            definition = QUEST_TEMPLATES.get(quest.quest_type, {})
            reward = reward_for(quest.quest_type)
            items.append(
                {
                    "id": quest.id,
                    "agent_id": agent_id,
                    "agent_name": agent.name if agent else "",
                    "type": quest.quest_type,
                    "target": quest.target,
                    "current_progress": quest.current_progress or 0,
                    "is_completed": bool(quest.is_completed),
                    "is_claimed": bool(quest.is_claimed),
                    "description": definition.get(
                        "description_zh" if lang == "zh" else "description_en", quest.quest_type
                    ),
                    **reward,
                }
            )
    return {"period": period, "quests": items}


def update_progress(db: Session, agent_id: int, quest_type: str, delta: int = 1) -> None:
    """由系統事件推進進度；失敗只記 log，絕不影響主動作。

    `earn_gold` 的 delta 是「實際賺到的金幣」而非次數，否則 target=100 永遠達不到。
    """
    if quest_type not in EVENT_TYPES:
        return
    try:
        amount = int(delta)
        if amount <= 0:
            return
        targets = (
            (AgentDailyQuest, "quest_date", utc_date(), quest_type),
            (
                AgentWeeklyQuest,
                "week_start",
                week_start(),
                WEEKLY_ALIAS.get(quest_type, quest_type),
            ),
        )
        dirty = False
        for model, field, value, quest_key in targets:
            row = (
                db.query(model)
                .filter(
                    model.agent_id == agent_id,
                    model.quest_type == quest_key,
                    getattr(model, field) == value,
                )
                .first()
            )
            if row is None or row.is_claimed:
                continue
            row.current_progress = (row.current_progress or 0) + amount
            if row.current_progress >= row.target:
                row.is_completed = True
            db.add(row)
            dirty = True
        if dirty:
            db.commit()
    except Exception as exc:  # 任務進度永遠不能讓主要動作失敗
        logger.warning("Failed to update quest progress: %s", exc)


def claim(
    db: Session,
    quest_id: int,
    owner_user_id: int,
    weekly: bool = False,
) -> dict[str, Any]:
    """領獎：檢查擁有者、完成狀態、重複領取；用 row lock 避免併發重複發獎。"""
    model = AgentWeeklyQuest if weekly else AgentDailyQuest
    query = db.query(model).filter(model.id == quest_id)
    try:
        use_row_lock = db.get_bind().dialect.name != "sqlite"
    except Exception:
        use_row_lock = False
    if use_row_lock:
        query = query.with_for_update()
    quest = query.first()
    if not quest:
        raise AppError("QUEST_NOT_FOUND", "Quest not found.", status_code=404)
    agent = db.get(Agent, quest.agent_id)
    if not agent or agent.owner_user_id != owner_user_id:
        raise AppError("FORBIDDEN", "You do not own this agent.", status_code=403)
    if quest.is_claimed:
        raise AppError("QUEST_ALREADY_CLAIMED", "Reward already claimed.", status_code=409)
    if not quest.is_completed or (quest.current_progress or 0) < quest.target:
        raise AppError("QUEST_NOT_COMPLETED", "Quest not completed.", status_code=400)

    reward = reward_for(quest.quest_type)
    agent.gold = (agent.gold or 0) + reward["reward_gold"]
    agent.food = (agent.food or 0) + reward["reward_food"]
    agent.reputation = (agent.reputation or 0) + reward["reward_reputation"]
    quest.is_claimed = True
    db.add(agent)
    db.add(quest)
    db.commit()
    return {
        **reward,
        "quest_type": quest.quest_type,
        "new_gold": agent.gold,
        "new_food": agent.food,
        "new_reputation": agent.reputation,
    }
