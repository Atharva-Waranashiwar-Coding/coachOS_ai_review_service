from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="CoachOS AI Review Service", alias="APP_NAME")
    database_url: str = Field(alias="DATABASE_URL")
    jwt_secret_key: str = Field(alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    athlete_service_url: str = Field(alias="ATHLETE_SERVICE_URL")
    media_service_url: str = Field(alias="MEDIA_SERVICE_URL")
    athlete_service_internal_url: str = Field(alias="ATHLETE_SERVICE_INTERNAL_URL")
    internal_service_name: str = Field(default="ai-review-service", alias="INTERNAL_SERVICE_NAME")
    internal_service_token: str = Field(alias="INTERNAL_SERVICE_TOKEN")
    outbox_batch_size: int = Field(default=20, alias="OUTBOX_BATCH_SIZE", gt=0)
    outbox_poll_interval_seconds: float = Field(default=2, alias="OUTBOX_POLL_INTERVAL_SECONDS", gt=0)
    outbox_max_attempts: int = Field(default=8, alias="OUTBOX_MAX_ATTEMPTS", gt=0)
    outbox_base_retry_seconds: int = Field(default=5, alias="OUTBOX_BASE_RETRY_SECONDS", gt=0)
    upstream_timeout_seconds: float = 5
    ai_provider: str = Field(default="openai", alias="AI_PROVIDER")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    ai_request_timeout_seconds: float = Field(default=60, alias="AI_REQUEST_TIMEOUT_SECONDS")
    ai_max_retries: int = Field(default=3, alias="AI_MAX_RETRIES")
    ai_temperature: float = Field(default=0.2, alias="AI_TEMPERATURE")
    ai_max_output_tokens: int = Field(default=3000, alias="AI_MAX_OUTPUT_TOKENS")
    prompt_version: str = Field(default="coachos-review-v1", alias="PROMPT_VERSION")
    review_schema_version: int = Field(default=1, alias="REVIEW_SCHEMA_VERSION")
    review_job_batch_size: int = Field(default=5, alias="REVIEW_JOB_BATCH_SIZE")
    review_job_poll_interval_seconds: float = Field(default=5, alias="REVIEW_JOB_POLL_INTERVAL_SECONDS")
    review_job_max_attempts: int = Field(default=3, alias="REVIEW_JOB_MAX_ATTEMPTS")
    review_job_base_retry_seconds: int = Field(default=10, alias="REVIEW_JOB_BASE_RETRY_SECONDS")
    max_coach_context_characters: int = Field(default=10000, alias="MAX_COACH_CONTEXT_CHARACTERS")
    max_transcript_characters: int = Field(default=50000, alias="MAX_TRANSCRIPT_CHARACTERS")
    max_manual_observations: int = Field(default=50, alias="MAX_MANUAL_OBSERVATIONS")
    max_frame_observations: int = Field(default=100, alias="MAX_FRAME_OBSERVATIONS")
    default_page_size: int = Field(default=20, alias="DEFAULT_PAGE_SIZE")
    max_page_size: int = Field(default=100, alias="MAX_PAGE_SIZE")
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
