from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="CoachOS AI Review Service", alias="APP_NAME")
    database_url: str = Field(alias="DATABASE_URL")
    athlete_service_internal_url: str = Field(alias="ATHLETE_SERVICE_INTERNAL_URL")
    internal_service_name: str = Field(default="ai-review-service", alias="INTERNAL_SERVICE_NAME")
    internal_service_token: str = Field(alias="INTERNAL_SERVICE_TOKEN")
    outbox_batch_size: int = Field(default=20, alias="OUTBOX_BATCH_SIZE", gt=0)
    outbox_poll_interval_seconds: float = Field(default=2, alias="OUTBOX_POLL_INTERVAL_SECONDS", gt=0)
    outbox_max_attempts: int = Field(default=8, alias="OUTBOX_MAX_ATTEMPTS", gt=0)
    outbox_base_retry_seconds: int = Field(default=5, alias="OUTBOX_BASE_RETRY_SECONDS", gt=0)
    upstream_timeout_seconds: float = 5
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
