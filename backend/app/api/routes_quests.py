from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..api.deps import get_current_user
from ..db import get_db
from ..models import Agent, AgentDailyQuest, AgentWeeklyQuest, DailyQuestTemplate, User
from ..config import settings

router = APIRouter(prefix="/quests", tags=["quests"])


def get_utc_date() -> str:
    """Get current UTC date string (YYYY-MM-DD)"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_week_start() -> str:
    """Get current week's Monday UTC date string"""
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    return monday.strftime("%Y-%m-%d")


# Default daily quest templates
DEFAULT_DAILY_QUESTS = [
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

# Default weekly quest templates
DEFAULT_WEEKLY_QUESTS = [
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


def ensure_quest_templates(db: Session):
    """Ensure default quest templates exist in database"""
    for quest_data in DEFAULT_DAILY_QUESTS:
        existing = db.query(DailyQuestTemplate).filter(
            DailyQuestTemplate.quest_type == quest_data["quest_type"],
            DailyQuestTemplate.is_active == True
        ).first()
        
        if not existing:
            template = DailyQuestTemplate(
                quest_type=quest_data["quest_type"],
                target=quest_data["target"],
                reward_gold=quest_data["reward_gold"],
                reward_food=quest_data["reward_food"],
                reward_reputation=quest_data["reward_reputation"],
                description_zh=quest_data["description_zh"],
                description_en=quest_data["description_en"],
            )
            db.add(template)
    
    db.commit()


def generate_daily_quests_for_agent(db: Session, agent_id: int, date: str):
    """Generate daily quests for an agent if they don't exist"""
    existing = db.query(AgentDailyQuest).filter(
        AgentDailyQuest.agent_id == agent_id,
        AgentDailyQuest.quest_date == date
    ).first()
    
    if existing:
        return  # Already generated
    
    for quest_data in DEFAULT_DAILY_QUESTS:
        quest = AgentDailyQuest(
            agent_id=agent_id,
            quest_type=quest_data["quest_type"],
            target=quest_data["target"],
            current_progress=0,
            is_completed=False,
            is_claimed=False,
            quest_date=date,
        )
        db.add(quest)
    
    db.commit()


def generate_weekly_quests_for_agent(db: Session, agent_id: int, week_start: str):
    """Generate weekly quests for an agent if they don't exist"""
    existing = db.query(AgentWeeklyQuest).filter(
        AgentWeeklyQuest.agent_id == agent_id,
        AgentWeeklyQuest.week_start == week_start
    ).first()
    
    if existing:
        return  # Already generated
    
    for quest_data in DEFAULT_WEEKLY_QUESTS:
        quest = AgentWeeklyQuest(
            agent_id=agent_id,
            quest_type=quest_data["quest_type"],
            target=quest_data["target"],
            current_progress=0,
            is_completed=False,
            is_claimed=False,
            week_start=week_start,
        )
        db.add(quest)
    
    db.commit()


@router.get("/daily")
def get_daily_quests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current daily quests for the user's agents"""
    ensure_quest_templates(db)
    
    agents = db.query(Agent).filter(Agent.user_id == current_user.id).all()
    if not agents:
        return {"success": True, "data": {"date": get_utc_date(), "quests": []}}
    
    utc_date = get_utc_date()
    
    all_quests = []
    for agent in agents:
        generate_daily_quests_for_agent(db, agent.id, utc_date)
        
        quests = db.query(AgentDailyQuest).filter(
            AgentDailyQuest.agent_id == agent.id,
            AgentDailyQuest.quest_date == utc_date
        ).all()
        
        for quest in quests:
            all_quests.append({
                "id": quest.id,
                "agent_id": agent.id,
                "agent_name": agent.name,
                "type": quest.quest_type,
                "target": quest.target,
                "current_progress": quest.current_progress,
                "is_completed": quest.is_completed,
                "is_claimed": quest.is_claimed,
            })
    
    return {"success": True, "data": {"date": utc_date, "quests": all_quests}}


@router.get("/weekly")
def get_weekly_quests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current weekly quests for the user's agents"""
    agents = db.query(Agent).filter(Agent.user_id == current_user.id).all()
    if not agents:
        return {"success": True, "data": {"week_start": get_week_start(), "quests": []}}
    
    week_start = get_week_start()
    
    all_quests = []
    for agent in agents:
        generate_weekly_quests_for_agent(db, agent.id, week_start)
        
        quests = db.query(AgentWeeklyQuest).filter(
            AgentWeeklyQuest.agent_id == agent.id,
            AgentWeeklyQuest.week_start == week_start
        ).all()
        
        for quest in quests:
            all_quests.append({
                "id": quest.id,
                "agent_id": agent.id,
                "agent_name": agent.name,
                "type": quest.quest_type,
                "target": quest.target,
                "current_progress": quest.current_progress,
                "is_completed": quest.is_completed,
                "is_claimed": quest.is_claimed,
            })
    
    return {"success": True, "data": {"week_start": week_start, "quests": all_quests}}


@router.post("/daily/{quest_id}/claim")
def claim_daily_reward(
    quest_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Claim reward for a completed daily quest"""
    quest = db.query(AgentDailyQuest).filter(AgentDailyQuest.id == quest_id).first()
    
    if not quest:
        raise HTTPException(status_code=404, detail="Quest not found")
    
    if quest.is_claimed:
        raise HTTPException(status_code=400, detail="Reward already claimed")
    
    if not quest.is_completed:
        raise HTTPException(status_code=400, detail="Quest not completed")
    
    agent = db.query(Agent).filter(Agent.id == quest.agent_id).first()
    if not agent or agent.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Grant rewards
    agent.gold = (agent.gold or 0) + quest.reward_gold
    agent.food = (agent.food or 0) + quest.reward_food
    agent.reputation = (agent.reputation or 0) + quest.reward_reputation
    
    quest.is_claimed = True
    db.commit()
    
    return {
        "success": True,
        "data": {
            "reward_gold": quest.reward_gold,
            "reward_food": quest.reward_food,
            "reward_reputation": quest.reward_reputation,
            "new_gold": agent.gold,
            "new_food": agent.food,
            "new_reputation": agent.reputation,
        }
    }


@router.post("/weekly/{quest_id}/claim")
def claim_weekly_reward(
    quest_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Claim reward for a completed weekly quest"""
    quest = db.query(AgentWeeklyQuest).filter(AgentWeeklyQuest.id == quest_id).first()
    
    if not quest:
        raise HTTPException(status_code=404, detail="Quest not found")
    
    if quest.is_claimed:
        raise HTTPException(status_code=400, detail="Reward already claimed")
    
    if not quest.is_completed:
        raise HTTPException(status_code=400, detail="Quest not completed")
    
    agent = db.query(Agent).filter(Agent.id == quest.agent_id).first()
    if not agent or agent.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Grant rewards
    agent.gold = (agent.gold or 0) + quest.reward_gold
    agent.food = (agent.food or 0) + quest.reward_food
    agent.reputation = (agent.reputation or 0) + quest.reward_reputation
    
    quest.is_claimed = True
    db.commit()
    
    return {
        "success": True,
        "data": {
            "reward_gold": quest.reward_gold,
            "reward_food": quest.reward_food,
            "reward_reputation": quest.reward_reputation,
            "new_gold": agent.gold,
            "new_food": agent.food,
            "new_reputation": agent.reputation,
        }
    }


@router.post("/update_progress")
def update_quest_progress(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update quest progress for an agent"""
    agent_id = payload.get("agent_id")
    quest_type = payload.get("quest_type")
    progress_delta = payload.get("progress", 1)
    
    if not agent_id or not quest_type:
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    utc_date = get_utc_date()
    week_start = get_week_start()
    
    # Update daily quest progress
    daily_quest = db.query(AgentDailyQuest).filter(
        AgentDailyQuest.agent_id == agent_id,
        AgentDailyQuest.quest_type == quest_type,
        AgentDailyQuest.quest_date == utc_date
    ).first()
    
    if daily_quest and not daily_quest.is_claimed:
        daily_quest.current_progress += progress_delta
        if daily_quest.current_progress >= daily_quest.target:
            daily_quest.is_completed = True
        db.commit()
    
    # Update weekly quest progress (for weekly versions of quest types)
    weekly_quest_type = f"{quest_type}_weekly" if quest_type == "earn_gold" else quest_type
    weekly_quest = db.query(AgentWeeklyQuest).filter(
        AgentWeeklyQuest.agent_id == agent_id,
        AgentWeeklyQuest.quest_type == weekly_quest_type,
        AgentWeeklyQuest.week_start == week_start
    ).first()
    
    if weekly_quest and not weekly_quest.is_claimed:
        weekly_quest.current_progress += progress_delta
        if weekly_quest.current_progress >= weekly_quest.target:
            weekly_quest.is_completed = True
        db.commit()
    
    return {"success": True}