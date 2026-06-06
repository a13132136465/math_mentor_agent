from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False
    log_level: str = "INFO"

    # ── Security ───────────────────────────────────────────────
    jwt_secret: str = "insecure-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 days

    # ── Google Cloud ───────────────────────────────────────────
    gcp_project: str = "mathmentor-dev"
    gcp_region: str = "us-central1"

    # ── Vertex AI ──────────────────────────────────────────────
    vertex_location: str = "us-central1"
    gemini_model_pro: str = "gemini-2.5-pro-preview-05-06"
    gemini_model_flash: str = "gemini-2.5-flash-preview-05-20"
    vertex_timeout_pro: float = 30.0
    vertex_timeout_flash: float = 10.0

    # Retry config
    vertex_max_retries: int = 3
    vertex_retry_min_wait: float = 1.0
    vertex_retry_max_wait: float = 8.0

    # Generation defaults
    gemini_temperature_pro: float = 0.2
    gemini_temperature_flash: float = 0.4
    gemini_max_output_tokens: int = 2048

    # Leak-check fast call
    vertex_timeout_leak_check: float = 3.0

    # ── DeepSeek ─────────────────────────────────────────────
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model_pro: str = "deepseek-reasoner"
    deepseek_model_flash: str = "deepseek-chat"
    deepseek_timeout_pro: float = 60.0
    deepseek_timeout_flash: float = 30.0
    deepseek_temperature_pro: float = 0.2
    deepseek_temperature_flash: float = 0.4

    # ── MongoDB ────────────────────────────────────────────────
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "mathmentor"
    mongodb_max_pool_size: int = 50
    mongodb_min_pool_size: int = 5
    mongodb_server_selection_timeout_ms: int = 5000
    mongodb_connect_timeout_ms: int = 3000
    mongodb_socket_timeout_ms: int = 10000

    # ── CORS ───────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000"

    # ── Google OAuth ───────────────────────────────────────────
    google_client_id: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str) -> str:
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
