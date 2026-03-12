from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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
    ps3838_zenrows_api_key: str = Field(default="", alias="PS3838_ZENROWS_API_KEY")
    ps3838_scrapingbee_api_key: str = Field(default="", alias="PS3838_SCRAPINGBEE_API_KEY")

    vodds_dashboard_url: str = Field(
        default="https://vodds.com/member/dashboard", alias="VODDS_DASHBOARD_URL"
    )
    vodds_username: str = Field(default="", alias="VODDS_USERNAME")
    vodds_password: str = Field(default="", alias="VODDS_PASSWORD")
    vodds_proxy_url: str = Field(default="", alias="VODDS_PROXY_URL")
    vodds_headless: bool = Field(default=True, alias="VODDS_HEADLESS")
    vodds_timeout_sec: float = Field(default=60.0, alias="VODDS_TIMEOUT_SEC")

    estave_soccer_url: str = Field(
        default="https://www.e-stave.com/stave", alias="ESTAVE_SOCCER_URL"
    )
    estave_page_size: int = Field(default=25, alias="ESTAVE_PAGE_SIZE")
    estave_max_pages_per_query: int = Field(default=40, alias="ESTAVE_MAX_PAGES_PER_QUERY")
    estave_max_empty_pages_per_query: int = Field(
        default=2, alias="ESTAVE_MAX_EMPTY_PAGES_PER_QUERY"
    )
    estave_max_repeat_pages_per_query: int = Field(
        default=2, alias="ESTAVE_MAX_REPEAT_PAGES_PER_QUERY"
    )
    estave_max_no_new_pages_per_query: int = Field(
        default=3, alias="ESTAVE_MAX_NO_NEW_PAGES_PER_QUERY"
    )
    estave_extra_b_values: str = Field(default="", alias="ESTAVE_EXTRA_B_VALUES")
    estave_g_values: str = Field(default="25", alias="ESTAVE_G_VALUES")
    estave_backfill_max_pages_per_query: int = Field(
        default=80, alias="ESTAVE_BACKFILL_MAX_PAGES_PER_QUERY"
    )
    estave_backfill_extra_b_values: str = Field(default="", alias="ESTAVE_BACKFILL_EXTRA_B_VALUES")
    estave_backfill_g_values: str = Field(default="", alias="ESTAVE_BACKFILL_G_VALUES")

    scraper_request_timeout_sec: float = Field(default=30.0, alias="SCRAPER_REQUEST_TIMEOUT_SEC")
    scraper_enable_playwright: bool = Field(default=True, alias="SCRAPER_ENABLE_PLAYWRIGHT")
    scraper_proxy_url: str = Field(default="", alias="SCRAPER_PROXY_URL")
    scrape_interval_sec: int = Field(default=300, alias="SCRAPE_INTERVAL_SEC")
    compare_interval_sec: int = Field(default=300, alias="COMPARE_INTERVAL_SEC")
    alert_dispatch_interval_sec: int = Field(default=30, alias="ALERT_DISPATCH_INTERVAL_SEC")
    retention_cleanup_interval_sec: int = Field(default=3600, alias="RETENTION_CLEANUP_INTERVAL_SEC")
    scrape_min_quotes_success: int = Field(default=1, alias="SCRAPE_MIN_QUOTES_SUCCESS")
    scrape_recovery_retry_count: int = Field(default=1, alias="SCRAPE_RECOVERY_RETRY_COUNT")
    scrape_recovery_backoff_sec: float = Field(default=2.0, alias="SCRAPE_RECOVERY_BACKOFF_SEC")
    scrape_degraded_consecutive_failures: int = Field(
        default=3, alias="SCRAPE_DEGRADED_CONSECUTIVE_FAILURES"
    )
    scrape_degraded_cooldown_sec: int = Field(default=600, alias="SCRAPE_DEGRADED_COOLDOWN_SEC")
    scrape_backfill_near_interval_sec: int = Field(
        default=1800, alias="SCRAPE_BACKFILL_NEAR_INTERVAL_SEC"
    )
    scrape_backfill_far_interval_sec: int = Field(
        default=3600, alias="SCRAPE_BACKFILL_FAR_INTERVAL_SEC"
    )
    scrape_backfill_near_min_hours: int = Field(default=24, alias="SCRAPE_BACKFILL_NEAR_MIN_HOURS")
    scrape_backfill_near_max_hours: int = Field(default=72, alias="SCRAPE_BACKFILL_NEAR_MAX_HOURS")
    scrape_backfill_far_min_hours: int = Field(default=72, alias="SCRAPE_BACKFILL_FAR_MIN_HOURS")
    scrape_backfill_far_max_hours: int = Field(default=336, alias="SCRAPE_BACKFILL_FAR_MAX_HOURS")
    canary_interval_sec: int = Field(default=900, alias="CANARY_INTERVAL_SEC")
    canary_window_hours: int = Field(default=6, alias="CANARY_WINDOW_HOURS")
    canary_min_success_rate_pct: float = Field(default=70.0, alias="CANARY_MIN_SUCCESS_RATE_PCT")
    canary_min_avg_quotes: float = Field(default=5.0, alias="CANARY_MIN_AVG_QUOTES")
    canary_min_upcoming_72h: int = Field(default=20, alias="CANARY_MIN_UPCOMING_72H")
    canary_min_upcoming_168h: int = Field(default=50, alias="CANARY_MIN_UPCOMING_168H")
    canary_alert_cooldown_min: int = Field(default=120, alias="CANARY_ALERT_COOLDOWN_MIN")

    odds_drop_threshold_pct: float = Field(default=8.0, alias="ODDS_DROP_THRESHOLD_PCT")
    odds_drop_opening_threshold_pct: float = Field(
        default=12.0, alias="ODDS_DROP_OPENING_THRESHOLD_PCT"
    )
    odds_drop_lookback_min: int = Field(default=15, alias="ODDS_DROP_LOOKBACK_MIN")
    odds_drop_confirmation_count: int = Field(default=2, alias="ODDS_DROP_CONFIRMATION_COUNT")
    odds_drop_confirmation_window_min: int = Field(
        default=180, alias="ODDS_DROP_CONFIRMATION_WINDOW_MIN"
    )
    odds_drop_renotify_improvement_pct: float = Field(
        default=1.5, alias="ODDS_DROP_RENOTIFY_IMPROVEMENT_PCT"
    )
    value_edge_threshold_pct: float = Field(default=4.0, alias="VALUE_EDGE_THRESHOLD_PCT")
    alert_cooldown_min: int = Field(default=20, alias="ALERT_COOLDOWN_MIN")
    odds_snapshot_retention_days: int = Field(default=45, alias="ODDS_SNAPSHOT_RETENTION_DAYS")
    scrape_run_retention_days: int = Field(default=14, alias="SCRAPE_RUN_RETENTION_DAYS")
    alert_retention_days: int = Field(default=60, alias="ALERT_RETENTION_DAYS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
