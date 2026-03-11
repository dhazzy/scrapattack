import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from odds_app.config import get_settings
from odds_app.scrapers.base import OddsQuote
from odds_app.scrapers.live_parser import extract_live_quotes

logger = logging.getLogger(__name__)


class PS3838Scraper:
    source = "ps3838"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def scrape_soccer(self) -> list[OddsQuote]:
        if self.settings.use_mock_scrape_data:
            return self._mock_quotes()

        try:
            quotes = await extract_live_quotes(
                source=self.source,
                url=self.settings.ps3838_soccer_url,
                timeout_sec=self.settings.scraper_request_timeout_sec,
                enable_playwright=self.settings.scraper_enable_playwright,
            )
        except Exception as exc:
            logger.warning("PS3838 live extraction error: %s", exc)
            return []

        if not quotes:
            logger.warning("No live PS3838 quotes parsed. Source may be blocked or selectors outdated.")
        return quotes

    def _mock_quotes(self) -> list[OddsQuote]:
        now = datetime.now(timezone.utc)
        kickoff = now + timedelta(hours=6)
        return [
            OddsQuote(
                source=self.source,
                sport="soccer",
                league="England Premier League",
                external_event_id="ps-ars-liv-001",
                home_team="Arsenal",
                away_team="Liverpool",
                kickoff_utc=kickoff,
                market_type="1x2",
                selection="home",
                odds_decimal=Decimal("2.35"),
                scraped_at=now,
            ),
            OddsQuote(
                source=self.source,
                sport="soccer",
                league="Spain La Liga",
                external_event_id="ps-rma-atm-002",
                home_team="Real Madrid",
                away_team="Atletico Madrid",
                kickoff_utc=kickoff + timedelta(hours=2),
                market_type="1x2",
                selection="home",
                odds_decimal=Decimal("1.95"),
                scraped_at=now,
            ),
        ]
