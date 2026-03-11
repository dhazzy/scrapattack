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
                "appVer": 1,
                "serviceVer": 2,
                "serviceType": "sencha",
                "appUUID": app_uuid,
                "CSRFToken": csrf_token,
                "appSig": "",
                "appKey": "mobileestave",
            }

            payload = await self._request_stave_payload(client, service_endpoint, headers, common)
            if not payload:
                return []
            quotes = self._quotes_from_stave_payload(payload, now)
            if not quotes:
                booster = await self._request_bet_booster(client, service_endpoint, headers, common)
                quotes = self._quotes_from_bet_booster(booster, now)
            return quotes

    async def _request_stave_payload(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        headers: dict[str, str],
        common: dict[str, Any],
    ) -> dict[str, Any] | None:
        candidates = [
            {"a": 3, "b": 4, "d": 0, "f": 1, "g": 25, "i": "false", "l": "", "n": 10},
            {"a": 3, "d": 1, "f": 1, "g": 25, "l": ""},
        ]
        for extra in candidates:
            params = {"controller": "stave", "action": "stave", **extra, **common}
            resp = await client.get(endpoint, headers=headers, params=params)
            if resp.status_code >= 400:
                continue
            payload = resp.json()
            if isinstance(payload, dict) and payload.get("success") is True and payload.get("data"):
                return payload
        return None

    async def _request_bet_booster(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        headers: dict[str, str],
        common: dict[str, Any],
    ) -> dict[str, Any] | None:
        params = {"controller": "stave", "action": "betBooster", "b": 0, **common}
        resp = await client.get(endpoint, headers=headers, params=params)
        if resp.status_code >= 400:
            return None
        data = resp.json()
        return data if isinstance(data, dict) and data.get("success") is True else None

    def _quotes_from_stave_payload(self, payload: dict[str, Any], now: datetime) -> list[OddsQuote]:
        data = payload.get("data") or {}
        events = data.get("bb") if isinstance(data, dict) else None
        if not isinstance(events, list):
            return []
        quotes: list[OddsQuote] = []
        seen: set[str] = set()
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
            home_odds = self._extract_home_odds_from_markets(event.get("bc"))
            if home_odds is None or event_id in seen:
                continue
            seen.add(event_id)
            quotes.append(
                OddsQuote(
                    source=self.source,
                    sport="soccer",
                    league=league,
                    external_event_id=event_id,
                    home_team=home_team,
                    away_team=away_team,
                    kickoff_utc=kickoff_utc,
                    market_type="1x2",
                    selection="home",
                    odds_decimal=home_odds,
                    scraped_at=now,
                )
            )
        return quotes

    def _extract_home_odds_from_markets(self, markets: Any) -> Decimal | None:
        if not isinstance(markets, list):
            return None
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
            for option in options:
                if not isinstance(option, dict):
                    continue
                if str(option.get("c")) != "1" and str(option.get("b")) != "A":
                    continue
                try:
                    odds = Decimal(str(option.get("a")))
                    if odds > 1:
                        return odds
                except Exception:
                    continue
        return None

    def _quotes_from_bet_booster(self, payload: dict[str, Any] | None, now: datetime) -> list[OddsQuote]:
        if not payload:
            return []
        items = payload.get("items")
        if not isinstance(items, list):
            return []
        quotes: list[OddsQuote] = []
        seen: set[str] = set()
        for group in items:
            for event in (group.get("e") or []) if isinstance(group, dict) else []:
                if not isinstance(event, dict):
                    continue
                event_id = str(event.get("a") or "").strip()
                match = str(event.get("b") or "").strip()
                if not event_id or " - " not in match:
                    continue
                home_team, away_team = [part.strip() for part in match.split(" - ", 1)]
                try:
                    odds = Decimal(str(event.get("c")))
                except Exception:
                    continue
                if odds <= 1 or event_id in seen:
                    continue
                seen.add(event_id)
                quotes.append(
                    OddsQuote(
                        source=self.source,
                        sport="soccer",
                        league=str(event.get("d") or "").strip() or None,
                        external_event_id=event_id,
                        home_team=home_team,
                        away_team=away_team,
                        kickoff_utc=None,
                        market_type="1x2",
                        selection="home",
                        odds_decimal=odds,
                        scraped_at=now,
                    )
                )
        return quotes

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
