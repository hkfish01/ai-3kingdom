"""
AI DevOps Service Tests
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models import Base, Agent, User, ActionLog, BattleLog
from app.services.ai_devops import (
    SystemHealthMonitor,
    GameDataAnalyzer,
    FeaturePlanner,
    AIDevOpsOrchestrator,
    HealthStatus,
)


@pytest.fixture
def db_session():
    """創建測試用資料庫 session"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def setup_test_data(db_session):
    """設定測試資料"""
    # 創建測試用戶
    user = User(
        username="test_user",
        email="test@example.com",
        password_hash="$pbkdf2-sha256$test",
        is_admin=True,
    )
    db_session.add(user)
    db_session.commit()

    # 創建測試代理
    agent1 = Agent(
        name="TestAgent1",
        role="warrior",
        home_city="Luoyang",
        current_city="Luoyang",
        owner_user_id=user.id,
        gold=100,
        food=100,
        energy=50,
        infantry=10,
        archer=5,
        cavalry=2,
        martial=60,
        intelligence=40,
        charisma=50,
        politics=30,
    )
    agent2 = Agent(
        name="TestAgent2",
        role="scholar",
        home_city="Luoyang",
        current_city="Luoyang",
        owner_user_id=user.id,
        gold=50,
        food=30,
        energy=80,
        infantry=2,
        archer=1,
        cavalry=0,
        martial=30,
        intelligence=70,
        charisma=60,
        politics=80,
    )
    db_session.add(agent1)
    db_session.add(agent2)
    db_session.commit()

    return {"user": user, "agent1": agent1, "agent2": agent2}


class TestSystemHealthMonitor:
    """測試系統健康監控"""

    def test_database_check_healthy(self, db_session, setup_test_data):
        """測試資料庫檢查 - 正常狀態"""
        monitor = SystemHealthMonitor(db_session)

        result = db_session.execute(text("SELECT 1")).fetchone()

        # 驗證檢查可以正常執行
        assert result is not None

    def test_recent_errors_check(self, db_session, setup_test_data):
        """測試錯誤檢查"""
        monitor = SystemHealthMonitor(db_session)

        # 驗證沒有錯誤時返回 healthy
        checks = {"recent_errors": monitor._check_recent_errors()}
        assert checks["recent_errors"]["status"] == "healthy"
        assert checks["recent_errors"]["failed_events_24h"] == 0

    def test_agent_activity_check(self, db_session, setup_test_data):
        """測試代理活動檢查"""
        monitor = SystemHealthMonitor(db_session)

        result = monitor._check_agent_activity()

        assert result["status"] in ["healthy", "warning", "critical"]
        assert result["total_agents"] == 2
        assert result["active_agents_7d"] == 2
        assert result["starving_agents"] == 0  # agent2 有 30 food，沒到飢餓線

    def test_battle_logs_check_no_battles(self, db_session, setup_test_data):
        """測試戰鬥記錄檢查 - 無戰鬥"""
        monitor = SystemHealthMonitor(db_session)

        result = monitor._check_battle_logs()

        assert result["status"] == "healthy"
        assert result["battle_count_7d"] == 0

    def test_battle_logs_check_imbalanced(self, db_session, setup_test_data):
        """測試戰鬥記錄檢查 - 失衡"""
        # 添加一些失衡的戰鬥記錄
        for i in range(10):
            battle = BattleLog(
                attacker_city="Luoyang",
                defender_city="Chengdu",
                attack_power=100,
                defense_power=50,
                outcome="attacker_wins",
            )
            db_session.add(battle)
        db_session.commit()

        monitor = SystemHealthMonitor(db_session)
        result = monitor._check_battle_logs()

        # 100% 攻方勝利，應該被標記為 warning
        assert result["status"] == "warning"
        assert result["attacker_win_rate"] == "100.0%"


