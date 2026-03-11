import logging

from odds_app.config import get_settings
from odds_app.scrapers.base import OddsQuote
from odds_app.scrapers.live_parser import (
    DEFAULT_HEADERS,
    extract_live_quotes,
    extract_quotes_from_html,
    fetch_html_via_scrapingbee,
    fetch_html_via_zenrows,
)
from odds_app.scrapers.vodds import scrape_ps3838_from_vodds

logger = logging.getLogger(__name__)


class PS3838Scraper:
    source = "ps3838"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def scrape_soccer(self) -> list[OddsQuote]:
        # Primary: scrape PS3838 odds via Vodds dashboard if credentials are configured.
        if self.settings.vodds_username and self.settings.vodds_password:
            vodds_proxy = (
                self.settings.vodds_proxy_url
                or self.settings.ps3838_proxy_url
                or self.settings.scraper_proxy_url
                or None
            )
            quotes = await scrape_ps3838_from_vodds(
                dashboard_url=self.settings.vodds_dashboard_url,
                username=self.settings.vodds_username,
                password=self.settings.vodds_password,
                headless=self.settings.vodds_headless,
                timeout_sec=self.settings.vodds_timeout_sec,
                proxy_url=vodds_proxy,
            )
            if quotes:
                logger.info("PS3838 scraping via Vodds succeeded with %s quotes", len(quotes))
                return quotes
            logger.warning("Vodds PS3838 scrape returned no quotes, trying direct paths.")

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

        provider_quotes = await self._try_unblock_provider_paths()
        if provider_quotes:
            return provider_quotes

        logger.warning(
            "No live PS3838 quotes parsed. Try Vodds login, residential proxy + valid session cookie, or provider API key."
        )
        return []

    async def _try_unblock_provider_paths(self) -> list[OddsQuote]:
        timeout_sec = max(self.settings.scraper_request_timeout_sec, 45.0)

        if self.settings.ps3838_zenrows_api_key:
            try:
                html = await fetch_html_via_zenrows(
                    target_url=self.settings.ps3838_soccer_url,
                    api_key=self.settings.ps3838_zenrows_api_key,
                    timeout_sec=timeout_sec,
                    js_render=True,
                )
                quotes = extract_quotes_from_html(source=self.source, html=html)
                if quotes:
                    logger.info("PS3838 extraction succeeded via ZenRows.")
                    return quotes
                logger.warning("ZenRows returned page but no parseable PS3838 quotes.")
            except Exception as exc:
                logger.warning("ZenRows PS3838 fetch failed: %s", exc)

        if self.settings.ps3838_scrapingbee_api_key:
            try:
                html = await fetch_html_via_scrapingbee(
                    target_url=self.settings.ps3838_soccer_url,
                    api_key=self.settings.ps3838_scrapingbee_api_key,
                    timeout_sec=timeout_sec,
                    render_js=True,
                )
                quotes = extract_quotes_from_html(source=self.source, html=html)
                if quotes:
                    logger.info("PS3838 extraction succeeded via ScrapingBee.")
                    return quotes
                logger.warning("ScrapingBee returned page but no parseable PS3838 quotes.")
            except Exception as exc:
                logger.warning("ScrapingBee PS3838 fetch failed: %s", exc)

        return []
