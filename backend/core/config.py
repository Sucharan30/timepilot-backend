"""
backend/core/config.py

Central settings object.  Reads all configuration from environment variables
(or from a .env file locally via python-dotenv).
All Railway Variables map directly to these fields.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Telegram ──────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""

    # ── App ───────────────────────────────────────────────────────────────────
    # Set DEBUG=true in Railway Variables to expose OTP in response
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"          # ignore any unknown env vars Railway injects


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton — import this wherever you need settings."""
    return Settings()
