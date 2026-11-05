from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Three Kingdoms City Node"
    app_version: str = "1.27.0"
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

    # -- Blockchain / Chain Abstraction Layer --
    chain_provider: str = "hyperledger"
    chain_base_url: str = "https://chain.onlyoneledger.com/api"
    chain_api_token: str = ""
    chain_id: str = "hyperledger-fabric-1"

    # -- Daily chronicle narrative layer --
    # 對話屬 Agent 私人往來，預設不寫入公開史記；營運者可明確開啟。
    chronicle_include_dialogue: bool = False
    public_site_url: str = "https://app.ai-3kingdom.xyz"
    # 選配：設定後才會用 LLM 潤飾史記；未設定時使用確定性模板，完全不需外部服務。
    chronicle_llm_endpoint: str = ""
    chronicle_llm_api_key: str = ""
    chronicle_llm_model: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
