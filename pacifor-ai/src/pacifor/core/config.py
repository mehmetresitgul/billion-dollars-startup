from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "Pacifor AI"
    debug: bool = False

    database_url: str = "sqlite+aiosqlite:///./pacifor.db"
    redis_url: str | None = None

    openai_api_key: str = ""

    kill_switch_ttl_seconds: int = 3600


settings = Settings()
