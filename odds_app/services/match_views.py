from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from odds_app.models import CanonicalMatch, OddsSnapshot, SourceEvent
from odds_app.schemas import MatchSummaryResponse, SourceEventSummary


def list_recent_matches(db: Session, limit: int = 50) -> list[MatchSummaryResponse]:
    matches = list(
        db.scalars(select(CanonicalMatch).order_by(desc(CanonicalMatch.updated_at)).limit(limit))
    )
    if not matches:
        return []

    match_ids = [match.id for match in matches]
    source_events = list(
        db.scalars(select(SourceEvent).where(SourceEvent.canonical_match_id.in_(match_ids)))
    )

    latest_odds: dict[tuple[str, str], tuple[object, object]] = {}
    for event in source_events:
        snap_stmt = (
            select(OddsSnapshot)
            .where(OddsSnapshot.source == event.source)
            .where(OddsSnapshot.external_event_id == event.external_event_id)
            .where(OddsSnapshot.market_type == "1x2")
            .where(OddsSnapshot.selection == "home")
            .order_by(desc(OddsSnapshot.scraped_at))
            .limit(1)
        )
        snap = db.scalar(snap_stmt)
        if snap:
            latest_odds[(event.source, event.external_event_id)] = (
                snap.odds_decimal,
                snap.scraped_at,
            )

    by_match: dict[int, list[SourceEventSummary]] = {mid: [] for mid in match_ids}
    for event in source_events:
        odds, scraped_at = latest_odds.get((event.source, event.external_event_id), (None, None))
        by_match[event.canonical_match_id].append(
            SourceEventSummary(
                source=event.source,
                external_event_id=event.external_event_id,
                league=event.league,
                latest_home_odds=odds,
                last_scraped_at=scraped_at,
            )
        )

    result: list[MatchSummaryResponse] = []
    for match in matches:
        result.append(
            MatchSummaryResponse(
                match_id=match.id,
                home_team=match.display_home_team,
                away_team=match.display_away_team,
                kickoff_bucket_utc=match.kickoff_bucket_utc,
                source_events=by_match.get(match.id, []),
                updated_at=match.updated_at,
            )
        )
    return result
