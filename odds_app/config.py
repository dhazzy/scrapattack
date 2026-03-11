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
    db_startup_max_retries: int = Field(default=20, alias="DB_STARTUP_MAX_RETRIES")
    db_startup_retry_delay_sec: float = Field(default=1.5, alias="DB_STARTUP_RETRY_DELAY_SEC")

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    ps3838_soccer_url: str = Field(
        default="https://www.ps3838.com/en/sports/soccer", alias="PS3838_SOCCER_URL"
    )
    ps3838_referer_url: str = Field(default="https://www.ps3838.com/", alias="PS3838_REFERER_URL")
    ps3838_cookie_header: str = Field(default="", alias="PS3838_COOKIE_HEADER")
    ps3838_proxy_url: str = Field(default="", alias="PS3838_PROXY_URL")
    ps3838_browser_only: bool = Field(default=False, alias="PS3838_BROWSER_ONLY")
    ps3838_enable_stealth: bool = Field(default=True, alias="PS3838_ENABLE_STEALTH")
    ps3838_retry_count: int = Field(default=2, alias="PS3838_RETRY_COUNT")

    estave_soccer_url: str = Field(
        default="https://www.e-stave.com/stave", alias="ESTAVE_SOCCER_URL"
    )

    scraper_request_timeout_sec: float = Field(default=30.0, alias="SCRAPER_REQUEST_TIMEOUT_SEC")
    scraper_enable_playwright: bool = Field(default=False, alias="SCRAPER_ENABLE_PLAYWRIGHT")
    scraper_proxy_url: str = Field(default="", alias="SCRAPER_PROXY_URL")
    scrape_interval_sec: int = Field(default=300, alias="SCRAPE_INTERVAL_SEC")
    compare_interval_sec: int = Field(default=300, alias="COMPARE_INTERVAL_SEC")
    alert_dispatch_interval_sec: int = Field(default=30, alias="ALERT_DISPATCH_INTERVAL_SEC")

    odds_drop_threshold_pct: float = Field(default=8.0, alias="ODDS_DROP_THRESHOLD_PCT")
    odds_drop_lookback_min: int = Field(default=15, alias="ODDS_DROP_LOOKBACK_MIN")
    value_edge_threshold_pct: float = Field(default=4.0, alias="VALUE_EDGE_THRESHOLD_PCT")
    alert_cooldown_min: int = Field(default=20, alias="ALERT_COOLDOWN_MIN")

    use_mock_scrape_data: bool = Field(default=True, alias="USE_MOCK_SCRAPE_DATA")


@lru_cache
def get_settings() -> Settings:
    return Settings()
