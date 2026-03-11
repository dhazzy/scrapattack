from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from odds_app.config import get_settings
from odds_app.models import Alert, OddsSnapshot
from odds_app.utils.normalize import canonical_match_key


def _edge_pct(base_odds: Decimal, alt_odds: Decimal) -> float:
    if base_odds <= 0:
        return 0.0
    return float(((alt_odds - base_odds) / base_odds) * Decimal(100))


def _kickoff_bucket(value: datetime | None) -> str:
    if value is None:
        return "unknown"
    minute_bucket = (value.minute // 15) * 15
    return value.replace(minute=minute_bucket, second=0, microsecond=0).isoformat()


def _recent_value_alert_exists(
    db: Session, home: str, away: str, market_type: str, selection: str, cooldown_min: int
) -> bool:
    since = datetime.now(timezone.utc) - timedelta(minutes=cooldown_min)
    stmt = (
        select(Alert.id)
        .where(Alert.alert_type == "value_edge")
        .where(Alert.home_team == home)
        .where(Alert.away_team == away)
        .where(Alert.market_type == market_type)
        .where(Alert.selection == selection)
        .where(Alert.created_at >= since)
        .limit(1)
    )
    return db.scalar(stmt) is not None


def scan_value_edges(db: Session) -> int:
    settings = get_settings()
    since = datetime.now(timezone.utc) - timedelta(minutes=90)
    stmt = (
        select(OddsSnapshot)
        .where(OddsSnapshot.sport == "soccer")
        .where(OddsSnapshot.source.in_(["ps3838", "e_stave"]))
        .where(OddsSnapshot.scraped_at >= since)
        .order_by(OddsSnapshot.scraped_at.desc())
    )
    snapshots = list(db.scalars(stmt))

    latest: dict[tuple[str, str, str, str, str], dict[str, OddsSnapshot]] = {}
    for snap in snapshots:
        home, away = canonical_match_key(snap.home_team, snap.away_team)
        key = (home, away, snap.market_type, snap.selection, _kickoff_bucket(snap.kickoff_utc))
        src_map = latest.setdefault(key, {})
        if snap.source not in src_map:
            src_map[snap.source] = snap

    created_alerts = 0
    for _, src_map in latest.items():
        ps = src_map.get("ps3838")
        es = src_map.get("e_stave")
        if not (ps and es):
            continue

        edge_pct = _edge_pct(ps.odds_decimal, es.odds_decimal)
        if edge_pct < settings.value_edge_threshold_pct:
            continue

        if _recent_value_alert_exists(
            db, ps.home_team, ps.away_team, ps.market_type, ps.selection, settings.alert_cooldown_min
        ):
            continue

        msg = (
            f"[VALUE EDGE] {ps.home_team} vs {ps.away_team} | {ps.market_type}:{ps.selection} "
            f"ps3838={ps.odds_decimal} vs e-stave={es.odds_decimal} (edge {edge_pct:.2f}%)"
        )
        alert = Alert(
            alert_type="value_edge",
            source="comparison",
            sport="soccer",
            market_type=ps.market_type,
            selection=ps.selection,
            home_team=ps.home_team,
            away_team=ps.away_team,
            kickoff_utc=ps.kickoff_utc,
            message=msg,
            details={
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
