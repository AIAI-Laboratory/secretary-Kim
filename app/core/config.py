import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    DISCORD_BOT_TOKEN: str = ""
    GEMINI_API_KEY: str = ""
    PIXELLAB_API_KEY: str = ""
    GEMINI_PRIMARY_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_FALLBACK_MODEL: str = "gemini-3.5-flash"
    TEMP_DIR: str = "temp"

    CLOUDFLARE_API_TOKEN: str = ""
    CLOUDFLARE_ACCOUNT_ID: str = ""
    GACHA_IMAGE_CHANNEL_ID: int = 0
    # Image generation model selection:
    CLOUDFLARE_IMAGE_MODEL: str = "google/imagen-4"
    DATABASE_PATH: str = "data/database.db"


settings = Settings()
