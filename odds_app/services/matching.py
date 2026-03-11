from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from odds_app.models import CanonicalMatch, SourceEvent
from odds_app.scrapers.base import OddsQuote
from odds_app.utils.normalize import canonical_match_key


def kickoff_bucket(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    minute_bucket = (value.minute // 15) * 15
    return value.replace(minute=minute_bucket, second=0, microsecond=0)


def canonical_key_for_quote(quote: OddsQuote) -> str:
    home_norm, away_norm = canonical_match_key(quote.home_team, quote.away_team)
    bucket = kickoff_bucket(quote.kickoff_utc)
    bucket_part = bucket.isoformat() if bucket else "unknown"
    return f"{home_norm}|{away_norm}|{bucket_part}"


def reverse_canonical_key_for_quote(quote: OddsQuote) -> str:
    home_norm, away_norm = canonical_match_key(quote.home_team, quote.away_team)
    bucket = kickoff_bucket(quote.kickoff_utc)
    bucket_part = bucket.isoformat() if bucket else "unknown"
    return f"{away_norm}|{home_norm}|{bucket_part}"


def resolve_source_event_mapping(db: Session, quote: OddsQuote) -> CanonicalMatch:
    source_stmt = (
        select(SourceEvent)
        .where(SourceEvent.source == quote.source)
        .where(SourceEvent.external_event_id == quote.external_event_id)
        .limit(1)
    )
    source_event = db.scalar(source_stmt)

    if source_event:
        source_event.league = quote.league
        source_event.home_team = quote.home_team
        source_event.away_team = quote.away_team
        source_event.kickoff_utc = quote.kickoff_utc
        source_event.last_seen_at = quote.scraped_at
        db.add(source_event)
        canonical = db.get(CanonicalMatch, source_event.canonical_match_id)
        if canonical:
            canonical.display_home_team = quote.home_team
            canonical.display_away_team = quote.away_team
            canonical.kickoff_bucket_utc = kickoff_bucket(quote.kickoff_utc)
            db.add(canonical)
            db.flush()
            return canonical

    home_norm, away_norm = canonical_match_key(quote.home_team, quote.away_team)
    key = canonical_key_for_quote(quote)
    reverse_key = reverse_canonical_key_for_quote(quote)
    canonical_stmt = (
        select(CanonicalMatch)
        .where(CanonicalMatch.canonical_key.in_([key, reverse_key]))
        .limit(1)
    )
    canonical = db.scalar(canonical_stmt)
    if not canonical:
        canonical = CanonicalMatch(
            sport=quote.sport,
            canonical_key=key,
            home_team_norm=home_norm,
            away_team_norm=away_norm,
            display_home_team=quote.home_team,
            display_away_team=quote.away_team,
            kickoff_bucket_utc=kickoff_bucket(quote.kickoff_utc),
        )
        db.add(canonical)
        db.flush()

    if not source_event:
        source_event = SourceEvent(
            canonical_match_id=canonical.id,
            source=quote.source,
            external_event_id=quote.external_event_id,
            sport=quote.sport,
            league=quote.league,
            home_team=quote.home_team,
            away_team=quote.away_team,
            kickoff_utc=quote.kickoff_utc,
            first_seen_at=quote.scraped_at,
            last_seen_at=quote.scraped_at,
        )
    else:
        source_event.canonical_match_id = canonical.id
    db.add(source_event)
    db.flush()
    return canonical
