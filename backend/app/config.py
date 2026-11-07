from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Three Kingdoms City Node"
    app_version: str = "1.29.0"
    database_url: str = "sqlite:///./ai_three_kingdoms.db"
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_exp_minutes: int = 15
    refresh_token_exp_days: int = 30
    world_name: str = "Three Kingdoms Autonomous World"
    city_name: str = "洛阳"
    city_base_url: str = "http://localhost:8000"
    city_location: str = "Unknown"
    city_wall: int = 300
    city_tax_rate: float = 0.05
    open_for_migration: bool = True

    protocol_version: str = "1.0"
    rule_version: str = "1.0"
    federation_shared_secret: str = "federation-dev-secret"
    central_registry_url: str = ""
    central_registry_token: str = ""
    central_roles_policy_url: str = ""
    central_heartbeat_url: str = ""
    central_node_id: str = ""
    central_roles_policy_required: bool = False
    federation_request_ttl_sec: int = 300
    auto_create_schema: bool = True
    admin_usernames: str = ""
    password_reset_code_ttl_minutes: int = 15
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    # 465 用 implicit TLS；587 用 STARTTLS（smtp_use_tls）。兩者不要同時開。
    smtp_use_ssl: bool = False
    smtp_timeout_sec: int = 10

    # -- Blockchain / Chain Abstraction Layer --
    chain_provider: str = "hyperledger"
    chain_base_url: str = "https://chain.onlyoneledger.com/api"
    chain_api_token: str = ""
    chain_id: str = "hyperledger-fabric-1"

    # -- Public docs --
    # 公開文件（skill.md / api.md / combat.md / reference.md）給外部 Agent 看，
    # 必須用公網網址；city_base_url 是節點內部位址（federation / health check 用），
    # 不能混用。留空時沿用 public_site_url。
    public_site_url: str = "https://app.ai-3kingdom.xyz"
    public_doc_base_url: str = ""

    # -- Daily chronicle narrative layer --
    # 對話屬 Agent 私人往來，預設不寫入公開史記；營運者可明確開啟。
    chronicle_include_dialogue: bool = False
    # 選配：設定後才會用 LLM 潤飾史記；未設定時使用確定性模板，完全不需外部服務。
    chronicle_llm_endpoint: str = ""
    chronicle_llm_api_key: str = ""
    chronicle_llm_model: str = ""

    # -- World events (稀缺 / 期限 / 不可逆) --
    # Python 預設關閉，讓本機開發與 CI 不會意外產生事件；
    # production 由 docker-compose.server.yml 傳入 WORLD_EVENTS_ENABLED=true。
    # 可用環境變數 WORLD_EVENTS_ENABLED=false 隨時覆寫關閉。
    world_events_enabled: bool = False
    world_events_deadline_hours: int = 72
    world_events_famine_threshold: int = 0
    world_events_famine_relief_target: int = 500
    world_events_betrayal_penalty: int = 30
    world_events_famine_wall_penalty: int = 50

    # -- Daily share card / content flywheel --
    # 每日 08:00 HKT 自動產出史記圖卡與發文包；不需任何憑證就能跑。
    # X／Threads／小紅書沒有平台憑證，預設只「備好文案＋圖卡」，由人工貼文；
    # 填入 CHRONICLE_CARD_WEBHOOK_URLS 後才會自動 POST（可接 n8n/Make/IFTTT 轉發）。
    chronicle_card_enabled: bool = True
    chronicle_card_publish_hour_hkt: int = 8
    chronicle_card_api_prefix: str = "/api"
    chronicle_card_webhook_urls: str = ""
    chronicle_card_webhook_type: str = "generic"  # generic | discord

    # -- Daily arena exhibition --
    # NPC 守軍主動挑釁的表演賽：不改 agent 狀態，只為觀戰世界每天備一場可回放的戲。
    # Python 預設關閉（本機／CI 不製造資料），production compose 預設啟用；
    # ARENA_HOUR_HKT 趕在 08:00 發文包之前，發出去的文案才帶得到戰報。
    arena_enabled: bool = False
    arena_hour_hkt: int = 7

    # -- 14-day seasons (開季詔書 / 霸主積分 / 季末本紀 / 結局卡) --
    # 賽季是只讀的排行榜與敘事層：不改 agent 數值、不替 agent 做決策、不新增資料表。
    # Python 預設關閉（本機／CI 不製造資料），production compose 預設啟用。
    season_enabled: bool = False
    season_length_days: int = 14

    # -- Audience participation (免登入助威 / 押陣) --
    # 真人觀眾每天可助威一位諸侯、押一次 07:00 演武的勝方。
    # 士氣只影響 NPC 表演賽，不改 agent 數值、不進霸主積分、不替 agent 決策。
    # Python 預設關閉（本機／CI 不製造資料），production compose 預設啟用。
    audience_enabled: bool = False
    audience_max_boost: float = 0.12
    audience_min_votes: int = 3

    # -- Market / famine relief --
    # 商城本身永遠可用；這個值只控制「每日重置後，低於底線的 agent 自動補到
    # 底線」的固定保底。0 = 停用（預設，保留糧荒的張力）；要每天保底可設 40~60。
    market_relief_floor: int = 0

    # 饑荒自動止血：只有「大多數諸侯連明日基本口糧都付不起」才開倉一次。
    # 觸發線 = DAILY_AGENT_FOOD_CONSUMPTION(10)，補給目標 = market_famine_relief_floor(60)；
    # 兩者分開，補完隔日扣糧不會又達標（否則等於天天白送、商城被架空）。
    # 這是全城 food=0（誰也買不起第一袋糧）的處方；每天檢查一次，system_state 冪等。
    # Python 預設關閉（本機／CI 不製造資料），production compose 預設啟用。
    market_famine_relief_enabled: bool = False
    market_famine_relief_floor: int = 60
    market_famine_starving_ratio: float = 0.8
    market_famine_min_agents: int = 3

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
