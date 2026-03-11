import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
from dateutil import parser as dt_parser

from odds_app.config import get_settings
from odds_app.scrapers.base import OddsQuote
from odds_app.scrapers.live_parser import extract_live_quotes

logger = logging.getLogger(__name__)

# Pulled from live probing. Different b values expose different early lists.
SPORT_REQUESTS = [
    {"sport": "soccer", "f": 1, "b_values": [0, 2, 4, 6, 7, 11]},
    {"sport": "basketball", "f": 2, "b_values": [0, 2, 6, 7, 11]},
    {"sport": "tennis", "f": 4, "b_values": [0, 6, 7, 11]},
]


class EStaveScraper:
    source = "e_stave"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def scrape_soccer(self) -> list[OddsQuote]:
        mobile_quotes = await self._scrape_mobile_service_quotes()
        if mobile_quotes:
            return mobile_quotes

        generic_quotes = await extract_live_quotes(
            source=self.source,
            url=self.settings.estave_soccer_url,
            timeout_sec=self.settings.scraper_request_timeout_sec,
            enable_playwright=self.settings.scraper_enable_playwright,
            proxy_url=self.settings.scraper_proxy_url or None,
        )
        if generic_quotes:
            return generic_quotes

        logger.warning("No live e-stave quotes parsed.")
        return []

    async def _scrape_mobile_service_quotes(self) -> list[OddsQuote]:
        base_url = "https://www.e-stave.com"
        headers = {"User-Agent": "Mozilla/5.0"}
        now = datetime.now(timezone.utc)
        app_uuid = str(uuid.uuid4())

        client_kwargs: dict[str, Any] = {"timeout": self.settings.scraper_request_timeout_sec}
        if self.settings.scraper_proxy_url:
            client_kwargs["proxy"] = self.settings.scraper_proxy_url

        async with httpx.AsyncClient(**client_kwargs) as client:
            service_resp = await client.get(f"{base_url}/service.json", headers=headers)
            service_resp.raise_for_status()
            service_url = service_resp.json().get("serviceURL", "_MobileService.aspx")
            service_endpoint = f"{base_url}/{service_url.lstrip('/')}"

            settings_resp = await client.get(
                service_endpoint,
                headers=headers,
                params={
                    "controller": "settings",
                    "action": "index",
                    "appVer": 1,
                    "serviceVer": 2,
                    "serviceType": "sencha",
                },
            )
            settings_resp.raise_for_status()
            settings_payload = settings_resp.json()
            csrf_token = (
                settings_payload.get("global", {}).get("csrfToken")
                or settings_payload.get("csrfToken")
            )
            if not csrf_token:
                logger.warning("e-stave settings did not return CSRF token")
                return []

            common = {
                "controller": "stave",
                "action": "stave",
                "appVer": 1,
                "serviceVer": 2,
                "serviceType": "sencha",
                "appUUID": app_uuid,
                "CSRFToken": csrf_token,
                "appSig": "",
                "appKey": "mobileestave",
                "a": 3,
                "g": 25,
                "i": "false",
                "l": "",
                "n": self.settings.estave_page_size,
            }

            quotes: list[OddsQuote] = []
            seen: set[tuple[str, str]] = set()
            for request in SPORT_REQUESTS:
                for b_value in request["b_values"]:
                    for page in range(self.settings.estave_max_pages_per_query):
                        params = {
                            **common,
                            "b": b_value,
                            "f": request["f"],
                            "d": page,
                        }
                        resp = await client.get(service_endpoint, headers=headers, params=params)
                        if resp.status_code >= 400:
                            break
                        payload = resp.json()
                        data = payload.get("data") if isinstance(payload, dict) else None
                        events = data.get("bb") if isinstance(data, dict) else None
                        if not isinstance(events, list) or not events:
                            break

                        page_quotes = self._quotes_from_events(events, request["sport"], now)
                        if not page_quotes:
                            break

                        new_count = 0
                        for quote in page_quotes:
                            key = (quote.external_event_id, quote.selection)
                            if key in seen:
                                continue
                            seen.add(key)
                            quotes.append(quote)
                            new_count += 1

                        # d parameter appears to be sticky in many lists; stop once pages repeat.
                        if new_count == 0:
                            break

            return quotes

    def _quotes_from_events(
        self, events: list[dict[str, Any]], sport: str, now: datetime
    ) -> list[OddsQuote]:
        quotes: list[OddsQuote] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("a") or event.get("b") or "").strip()
            match_name = str(event.get("c") or "").strip()
            if not event_id or " - " not in match_name:
                continue
            home_team, away_team = [part.strip() for part in match_name.split(" - ", 1)]
            league_parts = [str(event.get("p") or "").strip(), str(event.get("s") or "").strip()]
            league = " / ".join([p for p in league_parts if p]) or None
            kickoff_utc = self._parse_dt(event.get("h"))

            for selection, odds in self._extract_1x2_market_odds(event.get("bc")):
                quotes.append(
                    OddsQuote(
                        source=self.source,
                        sport=sport,
                        league=league,
                        external_event_id=event_id,
                        home_team=home_team,
                        away_team=away_team,
                        kickoff_utc=kickoff_utc,
                        market_type="1x2",
                        selection=selection,
                        odds_decimal=odds,
                        scraped_at=now,
                    )
                )
        return quotes

    def _extract_1x2_market_odds(self, markets: Any) -> list[tuple[str, Decimal]]:
        if not isinstance(markets, list):
            return []
        for market in markets:
            if not isinstance(market, dict):
                continue
            market_id = str(market.get("a") or "")
            market_name = str(market.get("b") or "").lower()
            if market_id != "00001" and not market_name.startswith("redni"):
                continue
            options = market.get("k")
            if not isinstance(options, list):
                continue

            out: list[tuple[str, Decimal]] = []
            for option in options:
                if not isinstance(option, dict):
                    continue
                selection = self._map_selection(option)
                if not selection:
                    continue
                try:
                    odds = Decimal(str(option.get("a")))
                except Exception:
                    continue
                if odds <= 1:
                    continue
                out.append((selection, odds))
            if out:
                return out
        return []

    def _map_selection(self, option: dict[str, Any]) -> str | None:
        c_val = str(option.get("c") or "").strip().lower()
        b_val = str(option.get("b") or "").strip().upper()
        if c_val in {"1", "home"} or b_val == "A":
            return "home"
        if c_val in {"0", "x", "draw"} or b_val == "B":
            return "draw"
        if c_val in {"2", "away"} or b_val == "C":
            return "away"
        return None

    def _parse_dt(self, value: Any) -> datetime | None:
        if value is None:
            return None
        try:
            parsed = dt_parser.parse(str(value))
            if parsed.tzinfo:
                return parsed.astimezone(timezone.utc)
            return parsed.replace(tzinfo=timezone.utc)
        except Exception:
            return None
