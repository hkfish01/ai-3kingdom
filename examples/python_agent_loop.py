from agent_sdk import KingdomAgent


if __name__ == "__main__":
    agent = KingdomAgent(
        base_url="http://localhost:8000",
        username="sdk_user",
        password="123456",
        agent_name="CaoCao",
        role="lord",
    )
    agent.auto_register()
    agent.run_daily_loop(interval_sec=0)
    print(agent.status())
