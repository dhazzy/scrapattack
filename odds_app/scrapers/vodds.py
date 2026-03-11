import logging
from datetime import datetime, timezone
from typing import Any

from odds_app.scrapers.base import OddsQuote
from odds_app.scrapers.live_parser import extract_quotes_from_payload

logger = logging.getLogger(__name__)


SPORTS = ["Football", "Tennis", "Basketball"]


def _normalize_sport(label: str) -> str:
    value = label.lower()
    if value == "football":
        return "soccer"
    if value in {"tennis", "basketball"}:
        return value
    return "soccer"


def _selection_normalize(value: str) -> str:
    val = value.strip().lower()
    if val in {"1", "home"}:
        return "home"
    if val in {"x", "draw", "0"}:
        return "draw"
    if val in {"2", "away"}:
        return "away"
    return val


def _extract_quotes_from_vodds_payload(payload: Any, sport_label: str) -> list[OddsQuote]:
    raw = extract_quotes_from_payload(source="ps3838", payload=payload, now=datetime.now(timezone.utc))
    sport = _normalize_sport(sport_label)
    quotes: list[OddsQuote] = []
    for quote in raw:
        quote.sport = sport
        quote.selection = _selection_normalize(quote.selection)
        quotes.append(quote)
    return quotes


async def scrape_ps3838_from_vodds(
    dashboard_url: str,
    username: str,
    password: str,
    headless: bool = True,
    timeout_sec: float = 60.0,
) -> list[OddsQuote]:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        logger.warning("Playwright not available for Vodds scraper: %s", exc)
        return []

    all_quotes: list[OddsQuote] = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()

            payloads_by_sport: dict[str, list[Any]] = {sport: [] for sport in SPORTS}
            active_sport = {"value": "Football"}

            async def on_response(resp):
                ctype = (resp.headers.get("content-type") or "").lower()
                if "application/json" not in ctype and resp.request.resource_type not in {"xhr", "fetch"}:
                    return
                try:
                    payload = await resp.json()
                except Exception:
                    return
                payloads_by_sport.setdefault(active_sport["value"], []).append(payload)

            page.on("response", on_response)

            await page.goto(dashboard_url, wait_until="domcontentloaded", timeout=int(timeout_sec * 1000))
            await page.wait_for_timeout(1500)

            # Login if login form is present.
            password_loc = page.locator('input[type="password"]')
            if await password_loc.count() > 0:
                user_loc = page.locator('input[type="email"], input[name="email"], input[name="username"], input[type="text"]')
                if await user_loc.count() > 0:
                    await user_loc.first.fill(username)
                    await password_loc.first.fill(password)
                    for label in ["Login", "Sign In", "Log In", "Submit"]:
                        btn = page.get_by_role("button", name=label)
                        if await btn.count() > 0:
                            await btn.first.click()
                            break
                    await page.wait_for_timeout(5000)

            for sport in SPORTS:
                active_sport["value"] = sport
                sport_loc = page.get_by_text(sport, exact=False)
                if await sport_loc.count() == 0:
                    continue
                await sport_loc.first.click()
                await page.wait_for_timeout(1200)
                early_loc = page.get_by_text("EARLY", exact=False)
                if await early_loc.count() > 0:
                    await early_loc.first.click()
                    await page.wait_for_timeout(1500)

            await page.wait_for_timeout(3000)
            await context.close()
            await browser.close()

            seen: set[tuple[str, str, str]] = set()
            for sport, payloads in payloads_by_sport.items():
                for payload in payloads:
                    for quote in _extract_quotes_from_vodds_payload(payload, sport):
                        key = (quote.external_event_id, quote.market_type, quote.selection)
                        if key in seen:
                            continue
                        seen.add(key)
                        all_quotes.append(quote)
    except Exception as exc:
        logger.warning("Vodds scraping failed: %s", exc)
        return []

    return all_quotes
