from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from odds_app.constants import DEFAULT_COMPARISON_SOURCES
from odds_app.models import OddsSnapshot
from odds_app.scrapers.base import OddsQuote
from odds_app.services.match_views import list_overlap_matches
from odds_app.services.matching import resolve_source_event_mapping
from odds_app.services.value_scan import scan_value_edges


def reconcile_match_mappings(db: Session, sources: tuple[str, str] = DEFAULT_COMPARISON_SOURCES) -> int:
    """Rebuild canonical/source mappings from latest snapshots per source event."""
    stmt = (
        select(OddsSnapshot)
        .where(OddsSnapshot.source.in_(sources))
        .order_by(desc(OddsSnapshot.scraped_at))
    )
    latest_by_event: dict[tuple[str, str], OddsSnapshot] = {}
    for snap in db.scalars(stmt):
        key = (snap.source, snap.external_event_id)
        if key not in latest_by_event:
            latest_by_event[key] = snap

    for snap in latest_by_event.values():
        resolve_source_event_mapping(
            db,
            OddsQuote(
                source=snap.source,
                sport=snap.sport,
                league=snap.league,
                external_event_id=snap.external_event_id,
                home_team=snap.home_team,
                away_team=snap.away_team,
                kickoff_utc=snap.kickoff_utc,
                market_type=snap.market_type,
                selection=snap.selection,
                odds_decimal=snap.odds_decimal,
                scraped_at=snap.scraped_at,
            ),
        )

    db.commit()
    return len(latest_by_event)


def run_match_comparison_cycle(
    db: Session, overlap_limit: int = 200, sources: tuple[str, str] = DEFAULT_COMPARISON_SOURCES
) -> dict:
    reconciled_events = reconcile_match_mappings(db, sources=sources)
    overlap_matches = len(list_overlap_matches(db, limit=overlap_limit))
    value_edge_alerts = scan_value_edges(db)
    return {
        "reconciled_events": reconciled_events,
        "overlap_matches": overlap_matches,
        "value_edge_alerts": value_edge_alerts,
    }
