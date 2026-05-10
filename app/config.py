from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Telegram
    TELEGRAM_BOT_TOKEN_CS: str
    TELEGRAM_BOT_TOKEN_AM: str
    WEBHOOK_BASE_URL: str
    WEBHOOK_SECRET_TOKEN: str = ""   # Validates X-Telegram-Bot-Api-Secret-Token header

    # NVIDIA NIM
    NVIDIA_API_KEY: str
    NVIDIA_MODEL_PRIMARY: str = "meta/llama-3.3-70b-instruct"
    NVIDIA_MODEL_FALLBACK: str = "mistralai/mistral-large-2-instruct"

    # Deploy / ops
    ENABLE_BACKGROUND_SCHEDULER: bool = False   # Use EventBridge on AWS; True for local dev only

    # Redis / memory
    REDIS_URL: str | None = None
    UPSTASH_REDIS_REST_URL: str | None = None
    UPSTASH_REDIS_REST_TOKEN: str | None = None
    REDIS_MEMORY_ENABLED: bool = True
    REDIS_MEMORY_TTL_CUSTOMER_MINUTES: int = 360
    REDIS_MEMORY_TTL_ADMIN_MINUTES: int = 30
    REDIS_IDEMPOTENCY_TTL_MINUTES: int = 30
    REDIS_HISTORY_MAX_MESSAGES: int = 24

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
