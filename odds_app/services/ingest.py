from datetime import timedelta
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from odds_app.config import get_settings
from odds_app.models import Alert, OddsSnapshot
from odds_app.scrapers.base import OddsQuote


def _pct_drop(old: Decimal, new: Decimal) -> float:
    if old <= 0:
        return 0.0
    return float(((old - new) / old) * Decimal(100))


def _recent_drop_alert_exists(db: Session, quote: OddsQuote, cooldown_min: int) -> bool:
    cooldown_from = quote.scraped_at - timedelta(minutes=cooldown_min)
    stmt = (
        select(Alert.id)
        .where(Alert.alert_type == "odds_drop")
        .where(Alert.source == quote.source)
        .where(Alert.market_type == quote.market_type)
        .where(Alert.selection == quote.selection)
        .where(Alert.home_team == quote.home_team)
        .where(Alert.away_team == quote.away_team)
        .where(Alert.created_at >= cooldown_from)
        .limit(1)
    )
    return db.scalar(stmt) is not None


def persist_quotes_and_detect_drops(db: Session, quotes: list[OddsQuote]) -> int:
    settings = get_settings()
    created_alerts = 0

    for quote in quotes:
        prev_stmt = (
            select(OddsSnapshot)
            .where(OddsSnapshot.source == quote.source)
            .where(OddsSnapshot.external_event_id == quote.external_event_id)
            .where(OddsSnapshot.market_type == quote.market_type)
            .where(OddsSnapshot.selection == quote.selection)
            .where(
                OddsSnapshot.scraped_at
                >= quote.scraped_at - timedelta(minutes=settings.odds_drop_lookback_min)
            )
            .where(OddsSnapshot.scraped_at < quote.scraped_at)
            .order_by(desc(OddsSnapshot.scraped_at))
            .limit(1)
        )
        previous = db.scalar(prev_stmt)

        snapshot = OddsSnapshot(
            source=quote.source,
            sport=quote.sport,
            league=quote.league,
            external_event_id=quote.external_event_id,
            home_team=quote.home_team,
            away_team=quote.away_team,
            kickoff_utc=quote.kickoff_utc,
            market_type=quote.market_type,
            selection=quote.selection,
            odds_decimal=quote.odds_decimal,
            scraped_at=quote.scraped_at,
        )
        db.add(snapshot)

        if previous and quote.odds_decimal < previous.odds_decimal:
            drop_pct = _pct_drop(previous.odds_decimal, quote.odds_decimal)
            if (
                drop_pct >= settings.odds_drop_threshold_pct
                and not _recent_drop_alert_exists(db, quote, settings.alert_cooldown_min)
            ):
                msg = (
                    f"[ODDS DROP] {quote.home_team} vs {quote.away_team} | "
                    f"{quote.market_type}:{quote.selection} {previous.odds_decimal} -> "
                    f"{quote.odds_decimal} ({drop_pct:.2f}% drop) on {quote.source}"
                )
                alert = Alert(
                    alert_type="odds_drop",
                    source=quote.source,
                    sport=quote.sport,
                    market_type=quote.market_type,
                    selection=quote.selection,
                    home_team=quote.home_team,
                    away_team=quote.away_team,
                    kickoff_utc=quote.kickoff_utc,
                    message=msg,
                    details={
                        "previous_odds": str(previous.odds_decimal),
                        "current_odds": str(quote.odds_decimal),
                        "drop_pct": round(drop_pct, 4),
                        "external_event_id": quote.external_event_id,
                    },
                )
                db.add(alert)
                created_alerts += 1

    db.commit()
    return created_alerts
