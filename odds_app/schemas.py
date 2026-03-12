from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    app: str


class RunOnceResponse(BaseModel):
    ps3838_quotes: int
    estave_quotes: int
    drop_alerts_ps3838: int
    drop_alerts_estave: int
    value_edge_alerts: int
    simulated_drop_alerts: int
    total_alerts_created: int


class ForceCompareResponse(BaseModel):
    reconciled_events: int
    overlap_matches: int
    value_edge_alerts: int


class AlertResponse(BaseModel):
    id: int
    alert_type: str
    source: str | None
    market_type: str
    selection: str
    home_team: str
    away_team: str
    message: str
    details: dict
    is_sent: bool
    created_at: datetime
    sent_at: datetime | None

    model_config = {"from_attributes": True}


class OddsSnapshotResponse(BaseModel):
    id: int
    source: str
    sport: str
    league: str | None
    external_event_id: str
    home_team: str
    away_team: str
    market_type: str
    selection: str
    odds_decimal: Decimal
    scraped_at: datetime

    model_config = {"from_attributes": True}


class SourceEventSummary(BaseModel):
    source: str
    sport: str
    external_event_id: str
    league: str | None
    latest_home_odds: Decimal | None
    latest_draw_odds: Decimal | None
    latest_away_odds: Decimal | None
    last_scraped_at: datetime | None


class MatchSummaryResponse(BaseModel):
    match_id: int
    sport: str
    home_team: str
    away_team: str
    kickoff_bucket_utc: datetime | None
    source_events: list[SourceEventSummary]
    updated_at: datetime


class SourceMatchRow(BaseModel):
    canonical_match_id: int
    source: str
    sport: str
    external_event_id: str
    home_team: str
    away_team: str
    league: str | None
    kickoff_utc: datetime | None
    latest_home_odds: Decimal | None
    latest_draw_odds: Decimal | None
    latest_away_odds: Decimal | None
    last_scraped_at: datetime | None
    updated_at: datetime


class OverlapMatchRow(BaseModel):
    canonical_match_id: int
    sport: str
    home_team: str
    away_team: str
    kickoff_utc: datetime | None
    ps3838_event_id: str
    estave_event_id: str
    ps3838_home_odds: Decimal | None
    ps3838_draw_odds: Decimal | None
    ps3838_away_odds: Decimal | None
    estave_home_odds: Decimal | None
    estave_draw_odds: Decimal | None
    estave_away_odds: Decimal | None
    edge_pct_estave_vs_ps3838_home: float | None
    better_source_home: str | None
    updated_at: datetime


class PS3838DiagnosticsOverrides(BaseModel):
    scraper_enable_playwright: bool | None = None
    scraper_request_timeout_sec: float | None = None
    scraper_proxy_url: str | None = None

    ps3838_proxy_url: str | None = None
    ps3838_cookie_header: str | None = None
    ps3838_referer_url: str | None = None
    ps3838_browser_only: bool | None = None
    ps3838_enable_stealth: bool | None = None
    ps3838_retry_count: int | None = None
    ps3838_zenrows_api_key: str | None = None
    ps3838_scrapingbee_api_key: str | None = None
    vodds_dashboard_url: str | None = None
    vodds_username: str | None = None
    vodds_password: str | None = None
    vodds_proxy_url: str | None = None
    vodds_headless: bool | None = None
    vodds_timeout_sec: float | None = None
