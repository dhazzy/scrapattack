from datetime import timedelta
from decimal import Decimal

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from odds_app.config import get_settings
from odds_app.models import Alert, OddsSnapshot
from odds_app.scrapers.base import OddsQuote
from odds_app.services.matching import resolve_source_event_mapping


def _pct_drop(old: Decimal, new: Decimal) -> float:
    if old <= 0:
        return 0.0
    return float(((old - new) / old) * Decimal(100))


def _hours_to_kickoff(quote: OddsQuote) -> float | None:
    if quote.kickoff_utc is None:
        return None
    return round((quote.kickoff_utc - quote.scraped_at).total_seconds() / 3600, 2)


def _latest_drop_alert(db: Session, quote: OddsQuote) -> Alert | None:
    stmt = (
        select(Alert)
        .where(Alert.alert_type == "odds_drop")
        .where(Alert.source == quote.source)
        .where(Alert.market_type == quote.market_type)
        .where(Alert.selection == quote.selection)
        .where(Alert.home_team == quote.home_team)
        .where(Alert.away_team == quote.away_team)
        .order_by(desc(Alert.created_at))
        .limit(1)
    )
    return db.scalar(stmt)


def _latest_alert_odds(alert: Alert | None) -> Decimal | None:
    if alert is None:
        return None
    details = alert.details or {}
    value = details.get("current_odds") or details.get("current_odds_decimal")
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _allow_drop_alert(
    quote: OddsQuote,
    latest_alert: Alert | None,
    cooldown_min: int,
    renotify_improvement_pct: float,
) -> tuple[bool, float | None]:
    if latest_alert is None:
        return True, None

    cooldown_from = quote.scraped_at - timedelta(minutes=cooldown_min)
    if latest_alert.created_at >= cooldown_from:
        return False, None

    previous_alert_odds = _latest_alert_odds(latest_alert)
    if previous_alert_odds is None:
        return True, None
    if quote.odds_decimal >= previous_alert_odds:
        return False, 0.0

    improvement_pct = _pct_drop(previous_alert_odds, quote.odds_decimal)
    return improvement_pct >= max(0.0, renotify_improvement_pct), improvement_pct


def _confirmation_points(db: Session, quote: OddsQuote, window_min: int) -> int:
    window_from = quote.scraped_at - timedelta(minutes=max(1, window_min))
    stmt = (
        select(func.count(OddsSnapshot.id))
        .where(OddsSnapshot.source == quote.source)
        .where(OddsSnapshot.external_event_id == quote.external_event_id)
        .where(OddsSnapshot.market_type == quote.market_type)
        .where(OddsSnapshot.selection == quote.selection)
        .where(OddsSnapshot.scraped_at >= window_from)
        .where(OddsSnapshot.scraped_at < quote.scraped_at)
        .where(OddsSnapshot.odds_decimal <= quote.odds_decimal)
    )
    prior_points = int(db.scalar(stmt) or 0)
    return prior_points + 1  # include current quote


def persist_quotes_and_detect_drops(db: Session, quotes: list[OddsQuote]) -> int:
    settings = get_settings()
    created_alerts = 0

    for quote in quotes:
        canonical = resolve_source_event_mapping(db, quote)

        base_stmt = (
            select(OddsSnapshot)
            .where(OddsSnapshot.source == quote.source)
            .where(OddsSnapshot.external_event_id == quote.external_event_id)
            .where(OddsSnapshot.market_type == quote.market_type)
            .where(OddsSnapshot.selection == quote.selection)
        )

        prev_stmt = (
            base_stmt.where(
                OddsSnapshot.scraped_at
                >= quote.scraped_at - timedelta(minutes=settings.odds_drop_lookback_min)
            )
            .where(OddsSnapshot.scraped_at < quote.scraped_at)
            .order_by(desc(OddsSnapshot.scraped_at))
            .limit(1)
        )
        previous = db.scalar(prev_stmt)

        opening_stmt = (
            base_stmt.where(OddsSnapshot.scraped_at < quote.scraped_at)
            .order_by(asc(OddsSnapshot.scraped_at))
            .limit(1)
        )
        opening = db.scalar(opening_stmt)

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

        baseline_type: str | None = None
        baseline_odds: Decimal | None = None
        drop_pct = 0.0

        if previous and quote.odds_decimal < previous.odds_decimal:
            recent_drop_pct = _pct_drop(previous.odds_decimal, quote.odds_decimal)
            if recent_drop_pct >= settings.odds_drop_threshold_pct:
                baseline_type = "recent"
                baseline_odds = previous.odds_decimal
                drop_pct = recent_drop_pct

        is_pre_match = quote.kickoff_utc is None or quote.scraped_at <= quote.kickoff_utc
        if opening and is_pre_match and quote.odds_decimal < opening.odds_decimal:
            opening_drop_pct = _pct_drop(opening.odds_decimal, quote.odds_decimal)
            if (
                opening_drop_pct >= settings.odds_drop_opening_threshold_pct
                and opening_drop_pct > drop_pct
            ):
                baseline_type = "opening"
                baseline_odds = opening.odds_decimal
                drop_pct = opening_drop_pct

        if baseline_odds is None:
            continue

        confirmation_points = _confirmation_points(
            db, quote, settings.odds_drop_confirmation_window_min
        )
        if confirmation_points < max(1, settings.odds_drop_confirmation_count):
            continue

        latest_alert = _latest_drop_alert(db, quote)
        allow_emit, improvement_pct = _allow_drop_alert(
            quote,
            latest_alert,
            settings.alert_cooldown_min,
            settings.odds_drop_renotify_improvement_pct,
        )
        if not allow_emit:
            continue

        kickoff_hours = _hours_to_kickoff(quote)
        kickoff_suffix = "" if kickoff_hours is None else f" | kickoff in {kickoff_hours:.2f}h"
        confirm_suffix = (
            f" | confirmations={confirmation_points}/{settings.odds_drop_confirmation_count}"
        )
        msg = (
            f"[ODDS DROP] {quote.home_team} vs {quote.away_team} | "
            f"{quote.market_type}:{quote.selection} {baseline_odds} -> "
            f"{quote.odds_decimal} ({drop_pct:.2f}% drop, baseline={baseline_type}) "
            f"on {quote.source}{confirm_suffix}{kickoff_suffix}"
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
                "canonical_match_id": canonical.id,
                "baseline_type": baseline_type,
                "baseline_odds": str(baseline_odds),
                "current_odds": str(quote.odds_decimal),
                "drop_pct": round(drop_pct, 4),
                "external_event_id": quote.external_event_id,
                "hours_to_kickoff": kickoff_hours,
                "opening_odds": str(opening.odds_decimal) if opening else None,
                "recent_odds": str(previous.odds_decimal) if previous else None,
                "confirmation_points": confirmation_points,
                "confirmation_required": max(1, settings.odds_drop_confirmation_count),
                "confirmation_window_min": settings.odds_drop_confirmation_window_min,
                "renotify_improvement_pct": (
                    round(improvement_pct, 4) if improvement_pct is not None else None
                ),
                "last_alert_at": latest_alert.created_at.isoformat() if latest_alert else None,
            },
        )
        db.add(alert)
        created_alerts += 1

    db.commit()
    return created_alerts
