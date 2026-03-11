from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class OddsQuote:
    source: str
    sport: str
    league: str | None
    external_event_id: str
    home_team: str
    away_team: str
    kickoff_utc: datetime | None
    market_type: str
    selection: str
    odds_decimal: Decimal
    scraped_at: datetime
