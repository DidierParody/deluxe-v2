from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Telegram
    TELEGRAM_BOT_TOKEN_CS: str
    TELEGRAM_BOT_TOKEN_AM: str
    WEBHOOK_BASE_URL: str

    # LLMs
    GOOGLE_API_KEY: str
    GROQ_API_KEY: str

    # Constant Models (Primary and Fallback)
    GOOGLE_MODEL: str = "gemini-2.5-flash"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Deploy / ops
    ENABLE_BACKGROUND_SCHEDULER: bool = True
    ENABLE_SELF_PING: bool = False

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
