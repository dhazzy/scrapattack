import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from odds_app.config import get_settings
from odds_app.scrapers.base import OddsQuote
from odds_app.scrapers.live_parser import DEFAULT_HEADERS, extract_live_quotes

logger = logging.getLogger(__name__)


class PS3838Scraper:
    source = "ps3838"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def scrape_soccer(self) -> list[OddsQuote]:
        if self.settings.use_mock_scrape_data:
            return self._mock_quotes()

        headers = dict(DEFAULT_HEADERS)
        headers.update(
            {
                "Referer": self.settings.ps3838_referer_url,
                "Origin": "https://www.ps3838.com",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        if self.settings.ps3838_cookie_header:
            headers["Cookie"] = self.settings.ps3838_cookie_header

        proxy_url = self.settings.ps3838_proxy_url or self.settings.scraper_proxy_url or None
        retries = max(1, self.settings.ps3838_retry_count)

        for attempt in range(1, retries + 1):
            use_playwright = self.settings.scraper_enable_playwright or attempt > 1
            try:
                quotes = await extract_live_quotes(
                    source=self.source,
                    url=self.settings.ps3838_soccer_url,
                    timeout_sec=self.settings.scraper_request_timeout_sec,
                    enable_playwright=use_playwright,
                    headers=headers,
                    proxy_url=proxy_url,
                    cookie_header=self.settings.ps3838_cookie_header,
                    enable_stealth=self.settings.ps3838_enable_stealth,
                    browser_only=self.settings.ps3838_browser_only,
                )
            except Exception as exc:
                logger.warning("PS3838 extraction error (attempt %s/%s): %s", attempt, retries, exc)
                continue

            if quotes:
                if attempt > 1:
                    logger.info("PS3838 scraping succeeded after retry attempt %s", attempt)
                return quotes

            logger.warning(
                "PS3838 returned no quotes on attempt %s/%s (proxy=%s, playwright=%s)",
                attempt,
                retries,
                bool(proxy_url),
                use_playwright,
            )

        logger.warning(
            "No live PS3838 quotes parsed. Usually requires residential proxy and valid session cookies."
        )
        return []

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
