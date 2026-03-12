from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import desc, select, tuple_
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


def _downsample(values: list[float], max_points: int) -> list[float]:
    if max_points <= 0:
        return []
    if len(values) <= max_points:
        return values
    if max_points == 1:
        return [values[-1]]

    step = (len(values) - 1) / (max_points - 1)
    sampled: list[float] = []
    used: set[int] = set()
    for i in range(max_points):
        idx = int(round(i * step))
        idx = max(0, min(idx, len(values) - 1))
        if idx in used:
            continue
        sampled.append(values[idx])
        used.add(idx)
    if sampled[-1] != values[-1]:
        sampled[-1] = values[-1]
    return sampled


def get_overlap_home_trends(
    db: Session,
    canonical_match_ids: list[int],
    hours: int = 72,
    max_points: int = 18,
    sources: tuple[str, str] = DEFAULT_COMPARISON_SOURCES,
) -> list[dict]:
    if not canonical_match_ids:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, hours))
    source_events = list(
        db.scalars(
            select(SourceEvent)
            .where(SourceEvent.canonical_match_id.in_(canonical_match_ids))
            .where(SourceEvent.source.in_(list(sources)))
            .order_by(SourceEvent.last_seen_at.desc())
        )
    )

    latest_by_match_source: dict[tuple[int, str], SourceEvent] = {}
    for event in source_events:
        key = (event.canonical_match_id, event.source)
        if key not in latest_by_match_source:
            latest_by_match_source[key] = event

    pair_to_match: dict[tuple[str, str], int] = {}
    for (match_id, source), event in latest_by_match_source.items():
        pair_to_match[(source, event.external_event_id)] = match_id

    pairs = list(pair_to_match.keys())
    grouped: dict[tuple[int, str], list[float]] = {}
    if pairs:
        snapshots = db.scalars(
            select(OddsSnapshot)
            .where(tuple_(OddsSnapshot.source, OddsSnapshot.external_event_id).in_(pairs))
            .where(OddsSnapshot.market_type == "1x2")
            .where(OddsSnapshot.selection == "home")
            .where(OddsSnapshot.scraped_at >= cutoff)
            .order_by(OddsSnapshot.scraped_at.asc())
        )
        for snap in snapshots:
            match_id = pair_to_match.get((snap.source, snap.external_event_id))
            if match_id is None:
                continue
            grouped.setdefault((match_id, snap.source), []).append(float(snap.odds_decimal))

    output: list[dict] = []
    for match_id in canonical_match_ids:
        output.append(
            {
                "canonical_match_id": match_id,
                "ps3838_home": _downsample(grouped.get((match_id, sources[0]), []), max_points),
                "estave_home": _downsample(grouped.get((match_id, sources[1]), []), max_points),
            }
        )
    return output


def get_match_odds_snapshots(
    db: Session,
    canonical_match_id: int,
    hours: int = 0,
    sources: tuple[str, str] = DEFAULT_COMPARISON_SOURCES,
) -> dict:
    canonical = db.get(CanonicalMatch, canonical_match_id)
    if not canonical:
        raise ValueError("canonical match not found")

    source_events = list(
        db.scalars(
            select(SourceEvent)
            .where(SourceEvent.canonical_match_id == canonical_match_id)
            .where(SourceEvent.source.in_(list(sources)))
            .order_by(SourceEvent.last_seen_at.desc())
        )
    )

    pairs = list({(event.source, event.external_event_id) for event in source_events})
    snapshots: list[OddsSnapshot] = []
    if pairs:
        stmt = (
            select(OddsSnapshot)
            .where(tuple_(OddsSnapshot.source, OddsSnapshot.external_event_id).in_(pairs))
            .where(OddsSnapshot.market_type == "1x2")
            .where(OddsSnapshot.selection.in_(list(SELECTION_ORDER)))
        )
        if hours > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            stmt = stmt.where(OddsSnapshot.scraped_at >= cutoff)
        stmt = stmt.order_by(
            OddsSnapshot.scraped_at.asc(),
            OddsSnapshot.source.asc(),
            OddsSnapshot.selection.asc(),
        )
        snapshots = list(db.scalars(stmt))

    return {
        "canonical_match_id": canonical.id,
        "sport": canonical.sport,
        "home_team": canonical.display_home_team,
        "away_team": canonical.display_away_team,
        "kickoff_utc": canonical.kickoff_bucket_utc,
        "snapshots": [
            {
                "source": snap.source,
                "external_event_id": snap.external_event_id,
                "market_type": snap.market_type,
                "selection": snap.selection,
                "odds_decimal": Decimal(snap.odds_decimal),
                "scraped_at": snap.scraped_at,
                "league": snap.league,
            }
            for snap in snapshots
        ],
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
