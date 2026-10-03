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
    openai_model: str = "gpt-5.6-sol"
    # gpt-5.6-sol is a reasoning-tier model: `max_output_tokens` is shared
    # between its internal reasoning and the final visible message, and
    # real draft prompts (full Manual Maestro-style instructions +
    # code_interpreter reading a real file) measured ~2.5-3k reasoning
    # tokens alone — 1000 silently produced an empty, "incomplete" response
    # with no error. 8000 leaves real headroom; it's a ceiling, not a
    # consumption target, so it doesn't by itself raise cost.
    llm_max_tokens: int = 8000

    # Langfuse
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Mail worker
    mail_poll_interval_seconds: int = 60
    max_emails_per_run: int = 20
    max_retry_attempts: int = 3

    # Documents / knowledge files — real files uploaded to OpenAI's Files API
    # and attached to generation calls via the code_interpreter tool (see
    # llm_service.py / processing_service.py), not text-extracted locally.
    documents_storage_path: str = "/app/storage/documents"
    max_upload_file_bytes: int = 512 * 1024 * 1024  # OpenAI Files API hard cap
    max_knowledge_files_per_call: int = 20
    max_knowledge_file_total_bytes: int = 200 * 1024 * 1024

    # Drive sync (one file per DriveSource, polled by content hash)
    drive_poll_interval_seconds: int = 60

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
