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
    league: str | None
    external_event_id: str
    home_team: str
    away_team: str
    market_type: str
    selection: str
    odds_decimal: Decimal
    scraped_at: datetime

    model_config = {"from_attributes": True}
