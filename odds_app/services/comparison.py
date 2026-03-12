from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from odds_app.constants import DEFAULT_COMPARISON_SOURCES
from odds_app.models import CanonicalMatch, OddsSnapshot, SourceEvent
from odds_app.scrapers.base import OddsQuote
from odds_app.services.match_views import list_overlap_matches
from odds_app.services.matching import resolve_source_event_mapping
from odds_app.services.value_scan import scan_value_edges

SELECTION_ORDER = ("home", "draw", "away")
SELECTION_LABEL = {"home": "Home", "draw": "Draw", "away": "Away"}


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


def get_match_odds_history(
    db: Session,
    canonical_match_id: int,
    hours: int = 240,
    sources: tuple[str, str] = DEFAULT_COMPARISON_SOURCES,
) -> dict:
    canonical = db.get(CanonicalMatch, canonical_match_id)
    if not canonical:
        raise ValueError("canonical match not found")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, hours))
    source_events = list(
        db.scalars(
            select(SourceEvent)
            .where(SourceEvent.canonical_match_id == canonical_match_id)
            .where(SourceEvent.source.in_(list(sources)))
            .order_by(SourceEvent.last_seen_at.desc())
        )
    )

    latest_event_by_source: dict[str, SourceEvent] = {}
    for event in source_events:
        if event.source not in latest_event_by_source:
            latest_event_by_source[event.source] = event

    series: list[dict] = []
    for source, event in latest_event_by_source.items():
        snapshots = list(
            db.scalars(
                select(OddsSnapshot)
                .where(OddsSnapshot.source == source)
                .where(OddsSnapshot.external_event_id == event.external_event_id)
                .where(OddsSnapshot.market_type == "1x2")
                .where(OddsSnapshot.selection.in_(list(SELECTION_ORDER)))
                .where(OddsSnapshot.scraped_at >= cutoff)
                .order_by(OddsSnapshot.scraped_at.asc())
            )
        )
        grouped: dict[str, list[OddsSnapshot]] = {selection: [] for selection in SELECTION_ORDER}
        for snap in snapshots:
            if snap.selection in grouped:
                grouped[snap.selection].append(snap)

        for selection in SELECTION_ORDER:
            points = grouped[selection]
            if not points:
                continue
            series.append(
                {
                    "source": source,
                    "selection": selection,
                    "label": f"{source} {SELECTION_LABEL.get(selection, selection)}",
                    "points": [
                        {
                            "scraped_at": snap.scraped_at,
                            "odds_decimal": Decimal(snap.odds_decimal),
                        }
                        for snap in points
                    ],
                }
            )

    return {
        "canonical_match_id": canonical.id,
        "sport": canonical.sport,
        "home_team": canonical.display_home_team,
        "away_team": canonical.display_away_team,
        "kickoff_utc": canonical.kickoff_bucket_utc,
        "series": series,
    }
