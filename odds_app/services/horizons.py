from __future__ import annotations

from datetime import timezone

from odds_app.scrapers.base import OddsQuote


def quote_horizon_hours(quote: OddsQuote) -> float | None:
    if quote.kickoff_utc is None:
        return None
    kickoff = quote.kickoff_utc
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)
    return (kickoff - quote.scraped_at).total_seconds() / 3600.0


def filter_quotes_by_horizon(
    quotes: list[OddsQuote],
    *,
    min_hours: float | None = None,
    max_hours: float | None = None,
    require_kickoff: bool = True,
) -> list[OddsQuote]:
    out: list[OddsQuote] = []
    for quote in quotes:
        horizon_hours = quote_horizon_hours(quote)
        if horizon_hours is None:
            if require_kickoff:
                continue
            out.append(quote)
            continue
        if min_hours is not None and horizon_hours < min_hours:
            continue
        if max_hours is not None and horizon_hours > max_hours:
            continue
        out.append(quote)
    return out


def summarize_horizons(
    quotes: list[OddsQuote],
    *,
    buckets_days: tuple[int, ...] = (1, 3, 7, 14),
) -> dict:
    sorted_days = sorted(set(int(day) for day in buckets_days if int(day) > 0))
    horizon_counts = {f"upcoming_le_{day}d": 0 for day in sorted_days}
    by_sport_counts: dict[str, int] = {}
    event_keys: set[tuple[str, str]] = set()
    no_kickoff = 0
    after_last_bucket = 0

    for quote in quotes:
        by_sport_counts[quote.sport] = by_sport_counts.get(quote.sport, 0) + 1
        event_keys.add((quote.sport, quote.external_event_id))
        horizon_hours = quote_horizon_hours(quote)
        if horizon_hours is None:
            no_kickoff += 1
            continue
        if horizon_hours < 0:
            continue
        matched = False
        for day in sorted_days:
            if horizon_hours <= day * 24:
                horizon_counts[f"upcoming_le_{day}d"] += 1
                matched = True
                break
        if not matched:
            after_last_bucket += 1

    return {
        "quotes_total": len(quotes),
        "unique_events": len(event_keys),
        "by_sport_quotes": by_sport_counts,
        "horizon_quote_counts": horizon_counts,
        "quotes_without_kickoff": no_kickoff,
        "quotes_after_last_bucket": after_last_bucket,
    }

