"""Central application configuration, loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # General
    app_name: str = "Walli"
    environment: str = "local"
    backend_port: int = 8000
    frontend_port: int = 5173
    log_level: str = "INFO"

    # CORS
    cors_allowed_origins: str = "http://localhost:5173"

    # Database
    database_url: str = "postgresql+psycopg://walli:walli@localhost:5432/walli"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Auth
    jwt_secret_key: str = "insecure-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # Encryption
    encryption_key: str = ""

    # LLM
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-mini"
    llm_temperature: float = 0
    llm_max_tokens: int = 1000

    # Langfuse
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Mail worker
    mail_poll_interval_seconds: int = 60
    max_emails_per_run: int = 20
    max_retry_attempts: int = 3

    # Documents
    documents_storage_path: str = "/app/storage/documents"
    max_knowledge_context_chars: int = 600000

    # Agent images (inline images the agent can attach, e.g. a price table)
    # — a kill switch so the feature can be disabled instantly via env var
    # if the structured-output draft generation misbehaves in production,
    # without a code revert/redeploy under pressure.
    enable_agent_image_embedding: bool = True

    # Web sources (website knowledge ingestion)
    web_source_poll_interval_seconds: int = 86400

    # Initial admin seed
    initial_admin_email: str = "admin@lawall.local"
    initial_admin_password: str = "change-me-please"
    initial_admin_full_name: str = "Walli Admin"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
