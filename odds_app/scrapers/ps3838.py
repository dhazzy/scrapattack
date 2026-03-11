import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from bs4 import BeautifulSoup

from odds_app.config import get_settings
from odds_app.scrapers.base import OddsQuote

logger = logging.getLogger(__name__)


class PS3838Scraper:
    source = "ps3838"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def scrape_soccer(self) -> list[OddsQuote]:
        if self.settings.use_mock_scrape_data:
            return self._mock_quotes()

        html = await self._fetch_page_html(self.settings.ps3838_soccer_url)
        quotes = self._extract_quotes_from_html(html)
        if not quotes:
            logger.warning(
                "No PS3838 quotes parsed. Update selectors/API parser for production site layout."
            )
        return quotes

    async def _fetch_page_html(self, url: str) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            return response.text

    def _extract_quotes_from_html(self, html: str) -> list[OddsQuote]:
        now = datetime.now(timezone.utc)
        soup = BeautifulSoup(html, "lxml")
        rows = soup.select("[data-event-id][data-home-team][data-away-team]")
        quotes: list[OddsQuote] = []
        for row in rows:
            event_id = row.get("data-event-id", "").strip()
            home = row.get("data-home-team", "").strip()
            away = row.get("data-away-team", "").strip()
            market = row.get("data-market", "").strip() or "1x2"
            selection = row.get("data-selection", "").strip() or "home"
            odds_raw = row.get("data-odds", "").strip()
            league = row.get("data-league")
            if not (event_id and home and away and odds_raw):
                continue
            try:
                odds_val = Decimal(odds_raw)
            except Exception:
                continue
            quotes.append(
                OddsQuote(
                    source=self.source,
                    sport="soccer",
                    league=league,
                    external_event_id=event_id,
                    home_team=home,
                    away_team=away,
                    kickoff_utc=None,
                    market_type=market,
                    selection=selection,
                    odds_decimal=odds_val,
                    scraped_at=now,
                )
            )
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
