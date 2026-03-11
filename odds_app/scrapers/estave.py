import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from odds_app.config import get_settings
from odds_app.scrapers.base import OddsQuote
from odds_app.scrapers.live_parser import extract_live_quotes

logger = logging.getLogger(__name__)


class EStaveScraper:
    source = "e_stave"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def scrape_soccer(self) -> list[OddsQuote]:
        if self.settings.use_mock_scrape_data:
            return self._mock_quotes()

        quotes = await extract_live_quotes(
            source=self.source,
            url=self.settings.estave_soccer_url,
            timeout_sec=self.settings.scraper_request_timeout_sec,
            enable_playwright=self.settings.scraper_enable_playwright,
        )
        if not quotes:
            logger.warning("No live e-stave quotes parsed. Falling back to mock quotes.")
            return self._mock_quotes()
        return quotes

    def _mock_quotes(self) -> list[OddsQuote]:
        now = datetime.now(timezone.utc)
        kickoff = now + timedelta(hours=6)
        return [
            OddsQuote(
                source=self.source,
                sport="soccer",
                league="England Premier League",
                external_event_id="es-ars-liv-a",
                home_team="Arsenal FC",
                away_team="Liverpool FC",
                kickoff_utc=kickoff,
                market_type="1x2",
                selection="home",
                odds_decimal=Decimal("2.48"),
                scraped_at=now,
            ),
            OddsQuote(
                source=self.source,
                sport="soccer",
                league="Spain La Liga",
                external_event_id="es-rma-atm-b",
                home_team="Real Madrid CF",
                away_team="Atletico Madrid",
                kickoff_utc=kickoff + timedelta(hours=2),
                market_type="1x2",
                selection="home",
                odds_decimal=Decimal("2.10"),
                scraped_at=now,
            ),
        ]
