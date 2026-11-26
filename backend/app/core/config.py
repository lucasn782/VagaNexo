from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    ai_provider: str = "openai-compatible"
    ai_base_url: str = "http://127.0.0.1:11434/v1"
    ai_model: str = "llama3.1"
    ai_api_key: SecretStr = SecretStr("")


@lru_cache
def get_settings() -> Settings:
    return Settings()
