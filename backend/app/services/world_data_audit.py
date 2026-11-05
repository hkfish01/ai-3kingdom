"""世界資料稽核（**唯讀**）。

這是 P0-5 資料清洗的第一步：先產出可檢視的報告，不做任何修改。
刪除／搬移／重置永遠要由營運者看完報告後明確執行，本模組不提供寫入路徑。

用法：
    GET /admin/data/audit            (需管理員 token)
    python -m scripts.audit_world_data   (本機維運)
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Agent, ChronicleEntry, City, Faction

TEST_NAME_RE = re.compile(
    r"^(probe|test|demo|smoke|tmp|openclaw[ _-]?定時任務代理|example|sample)",
    re.IGNORECASE,
)
KNOWN_CITY_ALIASES = ("洛陽", "洛阳", "Luoyang", "luoyang")


def _is_test_agent(name: str) -> bool:
    normalized = (name or "").strip()
    if TEST_NAME_RE.match(normalized):
        return True
    return "testagent" in normalized.lower() or "定時任務代理" in normalized


def audit_world_data(db: Session) -> dict[str, Any]:
    agents: list[Agent] = db.query(Agent).all()
    cities: list[City] = db.query(City).all()
    factions: list[Faction] = db.query(Faction).all()

    test_agents = [
        {"id": a.id, "name": a.name, "owner_user_id": a.owner_user_id, "created_at": a.created_at.isoformat()}
        for a in agents
        if _is_test_agent(a.name)
    ]

    by_name: dict[str, list[int]] = defaultdict(list)
    for a in agents:
        by_name[(a.name or "").strip()].append(a.id)
    duplicate_names = [
        {"name": name, "count": len(ids), "ids": ids}
        for name, ids in sorted(by_name.items())
        if name and len(ids) > 1
    ]

    # 城市名混雜：這正是史記曾經查不到資料的原因（見 CHANGELOG）。
    city_variants: dict[str, Any] = {
        "cities": [c.name for c in cities],
        "agent_home_city": dict(Counter(a.home_city for a in agents)),
        "agent_current_city": dict(Counter(a.current_city for a in agents)),
        "faction_home_city": dict(Counter(f.home_city for f in factions)),
        "chronicle_city_name": dict(
            db.query(ChronicleEntry.city_name, func.count(ChronicleEntry.id))
            .group_by(ChronicleEntry.city_name)
            .all()
        ),
    }
    seen_variants = {
        *city_variants["cities"],
        *city_variants["agent_home_city"],
        *city_variants["agent_current_city"],
        *city_variants["faction_home_city"],
        *city_variants["chronicle_city_name"],
    }
    mismatched_city_names = sorted(
        v for v in seen_variants if v and v not in KNOWN_CITY_ALIASES
    )

    member_counts = dict(
        db.query(Agent.faction_id, func.count(Agent.id))
        .filter(Agent.faction_id.isnot(None))
        .group_by(Agent.faction_id)
        .all()
    )
    faction_report = [
        {
            "id": f.id,
            "name": f.name,
            "leader_agent_id": f.leader_agent_id,
            "leader_exists": db.get(Agent, f.leader_agent_id) is not None,
            "member_count": member_counts.get(f.id, 0),
            "home_city": f.home_city,
        }
        for f in factions
    ]

    zero_food = sum(1 for a in agents if (a.food or 0) == 0)
    zero_reputation = sum(1 for a in agents if (a.reputation or 0) == 0)
    no_faction = sum(1 for a in agents if a.faction_id is None)
    empty_treasury_food = [c.name for c in cities if (c.treasury_food or 0) == 0]

    recommendations: list[str] = []
    if test_agents:
        recommendations.append(
            f"隱藏／封存 {len(test_agents)} 個測試號（建议先停用而不實體刪除，保留歷史參照）。"
        )
    if duplicate_names:
        recommendations.append(f"處理 {len(duplicate_names)} 組重複顯示名稱（如「小魚兒」）。")
    if len(seen_variants) > 1:
        recommendations.append("統一城市名寫法，或在所有查詢改用別名 clause（洛陽／洛阳／Luoyang）。")
    if empty_treasury_food:
        recommendations.append("城倉糧 0：啟用洛陽糧盡事件，讓諸侯捐糧成為可玩的解法。")
    if no_faction and len(agents) >= 10:
        recommendations.append(f"{no_faction} 位諸侯未選邊：用三城分立事件給他們選邊的理由。")
    if any(not f["leader_exists"] for f in faction_report):
        recommendations.append("有勢力的 leader_agent_id 指向不存在的人物，需補正。")
    if not recommendations:
        recommendations.append("目前未發現需要清洗的項目。")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "read_only": True,
        "summary": {
            "agents": len(agents),
            "cities": len(cities),
            "factions": len(factions),
            "test_agents": len(test_agents),
            "duplicate_names": len(duplicate_names),
            "agents_zero_food": zero_food,
            "agents_zero_reputation": zero_reputation,
            "agents_without_faction": no_faction,
            "city_names_in_use": sorted(v for v in seen_variants if v),
        },
        "test_agents": test_agents,
        "duplicate_names": duplicate_names,
        "city_variants": city_variants,
        "unknown_city_names": mismatched_city_names,
        "zero_treasury_food_cities": empty_treasury_food,
        "factions": faction_report,
        "recommendations": recommendations,
    }
