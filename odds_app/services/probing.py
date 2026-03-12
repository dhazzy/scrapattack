from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from odds_app.config import get_settings
from odds_app.scrapers.base import OddsQuote
from odds_app.scrapers.estave import EStaveScraper
from odds_app.scrapers.vodds import scrape_ps3838_from_vodds
from odds_app.services.horizons import filter_quotes_by_horizon, summarize_horizons


def _normalize_sports(raw: list[str] | tuple[str, ...] | None) -> set[str] | None:
    if not raw:
        return None
    sports = {str(item).strip().lower() for item in raw if str(item).strip()}
    return sports or None


def _filter_for_probe(
    quotes: list[OddsQuote],
    *,
    sports: set[str] | None,
    min_days: float,
    max_days: float,
) -> list[OddsQuote]:
    filtered = filter_quotes_by_horizon(
        quotes,
        min_hours=max(0.0, float(min_days)) * 24.0,
        max_hours=max(0.0, float(max_days)) * 24.0 if max_days > 0 else None,
        require_kickoff=True,
    )
    if sports is None:
        return filtered
    return [quote for quote in filtered if quote.sport.strip().lower() in sports]


def _sample_events(quotes: list[OddsQuote], limit: int = 15) -> list[dict]:
    rows = sorted(
        quotes,
        key=lambda quote: (
            quote.kickoff_utc or datetime.max.replace(tzinfo=timezone.utc),
            quote.sport,
            quote.home_team,
            quote.away_team,
        ),
    )
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for quote in rows:
        key = (quote.sport, quote.external_event_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "sport": quote.sport,
                "league": quote.league,
                "home_team": quote.home_team,
                "away_team": quote.away_team,
                "kickoff_utc": quote.kickoff_utc.isoformat() if quote.kickoff_utc else None,
                "external_event_id": quote.external_event_id,
            }
        )
        if len(out) >= limit:
            break
    return out


async def probe_estave_scrape(
    *,
    sports: list[str] | None = None,
    min_days: float = 0.0,
    max_days: float = 14.0,
    max_pages_per_query: int | None = None,
    page_size: int | None = None,
    g_values: str | None = None,
    extra_b_values: str | None = None,
) -> tuple[list[OddsQuote], dict]:
    scraper = EStaveScraper()
    scraper.settings = scraper.settings.model_copy(deep=True)
    applied: dict[str, Any] = {}

    if max_pages_per_query is not None:
        scraper.settings.estave_max_pages_per_query = max(1, int(max_pages_per_query))
        applied["estave_max_pages_per_query"] = scraper.settings.estave_max_pages_per_query
    if page_size is not None:
        scraper.settings.estave_page_size = max(1, int(page_size))
        applied["estave_page_size"] = scraper.settings.estave_page_size
    if g_values is not None:
        scraper.settings.estave_g_values = str(g_values)
        applied["estave_g_values"] = scraper.settings.estave_g_values
    if extra_b_values is not None:
        scraper.settings.estave_extra_b_values = str(extra_b_values)
        applied["estave_extra_b_values"] = scraper.settings.estave_extra_b_values

    raw_quotes = await scraper.scrape_soccer()
    target_sports = _normalize_sports(sports)
    filtered = _filter_for_probe(
        raw_quotes,
        sports=target_sports,
        min_days=min_days,
        max_days=max_days,
    )
    summary = summarize_horizons(filtered)
    summary.update(
        {
            "source": scraper.source,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_days": {"min_days": min_days, "max_days": max_days},
            "sports_filter": sorted(target_sports) if target_sports else None,
            "raw_quotes_total": len(raw_quotes),
            "filtered_quotes_total": len(filtered),
            "applied_overrides": applied,
            "sample_events": _sample_events(filtered),
        }
    )
    return filtered, summary


async def probe_vodds_scrape(
    *,
    sports: list[str] | None = None,
    min_days: float = 0.0,
    max_days: float = 14.0,
    timeout_sec: float | None = None,
    headless: bool | None = None,
    proxy_url: str | None = None,
) -> tuple[list[OddsQuote], dict]:
    settings = get_settings()
    if not settings.vodds_username or not settings.vodds_password:
        raise ValueError("vodds credentials are not configured")

    actual_timeout = float(timeout_sec) if timeout_sec is not None else settings.vodds_timeout_sec
    actual_headless = bool(headless) if headless is not None else settings.vodds_headless
    actual_proxy = proxy_url or settings.vodds_proxy_url or settings.ps3838_proxy_url or None

    raw_quotes = await scrape_ps3838_from_vodds(
        dashboard_url=settings.vodds_dashboard_url,
        username=settings.vodds_username,
        password=settings.vodds_password,
        headless=actual_headless,
        timeout_sec=actual_timeout,
        proxy_url=actual_proxy,
    )
    target_sports = _normalize_sports(sports)
    filtered = _filter_for_probe(
        raw_quotes,
        sports=target_sports,
        min_days=min_days,
        max_days=max_days,
    )
    summary = summarize_horizons(filtered)
    summary.update(
        {
            "source": "ps3838",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_days": {"min_days": min_days, "max_days": max_days},
            "sports_filter": sorted(target_sports) if target_sports else None,
            "raw_quotes_total": len(raw_quotes),
            "filtered_quotes_total": len(filtered),
            "applied_overrides": {
                "headless": actual_headless,
                "timeout_sec": actual_timeout,
                "proxy_url_configured": bool(actual_proxy),
            },
            "sample_events": _sample_events(filtered),
        }
    )
    return filtered, summary

