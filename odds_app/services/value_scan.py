from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from odds_app.config import get_settings
from odds_app.models import Alert, CanonicalMatch, OddsSnapshot, SourceEvent


def _edge_pct(base_odds: Decimal, alt_odds: Decimal) -> float:
    if base_odds <= 0:
        return 0.0
    return float(((alt_odds - base_odds) / base_odds) * Decimal(100))


def _recent_value_alert_exists(
    db: Session, canonical_match_id: int, market_type: str, selection: str, cooldown_min: int
) -> bool:
    since = datetime.now(timezone.utc) - timedelta(minutes=cooldown_min)
    stmt = (
        select(Alert)
        .where(Alert.alert_type == "value_edge")
        .where(Alert.market_type == market_type)
        .where(Alert.selection == selection)
        .where(Alert.created_at >= since)
        .order_by(Alert.created_at.desc())
        .limit(20)
    )
    candidates = list(db.scalars(stmt))
    for candidate in candidates:
        if int(candidate.details.get("canonical_match_id", -1)) == canonical_match_id:
            return True
    return False


def scan_value_edges(db: Session) -> int:
    settings = get_settings()
    since = datetime.now(timezone.utc) - timedelta(minutes=90)

    source_events = list(db.scalars(select(SourceEvent)))
    event_map = {(item.source, item.external_event_id): item for item in source_events}
    if not event_map:
        return 0

    stmt = (
        select(OddsSnapshot)
        .where(OddsSnapshot.source.in_(["ps3838", "e_stave"]))
        .where(OddsSnapshot.scraped_at >= since)
        .order_by(OddsSnapshot.scraped_at.desc())
    )
    snapshots = list(db.scalars(stmt))

    latest: dict[tuple[int, str, str], dict[str, OddsSnapshot]] = {}
    for snap in snapshots:
        source_event = event_map.get((snap.source, snap.external_event_id))
        if not source_event:
            continue
        key = (source_event.canonical_match_id, snap.market_type, snap.selection)
        src_map = latest.setdefault(key, {})
        if snap.source not in src_map:
            src_map[snap.source] = snap

    created_alerts = 0
    for (canonical_match_id, market_type, selection), src_map in latest.items():
        ps = src_map.get("ps3838")
        es = src_map.get("e_stave")
        if not (ps and es):
            continue

        edge_pct = _edge_pct(ps.odds_decimal, es.odds_decimal)
        if edge_pct < settings.value_edge_threshold_pct:
            continue
        if _recent_value_alert_exists(
            db, canonical_match_id, market_type, selection, settings.alert_cooldown_min
        ):
            continue

        canonical = db.get(CanonicalMatch, canonical_match_id)
        home = canonical.display_home_team if canonical else ps.home_team
        away = canonical.display_away_team if canonical else ps.away_team
        sport = canonical.sport if canonical else ps.sport

        msg = (
            f"[VALUE EDGE] {home} vs {away} | {market_type}:{selection} "
            f"ps3838={ps.odds_decimal} vs e-stave={es.odds_decimal} (edge {edge_pct:.2f}%)"
        )
        alert = Alert(
            alert_type="value_edge",
            source="comparison",
            sport=sport,
            market_type=market_type,
            selection=selection,
            home_team=home,
            away_team=away,
            kickoff_utc=ps.kickoff_utc,
            message=msg,
            details={
                "canonical_match_id": canonical_match_id,
                "ps3838_odds": str(ps.odds_decimal),
                "e_stave_odds": str(es.odds_decimal),
                "edge_pct": round(edge_pct, 4),
                "ps3838_event_id": ps.external_event_id,
                "e_stave_event_id": es.external_event_id,
            },
        )
        db.add(alert)
        created_alerts += 1

    db.commit()
    return created_alerts
