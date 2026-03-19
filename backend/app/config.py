from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Three Kingdoms City Node"
    app_version: str = "1.25.1"
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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
