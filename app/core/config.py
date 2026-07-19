from pydantic import field_validator
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

    GACHA_IMAGE_CHANNEL_ID: int = 0
    LEADERBOARD_CHANNEL_ID: int = 0
    # Image generation model selection:
    CLOUDFLARE_IMAGE_MODEL: str = "google/imagen-4"
    DATABASE_PATH: str = "data/database.db"

    # Firebase configuration
    FIREBASE_CREDENTIALS_JSON: str = ""
    FIREBASE_CREDENTIALS_PATH: str = "data/firebase-key.json"
    FIREBASE_DATABASE_URL: str = ""

    @field_validator(
        "GACHA_IMAGE_CHANNEL_ID",
        "LEADERBOARD_CHANNEL_ID",
        mode="before",
    )
    @classmethod
    def empty_str_to_zero(cls, v):
        if v == "":
            return 0
        return v


settings = Settings()
