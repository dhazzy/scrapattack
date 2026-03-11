from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from odds_app.models import CanonicalMatch, OddsSnapshot, SourceEvent
from odds_app.schemas import (
    MatchSummaryResponse,
    OverlapMatchRow,
    SourceEventSummary,
    SourceMatchRow,
)


def _latest_home_snapshot(
    db: Session, source: str, external_event_id: str
) -> tuple[Decimal | None, object | None]:
    stmt = (
        select(OddsSnapshot)
        .where(OddsSnapshot.source == source)
        .where(OddsSnapshot.external_event_id == external_event_id)
        .where(OddsSnapshot.market_type == "1x2")
        .where(OddsSnapshot.selection == "home")
        .order_by(desc(OddsSnapshot.scraped_at))
        .limit(1)
    )
    snap = db.scalar(stmt)
    if not snap:
        return None, None
    return snap.odds_decimal, snap.scraped_at


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

    by_match: dict[int, list[SourceEventSummary]] = {mid: [] for mid in match_ids}
    for event in source_events:
        odds, scraped_at = _latest_home_snapshot(db, event.source, event.external_event_id)
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


def list_source_matches(db: Session, source: str, limit: int = 100) -> list[SourceMatchRow]:
    events = list(
        db.scalars(
            select(SourceEvent)
            .where(SourceEvent.source == source)
            .order_by(desc(SourceEvent.last_seen_at))
            .limit(limit)
        )
    )
    rows: list[SourceMatchRow] = []
    for event in events:
        canonical = db.get(CanonicalMatch, event.canonical_match_id)
        if not canonical:
            continue
        odds, scraped_at = _latest_home_snapshot(db, event.source, event.external_event_id)
        rows.append(
            SourceMatchRow(
                canonical_match_id=event.canonical_match_id,
                source=event.source,
                external_event_id=event.external_event_id,
                home_team=canonical.display_home_team,
                away_team=canonical.display_away_team,
                league=event.league,
                kickoff_utc=event.kickoff_utc,
                latest_home_odds=odds,
                last_scraped_at=scraped_at,
                updated_at=canonical.updated_at,
            )
        )
    return rows


def _edge_pct(ps_odds: Decimal | None, es_odds: Decimal | None) -> float | None:
    if ps_odds is None or es_odds is None:
        return None
    if ps_odds <= 0:
        return None
    return float(((es_odds - ps_odds) / ps_odds) * Decimal(100))


def _better_source(ps_odds: Decimal | None, es_odds: Decimal | None) -> str | None:
    if ps_odds is None or es_odds is None:
        return None
    if ps_odds > es_odds:
        return "ps3838"
    if es_odds > ps_odds:
        return "e_stave"
    return "equal"


def list_overlap_matches(db: Session, limit: int = 100) -> list[OverlapMatchRow]:
    canonical_rows = list(
        db.scalars(select(CanonicalMatch).order_by(desc(CanonicalMatch.updated_at)).limit(limit * 5))
    )
    output: list[OverlapMatchRow] = []

    for canonical in canonical_rows:
        events = list(
            db.scalars(
                select(SourceEvent)
                .where(SourceEvent.canonical_match_id == canonical.id)
                .where(SourceEvent.source.in_(["ps3838", "e_stave"]))
            )
        )
        by_source: dict[str, SourceEvent] = {}
        for event in events:
            existing = by_source.get(event.source)
            if not existing or event.last_seen_at > existing.last_seen_at:
                by_source[event.source] = event

        ps_event = by_source.get("ps3838")
        es_event = by_source.get("e_stave")
        if not (ps_event and es_event):
            continue

        ps_odds, _ = _latest_home_snapshot(db, "ps3838", ps_event.external_event_id)
        es_odds, _ = _latest_home_snapshot(db, "e_stave", es_event.external_event_id)
        output.append(
            OverlapMatchRow(
                canonical_match_id=canonical.id,
                home_team=canonical.display_home_team,
                away_team=canonical.display_away_team,
                kickoff_utc=canonical.kickoff_bucket_utc,
                ps3838_event_id=ps_event.external_event_id,
                estave_event_id=es_event.external_event_id,
                ps3838_home_odds=ps_odds,
                estave_home_odds=es_odds,
                edge_pct_estave_vs_ps3838=_edge_pct(ps_odds, es_odds),
                better_source=_better_source(ps_odds, es_odds),
                updated_at=canonical.updated_at,
            )
        )
        if len(output) >= limit:
            break

    return output
