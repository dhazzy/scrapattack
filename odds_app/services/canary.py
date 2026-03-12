from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from odds_app.config import get_settings
from odds_app.constants import DEFAULT_COMPARISON_SOURCES
from odds_app.models import Alert
from odds_app.services.coverage import get_scrape_coverage_metrics
from odds_app.services.reliability import get_scrape_health_summary


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aggregate_upcoming_by_source(coverage_rows: list[dict]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for row in coverage_rows:
        source = row["source"]
        bucket = out.setdefault(source, {"upcoming_24h": 0, "upcoming_72h": 0, "upcoming_168h": 0})
        bucket["upcoming_24h"] += int(row.get("upcoming_24h", 0) or 0)
        bucket["upcoming_72h"] += int(row.get("upcoming_72h", 0) or 0)
        bucket["upcoming_168h"] += int(row.get("upcoming_168h", 0) or 0)
    return out


def _latest_canary_alert(db: Session, source: str) -> Alert | None:
    stmt = (
        select(Alert)
        .where(Alert.alert_type == "canary_failure")
        .where(Alert.source == source)
        .order_by(desc(Alert.created_at))
        .limit(1)
    )
    return db.scalar(stmt)


def run_scrape_canary_checks(db: Session, *, create_alerts: bool = True) -> dict:
    settings = get_settings()
    now = _utcnow()
    health = get_scrape_health_summary(db, window_hours=settings.canary_window_hours)
    coverage = get_scrape_coverage_metrics(
        db,
        horizons_hours=(24, 72, 168),
        sources=DEFAULT_COMPARISON_SOURCES,
    )
    health_by_source = {row["source"]: row for row in health.get("sources", [])}
    upcoming_by_source = _aggregate_upcoming_by_source(coverage.get("coverage", []))

    sources = sorted(set(DEFAULT_COMPARISON_SOURCES) | set(health_by_source) | set(upcoming_by_source))
    results: list[dict] = []
    alerts_created = 0
    cooldown_cutoff = now - timedelta(minutes=max(1, settings.canary_alert_cooldown_min))

    for source in sources:
        health_row = health_by_source.get(source, {})
        upcoming_row = upcoming_by_source.get(
            source, {"upcoming_24h": 0, "upcoming_72h": 0, "upcoming_168h": 0}
        )

        checks = [
            {
                "name": "success_rate_pct",
                "value": float(health_row.get("success_rate_pct", 0.0) or 0.0),
                "threshold": float(settings.canary_min_success_rate_pct),
            },
            {
                "name": "avg_quotes",
                "value": float(health_row.get("avg_quotes", 0.0) or 0.0),
                "threshold": float(settings.canary_min_avg_quotes),
            },
            {
                "name": "upcoming_72h",
                "value": int(upcoming_row.get("upcoming_72h", 0) or 0),
                "threshold": int(settings.canary_min_upcoming_72h),
            },
            {
                "name": "upcoming_168h",
                "value": int(upcoming_row.get("upcoming_168h", 0) or 0),
                "threshold": int(settings.canary_min_upcoming_168h),
            },
        ]
        failing = [check for check in checks if check["value"] < check["threshold"]]
        status = "pass" if not failing else "fail"

        if failing and create_alerts:
            latest = _latest_canary_alert(db, source)
            if latest is None or latest.created_at < cooldown_cutoff:
                failure_msg = ", ".join(
                    f"{check['name']}={check['value']}<{check['threshold']}" for check in failing
                )
                alert = Alert(
                    alert_type="canary_failure",
                    source=source,
                    sport="system",
                    market_type="system",
                    selection="system",
                    home_team=source,
                    away_team="canary",
                    kickoff_utc=None,
                    message=f"[CANARY FAIL] {source}: {failure_msg}",
                    details={
                        "source": source,
                        "status": status,
                        "generated_at": now.isoformat(),
                        "checks": checks,
                        "health_row": health_row,
                        "upcoming_row": upcoming_row,
                    },
                    is_sent=False,
                )
                db.add(alert)
                alerts_created += 1

        results.append(
            {
                "source": source,
                "status": status,
                "failing_checks": failing,
                "checks": checks,
                "health": health_row,
                "upcoming": upcoming_row,
            }
        )

    if alerts_created:
        db.commit()

    return {
        "generated_at": now.isoformat(),
        "window_hours": settings.canary_window_hours,
        "status": "pass" if all(row["status"] == "pass" for row in results) else "fail",
        "alerts_created": alerts_created,
        "sources": results,
    }

