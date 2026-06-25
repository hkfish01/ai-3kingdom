"""
AI DevOps Agent Service

每天自動檢查系統狀況，分析遊戲數據，並規劃開心新功能。
所有變更都通過 PR 提交，由人工審核後合併。
"""

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    ActionLog,
    Agent,
    AgentActionEvent,
    BattleLog,
    ChronicleEntry,
    User,
    utc_now,
)
from ..services.system_state import get_state, set_state


class HealthStatus(Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class HealthCheckResult:
    status: HealthStatus
    checks: dict[str, Any]
    recommendations: list[str]


@dataclass
class GameAnalysisResult:
    balance_issues: list[dict]
    economy_issues: list[dict]
    engagement_metrics: dict
    suggestions: list[str]


@dataclass
class FeaturePlan:
    title: str
    description: str
    priority: int  # 1 = high, 3 = low
    category: str  # "bug_fix", "balance", "feature", "optimization"
    files_to_change: list[str]
    code_template: str
    test_template: str
    estimated_impact: str


# ============================================================
# 1. System Health Monitor
# ============================================================

class SystemHealthMonitor:
    """
    檢查系統健康狀況
    """

    def __init__(self, db: Session):
        self.db = db

    async def check_all(self) -> HealthCheckResult:
        """
        執行所有健康檢查
        """
        checks = {
            "database": await self._check_database(),
            "api_health": await self._check_api_health(),
            "recent_errors": self._check_recent_errors(),
            "agent_activity": self._check_agent_activity(),
            "battle_logs": self._check_battle_logs(),
            "federation_health": await self._check_federation(),
        }

        # 決定整體狀態
        statuses = [c["status"] for c in checks.values()]
        if "critical" in statuses:
            overall = HealthStatus.CRITICAL
        elif "warning" in statuses:
            overall = HealthStatus.WARNING
        else:
            overall = HealthStatus.HEALTHY

        recommendations = self._generate_recommendations(checks)

        return HealthCheckResult(
            status=overall,
            checks=checks,
            recommendations=recommendations,
        )

    async def _check_database(self) -> dict:
        """檢查資料庫連接和數據一致性"""
        try:
            # 檢查主要表的基本統計
            user_count = self.db.query(User).count()
            agent_count = self.db.query(Agent).count()

            # 檢查是否有孤立 agent（沒有 owner）
            orphan_agents = (
                self.db.query(Agent)
                .filter(Agent.owner_user_id.is_(None))
                .count()
            )

            # 檢查最近建立的記錄
            recent_actions = (
                self.db.query(ActionLog)
                .filter(ActionLog.created_at >= utc_now() - timedelta(hours=1))
                .count()
            )

            return {
                "status": "healthy" if orphan_agents == 0 else "warning",
                "user_count": user_count,
                "agent_count": agent_count,
                "orphan_agents": orphan_agents,
                "recent_actions_1h": recent_actions,
                "message": "Database connection OK" if orphan_agents == 0 else f"Found {orphan_agents} orphan agents",
            }
        except Exception as e:
            return {
                "status": "critical",
                "error": str(e),
                "message": "Database connection failed",
            }

    async def _check_api_health(self) -> dict:
        """檢查 API 端點響應"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{settings.city_base_url}/health")
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "status": "healthy",
                        "response_time_ms": response.elapsed.total_seconds() * 1000,
                        "version": data.get("data", {}).get("version", "unknown"),
                        "message": "API responding normally",
                    }
                else:
                    return {
                        "status": "warning",
                        "status_code": response.status_code,
                        "message": f"API returned {response.status_code}",
                    }
        except httpx.TimeoutException:
            return {
                "status": "critical",
                "message": "API timeout",
            }
        except Exception as e:
            return {
                "status": "warning",
                "message": f"API check failed: {str(e)}",
            }

    def _check_recent_errors(self) -> dict:
        """檢查最近 24 小時的錯誤"""
        cutoff = utc_now() - timedelta(hours=24)

        failed_events = (
            self.db.query(AgentActionEvent)
            .filter(
                AgentActionEvent.status == "failed",
                AgentActionEvent.created_at >= cutoff,
            )
            .count()
        )

        error_codes = (
            self.db.query(AgentActionEvent.error_code)
            .filter(
                AgentActionEvent.status == "failed",
                AgentActionEvent.created_at >= cutoff,
            )
            .distinct()
            .all()
        )

        return {
            "status": "healthy" if failed_events < 10 else "warning" if failed_events < 50 else "critical",
            "failed_events_24h": failed_events,
            "unique_error_codes": [e[0] for e in error_codes],
            "message": f"{failed_events} failed events in last 24h",
        }

    def _check_agent_activity(self) -> dict:
        """檢查 Agent 活動狀況"""
        cutoff = utc_now() - timedelta(days=7)

        active_agents = (
            self.db.query(Agent)
            .filter(Agent.updated_at >= cutoff)
            .count()
        )

        total_agents = self.db.query(Agent).count()
        inactive_agents = total_agents - active_agents

        # 檢查沒有 gold 或 food 的 agent
        starving_agents = (
            self.db.query(Agent)
            .filter(
                (Agent.gold < 10) | (Agent.food < 10)
            )
            .count()
        )

        return {
            "status": "healthy" if starving_agents == 0 else "warning",
            "total_agents": total_agents,
            "active_agents_7d": active_agents,
            "inactive_agents": inactive_agents,
            "starving_agents": starving_agents,
            "activity_rate": f"{(active_agents / total_agents * 100):.1f}%" if total_agents > 0 else "0%",
            "message": f"{active_agents}/{total_agents} agents active in 7 days",
        }

    def _check_battle_logs(self) -> dict:
        """檢查戰鬥記錄"""
        cutoff = utc_now() - timedelta(days=7)

        recent_battles = (
            self.db.query(BattleLog)
            .filter(BattleLog.created_at >= cutoff)
            .all()
        )

        if not recent_battles:
            return {
                "status": "healthy",
                "battle_count_7d": 0,
                "message": "No battles in last 7 days",
            }

        total = len(recent_battles)
        attacker_wins = sum(1 for b in recent_battles if b.outcome == "attacker_wins")
        defender_wins = sum(1 for b in recent_battles if b.outcome == "defender_wins")

        # 檢查是否失衡（某方勝率 > 70%）
        attacker_win_rate = attacker_wins / total if total > 0 else 0

        return {
            "status": "healthy" if 0.3 <= attacker_win_rate <= 0.7 else "warning",
            "battle_count_7d": total,
            "attacker_wins": attacker_wins,
            "defender_wins": defender_wins,
            "attacker_win_rate": f"{attacker_win_rate * 100:.1f}%",
            "message": f"Attackers win {attacker_win_rate * 100:.1f}% of battles",
        }

    async def _check_federation(self) -> dict:
        """檢查聯盟節點健康"""
        from ..models import FederationPeer

        peers = self.db.query(FederationPeer).all()

        if not peers:
            return {
                "status": "healthy",
                "peer_count": 0,
                "message": "No federation peers configured",
            }

        cutoff = utc_now() - timedelta(hours=1)
        active_peers = sum(1 for p in peers if p.last_seen_at >= cutoff)

        return {
            "status": "healthy" if active_peers == len(peers) else "warning",
            "total_peers": len(peers),
            "active_peers_1h": active_peers,
            "message": f"{active_peers}/{len(peers)} peers seen in last hour",
        }

    def _generate_recommendations(self, checks: dict) -> list[str]:
        """根據檢查結果生成建議"""
        recommendations = []

        if checks["database"]["status"] != "healthy":
            recommendations.append(
                f"🔴 Database issue: {checks['database'].get('message', 'Unknown error')}"
            )

        if checks["api_health"]["status"] != "healthy":
            recommendations.append(
                f"🟡 API issue: {checks['api_health'].get('message', 'Unknown error')}"
            )

        if checks["recent_errors"]["failed_events_24h"] > 10:
            recommendations.append(
                f"🟡 High error rate: {checks['recent_errors']['failed_events_24h']} failures in 24h"
            )

        if checks["agent_activity"]["starving_agents"] > 0:
            recommendations.append(
                f"🟡 {checks['agent_activity']['starving_agents']} agents are starving (low gold/food)"
            )

        if checks["battle_logs"]["status"] != "healthy":
            recommendations.append(
                f"🟡 Battle imbalance: {checks['battle_logs'].get('message', 'Check battle system')}"
            )

        if checks["federation_health"]["status"] != "healthy":
            recommendations.append(
                f"🟡 Federation issue: {checks['federation_health'].get('message', 'Check peer connections')}"
            )

        if not recommendations:
            recommendations.append("✅ All systems healthy")

        return recommendations


# ============================================================
# 2. Game Data Analyzer
# ============================================================

class GameDataAnalyzer:
    """
    分析遊戲數據，識別問題和機會
    """

    def __init__(self, db: Session):
        self.db = db

    def analyze(self) -> GameAnalysisResult:
        """
        執行完整的遊戲數據分析
        """
        balance_issues = self._analyze_balance()
        economy_issues = self._analyze_economy()
        engagement = self._analyze_engagement()
        suggestions = self._generate_suggestions(balance_issues, economy_issues, engagement)

        return GameAnalysisResult(
            balance_issues=balance_issues,
            economy_issues=economy_issues,
            engagement_metrics=engagement,
            suggestions=suggestions,
        )

    def _analyze_balance(self) -> list[dict]:
        """分析遊戲平衡問題"""
        issues = []

        # 檢查兵種分佈
        total_infantry = sum(a.infantry for a in self.db.query(Agent).all())
        total_archer = sum(a.archer for a in self.db.query(Agent).all())
        total_cavalry = sum(a.cavalry for a in self.db.query(Agent).all())
        total_troops = total_infantry + total_archer + total_cavalry

        if total_troops > 0:
            infantry_ratio = total_infantry / total_troops
            archer_ratio = total_archer / total_troops
            cavalry_ratio = total_cavalry / total_troops

            # 如果某兵種超過 60% 或低於 10%
            if infantry_ratio > 0.6:
                issues.append({
                    "type": "troop_imbalance",
                    "severity": "medium",
                    "detail": f"Infantry dominates ({infantry_ratio * 100:.1f}%), consider buffing cavalry/archer",
                    "data": {"infantry": infantry_ratio, "archer": archer_ratio, "cavalry": cavalry_ratio},
                })

        # 檢查角色分佈
        role_counts: dict[str, int] = {}
        for agent in self.db.query(Agent).all():
            role_counts[agent.role] = role_counts.get(agent.role, 0) + 1

        total_agents = len(role_counts)
        for role, count in role_counts.items():
            ratio = count / total_agents if total_agents > 0 else 0
            if ratio > 0.5:
                issues.append({
                    "type": "role_imbalance",
                    "severity": "medium",
                    "detail": f"Role '{role}' dominates ({ratio * 100:.1f}% of all agents)",
                    "data": role_counts,
                })

        # 檢查戰鬥勝率
        cutoff = utc_now() - timedelta(days=7)
        battles = self.db.query(BattleLog).filter(BattleLog.created_at >= cutoff).all()

        if len(battles) >= 10:
            attacker_wins = sum(1 for b in battles if b.outcome == "attacker_wins")
            win_rate = attacker_wins / len(battles)

            if win_rate > 0.7:
                issues.append({
                    "type": "combat_imbalance",
                    "severity": "high",
                    "detail": f"Attackers win {win_rate * 100:.1f}% of battles - defenders need buff",
                    "data": {"attacker_win_rate": win_rate, "total_battles": len(battles)},
                })
            elif win_rate < 0.3:
                issues.append({
                    "type": "combat_imbalance",
                    "severity": "high",
                    "detail": f"Defenders win {win_rate * 100:.1f}% of battles - attackers need buff",
                    "data": {"attacker_win_rate": win_rate, "total_battles": len(battles)},
                })

        return issues

    def _analyze_economy(self) -> list[dict]:
        """分析經濟系統"""
        issues = []

        agents = self.db.query(Agent).all()

        if not agents:
            return issues

        # 計算資源統計
        avg_gold = sum(a.gold for a in agents) / len(agents)
        avg_food = sum(a.food for a in agents) / len(agents)

        # 檢查資源分佈
        gold_std = self._std_dev([a.gold for a in agents])
        if gold_std > avg_gold * 2:
            issues.append({
                "type": "wealth_gap",
                "severity": "medium",
                "detail": "Large wealth gap between top and bottom agents",
                "data": {"avg_gold": avg_gold, "std_dev": gold_std},
            })

        # 檢查破產風險
        low_gold = sum(1 for a in agents if a.gold < 20)
        low_food = sum(1 for a in agents if a.food < 20)

        if low_gold > len(agents) * 0.3:
            issues.append({
                "type": "economic_stagnation",
                "severity": "high",
                "detail": f"{low_gold} agents ({low_gold / len(agents) * 100:.1f}%) have low gold",
                "data": {"low_gold_agents": low_gold, "total": len(agents)},
            })

        return issues

    def _analyze_engagement(self) -> dict:
        """分析玩家參與度"""
        cutoff_1d = utc_now() - timedelta(days=1)
        cutoff_7d = utc_now() - timedelta(days=7)
        cutoff_30d = utc_now() - timedelta(days=30)

        total_agents = self.db.query(Agent).count()

        active_1d = (
            self.db.query(Agent)
            .filter(Agent.updated_at >= cutoff_1d)
            .count()
        )

        active_7d = (
            self.db.query(Agent)
            .filter(Agent.updated_at >= cutoff_7d)
            .count()
        )

        active_30d = (
            self.db.query(Agent)
            .filter(Agent.updated_at >= cutoff_30d)
            .count()
        )

        # 計算每日平均動作數
        recent_actions = (
            self.db.query(ActionLog)
            .filter(ActionLog.created_at >= cutoff_7d)
            .count()
        )

        actions_per_day = recent_actions / 7

        return {
            "total_agents": total_agents,
            "active_1d": active_1d,
            "active_7d": active_7d,
            "active_30d": active_30d,
            "retention_1d": f"{active_1d / total_agents * 100:.1f}%" if total_agents > 0 else "0%",
            "retention_7d": f"{active_7d / total_agents * 100:.1f}%" if total_agents > 0 else "0%",
            "actions_per_day_7d": f"{actions_per_day:.1f}",
            "health": "good" if active_1d / total_agents > 0.5 else "warning" if active_1d / total_agents > 0.2 else "critical",
        }

    def _generate_suggestions(self, balance: list, economy: list, engagement: dict) -> list[str]:
        """根據分析生成建議"""
        suggestions = []

        # 基於平衡問題
        for issue in balance:
            if issue["type"] == "combat_imbalance":
                if "attacker" in issue["detail"].lower() and "high" in issue["severity"]:
                    suggestions.append(
                        "⚔️ 戰鬥失衡：建議增加城市防禦加成或降低攻擊方優勢"
                    )
            elif issue["type"] == "troop_imbalance":
                suggestions.append(
                    f"🏰 兵種失衡：{issue['detail']}"
                )
            elif issue["type"] == "role_imbalance":
                suggestions.append(
                    f"👤 角色失衡：{issue['detail']}"
                )

        # 基於經濟問題
        for issue in economy:
            if issue["type"] == "economic_stagnation":
                suggestions.append(
                    f"💰 經濟問題：{issue['detail']} - 建議增加低收入玩家的資源獲取途徑"
                )
            elif issue["type"] == "wealth_gap":
                suggestions.append(
                    f"📊 貧富差距：{issue['detail']} - 建議增加稅收重分配機制"
                )

        # 基於參與度
        health = engagement.get("health", "unknown")
        if health == "critical":
            suggestions.append(
                "📉 參與度危機：超過 80% 的玩家 24 小時內沒有活動，需要緊急改進新玩家體驗"
            )
        elif health == "warning":
            retention = float(engagement.get("retention_1d", "0%").rstrip("%"))
            if retention < 30:
                suggestions.append(
                    "📉 參與度下降：日留存率低於 30%，建議增加每日任務獎勵或縮短遊戲循環"
                )

        if not suggestions:
            suggestions.append("✅ 遊戲數據健康，無需特別建議")

        return suggestions

    @staticmethod
    def _std_dev(values: list[float]) -> float:
        """計算標準差"""
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5


# ============================================================
# 3. Feature Planner & PR Creator
# ============================================================

class FeaturePlanner:
    """
    根據分析結果規劃功能並生成 PR
    """

    SYSTEM_PROMPT = """你是 AI Three Kingdoms 的 AI 開發助手。

你的職責是根據每日健康檢查和遊戲數據分析結果，規劃和生成代碼改進。

## 約束條件：
1. 只生成 PR，不直接推送 main
2. 所有代碼必須有測試
3. 遵循現有的代碼風格
4. 保持簡潔，專注於一個功能

## 輸出格式：
生成一個完整的 PR，包含：
- 標題（中文）
- 描述
- 具體的代碼改動
- 測試代碼
"""

    def __init__(self, db: Session):
        self.db = db

    def plan(self, health: HealthCheckResult, analysis: GameAnalysisResult) -> list[FeaturePlan]:
        """
        根據檢查結果生成功能規劃
        """
        plans: list[FeaturePlan] = []

        # 1. 根據健康檢查生成修復計劃
        for rec in health.recommendations:
            if "🔴" in rec:  # Critical issue
                plans.append(self._create_fix_plan(rec))
            elif "🟡" in rec:  # Warning issue
                plans.append(self._create_improvement_plan(rec))

        # 2. 根據遊戲分析生成功能計劃
        for issue in analysis.balance_issues:
            if issue.get("severity") == "high":
                plans.append(self._create_balance_plan(issue))

        for issue in analysis.economy_issues:
            if issue.get("severity") == "high":
                plans.append(self._create_economy_plan(issue))

        # 3. 根據參與度生成優化
        if analysis.engagement_metrics.get("health") in ("warning", "critical"):
            plans.append(self._create_engagement_plan(analysis.engagement_metrics))

        # 按優先順序排序
        plans.sort(key=lambda p: p.priority)

        return plans[:5]  # 最多返回 5 個計劃

    def _create_fix_plan(self, recommendation: str) -> FeaturePlan:
        """為嚴重問題創建修復計劃"""
        return FeaturePlan(
            title=f"修復：{recommendation}",
            description=f"根據每日健康檢查發現的問題：{recommendation}",
            priority=1,
            category="bug_fix",
            files_to_change=["backend/app/services/daily_reset.py"],
            code_template=self._get_fix_template(recommendation),
            test_template=self._get_test_template(),
            estimated_impact="修復系統穩定性問題",
        )

    def _create_improvement_plan(self, recommendation: str) -> FeaturePlan:
        """為警告問題創建改進計劃"""
        return FeaturePlan(
            title=f"優化：{recommendation}",
            description=f"根據每日健康檢查發現的優化點：{recommendation}",
            priority=2,
            category="optimization",
            files_to_change=["backend/app/services/daily_reset.py"],
            code_template=self._get_optimization_template(recommendation),
            test_template=self._get_test_template(),
            estimated_impact="提升系統性能和穩定性",
        )

    def _create_balance_plan(self, issue: dict) -> FeaturePlan:
        """為平衡問題創建調整計劃"""
        issue_type = issue.get("type", "unknown")

        if issue_type == "combat_imbalance":
            return FeaturePlan(
                title="戰鬥系統平衡調整",
                description=f"問題：{issue.get('detail', 'Unknown')}",
                priority=1,
                category="balance",
                files_to_change=[
                    "backend/app/services/combat.py",
                    "backend/app/rules.py",
                ],
                code_template=self._get_combat_balance_template(issue),
                test_template=self._get_combat_test_template(),
                estimated_impact="改善戰鬥勝率，使其更公平",
            )
        elif issue_type == "troop_imbalance":
            return FeaturePlan(
                title="兵種強度調整",
                description=f"問題：{issue.get('detail', 'Unknown')}",
                priority=2,
                category="balance",
                files_to_change=["backend/app/rules.py"],
                code_template=self._get_troop_balance_template(issue),
                test_template=self._get_test_template(),
                estimated_impact="增加兵種多樣性",
            )

        return self._default_plan(issue)

    def _create_economy_plan(self, issue: dict) -> FeaturePlan:
        """為經濟問題創建調整計劃"""
        return FeaturePlan(
            title="經濟系統調整",
            description=f"問題：{issue.get('detail', 'Unknown')}",
            priority=1,
            category="balance",
            files_to_change=[
                "backend/app/services/daily_reset.py",
                "backend/app/rules.py",
            ],
            code_template=self._get_economy_template(issue),
            test_template=self._get_test_template(),
            estimated_impact="改善經濟平衡，減少玩家流失",
        )

    def _create_engagement_plan(self, metrics: dict) -> FeaturePlan:
        """為參與度問題創建計劃"""
        return FeaturePlan(
            title="玩家參與度優化",
            description=f"日留存率：{metrics.get('retention_1d', 'N/A')}，需要改善玩家體驗",
            priority=1,
            category="feature",
            files_to_change=[
                "backend/app/services/daily_reset.py",
                "backend/app/rules.py",
            ],
            code_template=self._get_engagement_template(metrics),
            test_template=self._get_test_template(),
            estimated_impact="提升玩家留存和活躍度",
        )

    def _default_plan(self, issue: dict) -> FeaturePlan:
        """默認計劃工廠"""
        return FeaturePlan(
            title=f"優化：{issue.get('type', 'unknown')}",
            description=issue.get("detail", ""),
            priority=3,
            category="optimization",
            files_to_change=["backend/app/services/daily_reset.py"],
            code_template="# 需要進一步分析",
            test_template="# 需要進一步分析",
            estimated_impact="待評估",
        )

    def generate_pr_description(self, plan: FeaturePlan) -> str:
        """生成 PR 描述"""
        return f"""## {plan.title}

### 問題描述
{plan.description}

### 變更範圍
- 文件：{', '.join(plan.files_to_change)}
- 類別：{plan.category}
- 優先級：{'高' if plan.priority == 1 else '中' if plan.priority == 2 else '低'}

### 預期影響
{plan.estimated_impact}

### 代碼變更

```python
{plan.code_template}
```

### 測試

```python
{plan.test_template}
```

---
_此 PR 由 AI DevOps Agent 自動生成，請人工審核後合併。_
"""

    # ==================== 代碼模板 ====================

    @staticmethod
    def _get_fix_template(issue: str) -> str:
        """生成修復代碼模板"""
        if "database" in issue.lower():
            return '''
# Database fix
def fix_orphan_agents(db: Session) -> int:
    """修復孤兒代理（沒有 owner 的代理）"""
    orphan_agents = (
        db.query(Agent)
        .filter(Agent.owner_user_id.is_(None))
        .all()
    )
    for agent in orphan_agents:
        # 將孤兒代理分配給系統管理員
        admin = db.query(User).filter(User.is_admin == True).first()
        if admin:
            agent.owner_user_id = admin.id
            db.add(agent)
    db.commit()
    return len(orphan_agents)
'''
        return '''
# System fix
def apply_system_fix(db: Session) -> dict:
    """應用系統修復"""
    # TODO: Implement specific fix based on issue
    pass
'''

    @staticmethod
    def _get_optimization_template(issue: str) -> str:
        """生成優化代碼模板"""
        return '''
# Performance optimization
def optimize_daily_reset(db: Session) -> dict:
    """
    優化每日重置邏輯，減少資料庫查詢次數
    """
    agents = db.query(Agent).all()

    # 使用 bulk 更新而不是逐個更新
    agent_ids = [a.id for a in agents]
    for agent_id in agent_ids:
        agent = db.query(Agent).get(agent_id)
        if agent:
            agent.energy = 100  # 重置能量
            agent.food = max(0, agent.food - 10)  # 基礎消耗
            db.add(agent)

    db.commit()
    return {"updated": len(agent_ids)}
'''

    @staticmethod
    def _get_combat_balance_template(issue: dict) -> str:
        """生成戰鬥平衡模板"""
        data = issue.get("data", {})
        current_rate = data.get("attacker_win_rate", 0.5)

        # 根據當前勝率計算調整
        if current_rate > 0.5:
            defense_bonus = 1.1
            attack_penalty = 0.95
        else:
            defense_bonus = 0.9
            attack_penalty = 1.05

        return f'''
# Combat balance adjustment
# Current attacker win rate: {current_rate * 100:.1f}%

COMBAT_DEFENSE_BONUS = {defense_bonus}  # 城市防禦加成
COMBAT_ATTACK_PENALTY = {attack_penalty}  # 攻擊方懲罰

def calculate_battle_result(attacker_power: float, defender_power: float, is_city_defense: bool) -> dict:
    """
    計算戰鬥結果，平衡攻守雙方
    """
    final_attacker = attacker_power * COMBAT_ATTACK_PENALTY
    final_defender = defender_power * COMBAT_DEFENSE_BONUS if is_city_defense else defender_power

    # 勝利機率基於最終力量對比
    total_power = final_attacker + final_defender
    win_probability = final_attacker / total_power if total_power > 0 else 0.5

    return {{
        "attacker_power": final_attacker,
        "defender_power": final_defender,
        "attacker_win_probability": win_probability,
    }}
'''

    @staticmethod
    def _get_troop_balance_template(issue: dict) -> str:
        """生成兵種平衡模板"""
        return '''
# Troop balance adjustment
# Increase non-dominant troop effectiveness

TROOP_BALANCE_FACTORS = {
    "infantry": 1.0,      # 保持不變
    "archer": 1.15,       # 輕步兵加成 15%
    "cavalry": 1.20,      # 騎兵加成 20%
}

def calculate_troop_power(base_power: float, troop_type: str) -> float:
    """
    根據兵種計算實際戰力，平衡兵種使用
    """
    factor = TROOP_BALANCE_FACTORS.get(troop_type, 1.0)
    return base_power * factor
'''

    @staticmethod
    def _get_economy_template(issue: dict) -> str:
        """生成經濟平衡模板"""
        return '''
# Economy adjustment - Help low-gold agents
DAILY_STARTER_GOLD = 10   # 每天最低保障金
DAILY_STARTER_FOOD = 15   # 每天最低保障食物

def daily_reset_with_economy_support(db: Session) -> dict:
    """
    每日重置，並為低資源玩家提供保障
    """
    agents = db.query(Agent).all()
    supported = 0

    for agent in agents:
        # 基礎重置
        agent.energy = 100

        # 資源消耗
        food_cost = 10
        agent.food = max(0, agent.food - food_cost)

        # 低資源玩家保障
        if agent.gold < 20:
            agent.gold += DAILY_STARTER_GOLD
            supported += 1

        if agent.food < 10:
            agent.food += DAILY_STARTER_FOOD
            supported += 1

        db.add(agent)

    db.commit()
    return {"agents_reset": len(agents), "supported": supported}
'''

    @staticmethod
    def _get_engagement_template(metrics: dict) -> str:
        """生成參與度優化模板"""
        return '''
# Player engagement optimization
DAILY_LOGIN_BONUS = {
    "gold": 20,
    "food": 30,
    "energy": 20,
}

QUEST_COMPLETION_BONUS = {
    "gold": 50,
    "food": 100,
    "reputation": 10,
}

def apply_engagement_bonus(db: Session, agent_id: int, action_type: str) -> dict:
    """
    根據玩家行為發放獎勵，增加參與度
    """
    agent = db.query(Agent).get(agent_id)
    if not agent:
        return {"success": False, "message": "Agent not found"}

    if action_type == "daily_login":
        agent.gold += DAILY_LOGIN_BONUS["gold"]
        agent.food += DAILY_LOGIN_BONUS["food"]
        agent.energy = min(150, agent.energy + DAILY_LOGIN_BONUS["energy"])
        message = "Daily login bonus applied"

    elif action_type == "quest_completed":
        agent.gold += QUEST_COMPLETION_BONUS["gold"]
        agent.food += QUEST_COMPLETION_BONUS["food"]
        agent.reputation += QUEST_COMPLETION_BONUS["reputation"]
        message = "Quest completion bonus applied"

    else:
        return {"success": False, "message": "Unknown action type"}

    db.add(agent)
    db.commit()

    return {
        "success": True,
        "message": message,
        "agent_id": agent_id,
    }
'''

    @staticmethod
    def _get_test_template() -> str:
        """生成測試模板"""
        return '''
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, Agent, User
from app.services.ai_devops import SystemHealthMonitor, GameDataAnalyzer

@pytest.fixture
def db_session():
    """創建測試資料庫"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # 創建測試用戶和代理
    user = User(username="test", email="test@test.com", password_hash="hash")
    session.add(user)
    session.commit()

    agent = Agent(
        name="TestAgent",
        role="warrior",
        home_city="Luoyang",
        current_city="Luoyang",
        owner_user_id=user.id,
        gold=100,
        food=100,
    )
    session.add(agent)
    session.commit()

    yield session
    session.close()

def test_health_check(db_session):
    """測試健康檢查"""
    monitor = SystemHealthMonitor(db_session)
    result = monitor.check_all()
    assert result.status in ["healthy", "warning", "critical"]

def test_game_analysis(db_session):
    """測試遊戲數據分析"""
    analyzer = GameDataAnalyzer(db_session)
    result = analyzer.analyze()
    assert result.engagement_metrics["total_agents"] >= 1
'''

    @staticmethod
    def _get_combat_test_template() -> str:
        """生成戰鬥測試模板"""
        return '''
import pytest
from app.services.ai_devops import FeaturePlanner

def test_combat_balance_calculation():
    """測試戰鬥平衡計算"""
    # 測試相同實力時，攻守雙方勝率接近 50%
    # ... implement test based on new combat logic
    pass

def test_troop_diversity():
    """測試兵種多樣性"""
    # 測試不同兵種組合的戰力計算
    pass
'''


# ============================================================
# 4. Main Orchestrator
# ============================================================

class AIDevOpsOrchestrator:
    """
    AI DevOps 主協調器，整合所有模組
    """

    def __init__(self, db: Session):
        self.db = db
        self.health_monitor = SystemHealthMonitor(db)
        self.game_analyzer = GameDataAnalyzer(db)
        self.feature_planner = FeaturePlanner(db)

    async def run_daily_check(self) -> dict:
        """
        執行完整的每日檢查
        """
        report_id = f"report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        # 1. 健康檢查
        health = await self.health_monitor.check_all()

        # 2. 遊戲數據分析
        analysis = self.game_analyzer.analyze()

        # 3. 功能規劃
        plans = self.feature_planner.plan(health, analysis)

        # 生成 PR 描述
        pr_descriptions = []
        for plan in plans:
            pr_descriptions.append({
                "title": plan.title,
                "description": self.feature_planner.generate_pr_description(plan),
                "priority": plan.priority,
                "category": plan.category,
                "files": plan.files_to_change,
            })

        # 構建完整報告
        report = {
            "report_id": report_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "health": {
                "status": health.status.value,
                "checks": health.checks,
                "recommendations": health.recommendations,
            },
            "game_analysis": {
                "balance_issues": analysis.balance_issues,
                "economy_issues": analysis.economy_issues,
                "engagement": analysis.engagement_metrics,
                "suggestions": analysis.suggestions,
            },
            "planned_features": pr_descriptions,
            "summary": self._generate_summary(health, analysis, len(plans)),
        }

        # 保存報告到 system_state
        self._save_report(report_id, report)

        return report

    def _save_report(self, report_id: str, report: dict) -> None:
        """保存報告"""
        # 保存最新報告 ID
        set_state(self.db, "latest_devops_report_id", report_id)

        # 保存報告內容（壓縮存儲）
        report_json = json.dumps(report, ensure_ascii=False, default=str)
        # 限制大小
        if len(report_json) > 10000:
            report_json = report_json[:10000] + "... (truncated)"
        set_state(self.db, f"devops_report_{report_id}", report_json)
        self.db.commit()

    def _generate_summary(self, health, analysis, plan_count: int) -> str:
        """生成摘要"""
        summary_parts = []

        # 健康狀態
        if health.status.value == "critical":
            summary_parts.append(f"🔴 系統狀態：危險 ({len([r for r in health.recommendations if '🔴' in r])} 個嚴重問題)")
        elif health.status.value == "warning":
            summary_parts.append(f"🟡 系統狀態：警告 ({len([r for r in health.recommendations if '🟡' in r])} 個警告)")
        else:
            summary_parts.append("✅ 系統狀態：正常")

        # 遊戲分析
        if analysis.balance_issues:
            summary_parts.append(f"⚔️ 平衡問題：{len(analysis.balance_issues)} 個")
        if analysis.economy_issues:
            summary_parts.append(f"💰 經濟問題：{len(analysis.economy_issues)} 個")

        # 參與度
        engagement = analysis.engagement_metrics
        summary_parts.append(f"📊 日活躍：{engagement.get('retention_1d', 'N/A')}")

        # 計劃數量
        summary_parts.append(f"📋 功能計劃：{plan_count} 個")

        return " | ".join(summary_parts)


# ============================================================
# 5. Public API Functions
# ============================================================

async def run_ai_devops_daily(db: Session) -> dict:
    """
    執行每日 AI DevOps 檢查
    """
    orchestrator = AIDevOpsOrchestrator(db)
    return await orchestrator.run_daily_check()


def get_latest_devops_report(db: Session) -> dict | None:
    """
    獲取最新的 DevOps 報告
    """
    report_id = get_state(db, "latest_devops_report_id", default="")
    if not report_id:
        return None

    report_json = get_state(db, f"devops_report_{report_id}", default="")
    if not report_json:
        return None

    try:
        return json.loads(report_json)
    except json.JSONDecodeError:
        return None
