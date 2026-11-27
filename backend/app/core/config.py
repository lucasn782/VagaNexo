from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "VagaNexo AI"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: list[str] = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ]

    database_url: str = "postgresql+psycopg://vaganexo:change-me@127.0.0.1:5432/vaganexo"
    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_broker_url: str = "redis://127.0.0.1:6379/0"
    celery_result_backend: str = "redis://127.0.0.1:6379/1"

    # Private storage for resumes. Paths are relative to STORAGE_ROOT unless
    # STORAGE_ROOT itself is absolute.
    storage_root: Path = PROJECT_ROOT / "storage"
    resume_upload_dir: str = "uploads"
    resume_extracted_dir: str = "extracted"
    resume_temp_dir: str = "temporary"
    max_resume_upload_bytes: int = 10 * 1024 * 1024
    max_resume_archive_entries: int = 2_000
    max_resume_uncompressed_bytes: int = 50 * 1024 * 1024
    max_resume_text_characters: int = 2_000_000

    # Authentication, opaque sessions, cookies, and rate limiting
    auth_session_cookie_name: str = "vaganexo_session"
    auth_session_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 days
    auth_cookie_secure: bool | None = None
    auth_public_registration_enabled: bool = False
    auth_login_rate_limit_max_attempts: int = 5
    auth_login_rate_limit_ip_max_attempts: int = 20
    auth_login_rate_limit_window_seconds: int = 300
    auth_register_rate_limit_max_attempts: int = 5
    auth_register_rate_limit_window_seconds: int = 3600
    auth_resend_rate_limit_max_attempts: int = 3
    auth_resend_rate_limit_window_seconds: int = 900
    auth_general_rate_limit_max_attempts: int = 60
    auth_general_rate_limit_window_seconds: int = 60
    auth_trusted_proxies: list[str] = []

    # Account lifecycle tokens, transactional email, and outbox encryption
    app_public_base_url: str = "http://127.0.0.1:3000"
    email_verification_ttl_hours: int = 24
    mail_provider: str = "fake"
    mail_from_address: str = "no-reply@vaganexo.local"
    mail_from_name: str = "VagaNexo"
    mail_host: str = "127.0.0.1"
    mail_port: int = 1025
    mail_username: str = ""
    mail_password: SecretStr = SecretStr("")
    mail_use_tls: bool = False
    mail_use_ssl: bool = False
    mail_timeout: int = 10
    email_outbox_encryption_keys: SecretStr = SecretStr("")
    email_outbox_max_attempts: int = 5
    email_outbox_lease_seconds: int = 60

    ai_provider: str = "openai-compatible"
    ai_base_url: str = "http://127.0.0.1:11434/v1"
    ai_model: str = "llama3.1"
    ai_api_key: SecretStr = SecretStr("")


@lru_cache
def get_settings() -> Settings:
    return Settings()