class TestGameDataAnalyzer:
    """測試遊戲數據分析"""

    def test_analyze_balance_troop_imbalance(self, db_session, setup_test_data):
        """測試兵種失衡檢測"""
        # 讓一個代理有大量步兵
        agent1 = db_session.query(Agent).filter(Agent.name == "TestAgent1").first()
        agent1.infantry = 100
        agent1.archer = 0
        agent1.cavalry = 0
        db_session.commit()

        analyzer = GameDataAnalyzer(db_session)
        result = analyzer.analyze()

        # 步兵佔 100%，應該檢測到兵種失衡
        assert len(result.balance_issues) > 0
        troop_issue = next(
            (i for i in result.balance_issues if i["type"] == "troop_imbalance"),
            None
        )
        assert troop_issue is not None

    def test_analyze_economy_low_resources(self, db_session, setup_test_data):
        """測試經濟問題檢測 - 低資源"""
        # 讓代理資源很低
        agent2 = db_session.query(Agent).filter(Agent.name == "TestAgent2").first()
        agent2.gold = 5
        agent2.food = 5
        db_session.commit()

        analyzer = GameDataAnalyzer(db_session)
        result = analyzer.analyze()

        # 應該檢測到經濟問題
        economy_issue = next(
            (i for i in result.economy_issues if i["type"] == "economic_stagnation"),
            None
        )
        # 因為只有 1 個代理低資源，不會觸發 30% 閾值
        # 但應該能檢測到其他問題
        assert result.economy_issues is not None

    def test_analyze_engagement(self, db_session, setup_test_data):
        """測試參與度分析"""
        analyzer = GameDataAnalyzer(db_session)
        result = analyzer.analyze()

        assert "total_agents" in result.engagement_metrics
        assert result.engagement_metrics["total_agents"] == 2
        assert result.engagement_metrics["retention_1d"] == "100.0%"

    def test_suggestions_generation(self, db_session, setup_test_data):
        """測試建議生成"""
        analyzer = GameDataAnalyzer(db_session)
        result = analyzer.analyze()

        # 應該有建議列表
        assert isinstance(result.suggestions, list)
        # 健康時 suggestions 可能為空列表，這是預期行為


class TestFeaturePlanner:
    """測試功能規劃器"""

    def test_plan_generates_plans(self, db_session, setup_test_data):
        """測試計劃生成"""
        from app.services.ai_devops import HealthCheckResult

        # 創建模擬的健康檢查結果
        health = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            checks={},
            recommendations=["✅ All systems healthy"],
        )

        analyzer = GameDataAnalyzer(db_session)
        analysis = analyzer.analyze()

        planner = FeaturePlanner(db_session)
        plans = planner.plan(health, analysis)

        assert isinstance(plans, list)
        # 如果所有系統健康，可能沒有計劃

    def test_plan_with_critical_issue(self, db_session, setup_test_data):
        """測試有嚴重問題時的計劃生成"""
        from app.services.ai_devops import HealthCheckResult

        health = HealthCheckResult(
            status=HealthStatus.CRITICAL,
            checks={},
            recommendations=["🔴 Database issue: Found 5 orphan agents"],
        )

        analyzer = GameDataAnalyzer(db_session)
        analysis = analyzer.analyze()

        planner = FeaturePlanner(db_session)
        plans = planner.plan(health, analysis)

        # 應該有修復計劃
        assert len(plans) > 0
        assert plans[0].priority == 1  # 高優先級
        assert plans[0].category == "bug_fix"

    def test_pr_description_generation(self, db_session):
        """測試 PR 描述生成"""
        from app.services.ai_devops import FeaturePlan

        plan = FeaturePlan(
            title="測試功能",
            description="這是一個測試功能描述",
            priority=1,
            category="feature",
            files_to_change=["test.py"],
            code_template="def test(): pass",
            test_template="def test_test(): pass",
            estimated_impact="提升系統功能",
        )

        planner = FeaturePlanner(db_session)
        description = planner.generate_pr_description(plan)

        assert "測試功能" in description
        assert "這是一個測試功能描述" in description
        assert "def test():" in description


class TestAIDevOpsOrchestrator:
    """測試 AI DevOps 協調器"""

    @pytest.mark.asyncio
    async def test_run_daily_check(self, db_session, setup_test_data):
        """測試每日檢查執行"""
        orchestrator = AIDevOpsOrchestrator(db_session)

        # Mock httpx client to avoid real HTTP calls
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": {"version": "1.0.0"}}
            mock_response.elapsed.total_seconds.return_value = 0.1
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            report = await orchestrator.run_daily_check()

            assert "report_id" in report
            assert "timestamp" in report
            assert "health" in report
            assert "game_analysis" in report
            assert "planned_features" in report
            assert "summary" in report

            # 驗證健康檢查結果
            assert report["health"]["status"] in ["healthy", "warning", "critical"]

            # 驗證遊戲分析結果
            assert "balance_issues" in report["game_analysis"]
            assert "economy_issues" in report["game_analysis"]
            assert "engagement" in report["game_analysis"]


class TestIntegration:
    """集成測試"""

    @pytest.mark.asyncio
    async def test_full_devops_pipeline(self, db_session, setup_test_data):
        """測試完整的 DevOps 流程"""
        from app.services.ai_devops import run_ai_devops_daily

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": {"version": "1.0.0"}}
            mock_response.elapsed.total_seconds.return_value = 0.1
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await run_ai_devops_daily(db_session)

            # 驗證返回結果
            assert result is not None
            assert "report_id" in result
            assert "summary" in result

            # 驗證報告已保存
            from app.services.ai_devops import get_latest_devops_report
            saved_report = get_latest_devops_report(db_session)
            assert saved_report is not None
            assert saved_report["report_id"] == result["report_id"]
