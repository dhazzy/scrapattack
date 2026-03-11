import json
import logging
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dt_parser

from odds_app.scrapers.base import OddsQuote

logger = logging.getLogger(__name__)

HOME_KEYS = ["home", "homeTeam", "home_team", "team1", "host", "h"]
AWAY_KEYS = ["away", "awayTeam", "away_team", "team2", "guest", "a"]
LEAGUE_KEYS = ["league", "leagueName", "competition", "tournament"]
EVENT_KEYS = ["eventId", "event_id", "matchId", "fixtureId", "id"]
KICKOFF_KEYS = ["kickoff", "startsAt", "startTime", "eventTime", "start_date", "date"]
HOME_ODDS_KEYS = ["homeOdds", "home_odds", "oddsHome", "priceHome", "hOdds"]


def _safe_get(node: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in node and node[key] not in (None, ""):
            return node[key]
    return None


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        try:
            dt = dt_parser.parse(value)
            if not dt.tzinfo:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None
    return None


def _to_decimal(value: Any) -> Decimal | None:
    try:
        if value is None:
            return None
        dec = Decimal(str(value))
        if dec <= 1:
            return None
        return dec
    except Exception:
        return None


def _walk_json_nodes(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for sub in value.values():
            yield from _walk_json_nodes(sub)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json_nodes(item)


def _extract_quotes_from_json_blob(source: str, payload: Any, now: datetime) -> list[OddsQuote]:
    quotes: list[OddsQuote] = []
    seen_ids: set[tuple[str, str]] = set()
    for node in _walk_json_nodes(payload):
        home = _safe_get(node, HOME_KEYS)
        away = _safe_get(node, AWAY_KEYS)
        event_id = _safe_get(node, EVENT_KEYS)
        home_odds = _safe_get(node, HOME_ODDS_KEYS)
        if isinstance(node.get("odds"), dict):
            home_odds = node["odds"].get("home") or home_odds
        if not (home and away and event_id and home_odds):
            continue

        odds_value = _to_decimal(home_odds)
        if odds_value is None:
            continue
        event_id_str = str(event_id).strip()
        if not event_id_str:
            continue
        dedupe_key = (event_id_str, "home")
        if dedupe_key in seen_ids:
            continue
        seen_ids.add(dedupe_key)

        kickoff_utc = _parse_dt(_safe_get(node, KICKOFF_KEYS))
        league = _safe_get(node, LEAGUE_KEYS)
        quotes.append(
            OddsQuote(
                source=source,
                sport="soccer",
                league=str(league) if league else None,
                external_event_id=event_id_str,
                home_team=str(home).strip(),
                away_team=str(away).strip(),
                kickoff_utc=kickoff_utc,
                market_type="1x2",
                selection="home",
                odds_decimal=odds_value,
                scraped_at=now,
            )
        )
    return quotes


def _extract_json_from_script_tags(html: str) -> list[Any]:
    payloads: list[Any] = []
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script"):
        text = script.string or script.get_text(strip=False) or ""
        if not text.strip():
            continue
        cleaned = text.strip()
        if cleaned.startswith("{") or cleaned.startswith("["):
            try:
                payloads.append(json.loads(cleaned))
            except Exception:
                pass
        for match in re.findall(r"(\{.*\"home.*\"away.*\})", cleaned):
            try:
                payloads.append(json.loads(match))
            except Exception:
                continue
    return payloads


async def _fetch_page_html(url: str, timeout_sec: float) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        response = await client.get(url, headers=headers, follow_redirects=True)
        response.raise_for_status()
        return response.text


async def _collect_playwright_json_payloads(url: str) -> list[Any]:
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return []

    payloads: list[Any] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        async def _on_response(resp):
            ctype = (resp.headers.get("content-type") or "").lower()
            if "application/json" not in ctype and resp.request.resource_type not in {"xhr", "fetch"}:
                return
            try:
                payloads.append(await resp.json())
            except Exception:
                return

        page.on("response", _on_response)
        await page.goto(url, wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(3000)
        await context.close()
        await browser.close()
    return payloads


async def extract_live_quotes(
    source: str,
    url: str,
    timeout_sec: float = 30.0,
    enable_playwright: bool = False,
) -> list[OddsQuote]:
    now = datetime.now(timezone.utc)
    quotes: list[OddsQuote] = []

    if enable_playwright:
        try:
            payloads = await _collect_playwright_json_payloads(url)
            for payload in payloads:
                quotes.extend(_extract_quotes_from_json_blob(source, payload, now))
        except Exception as exc:
            logger.warning("Playwright extraction failed for %s: %s", source, exc)

    try:
        html = await _fetch_page_html(url, timeout_sec=timeout_sec)
        for payload in _extract_json_from_script_tags(html):
            quotes.extend(_extract_quotes_from_json_blob(source, payload, now))
    except Exception as exc:
        logger.warning("HTML extraction failed for %s: %s", source, exc)

    unique: dict[str, OddsQuote] = {}
    for quote in quotes:
        unique[quote.external_event_id] = quote
    return list(unique.values())
