from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = Field(default="Soccer Odds Watcher", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")

    database_url: str = Field(
        default="postgresql+psycopg://odds_user:odds_password@localhost:5432/odds",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    ps3838_soccer_url: str = Field(
        default="https://www.ps3838.com/en/sports/soccer", alias="PS3838_SOCCER_URL"
    )
    estave_soccer_url: str = Field(
        default="https://www.e-stave.com/stave", alias="ESTAVE_SOCCER_URL"
    )

    odds_drop_threshold_pct: float = Field(default=8.0, alias="ODDS_DROP_THRESHOLD_PCT")
    odds_drop_lookback_min: int = Field(default=15, alias="ODDS_DROP_LOOKBACK_MIN")
    value_edge_threshold_pct: float = Field(default=4.0, alias="VALUE_EDGE_THRESHOLD_PCT")
    alert_cooldown_min: int = Field(default=20, alias="ALERT_COOLDOWN_MIN")

    use_mock_scrape_data: bool = Field(default=True, alias="USE_MOCK_SCRAPE_DATA")


@lru_cache
def get_settings() -> Settings:
    return Settings()
