import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from odds_app.config import get_settings
from odds_app.constants import DEFAULT_COMPARISON_SOURCES
from odds_app.models import ScrapeRun
from odds_app.scrapers.base import OddsQuote

ScrapeFn = Callable[[], list[OddsQuote]]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _trim_error(value: str | None, max_len: int = 1200) -> str | None:
    if not value:
        return None
    return value[:max_len]


def _floor_bucket(value: datetime, bucket_minutes: int) -> datetime:
    minute_bucket = (value.minute // bucket_minutes) * bucket_minutes
    return value.replace(minute=minute_bucket, second=0, microsecond=0)


def _record_scrape_run(
    db: Session,
    *,
    source: str,
    sport: str,
    trigger: str,
    mode: str,
    started_at: datetime,
    finished_at: datetime,
    success: bool,
    quotes_count: int,
    error_message: str | None,
) -> ScrapeRun:
    duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
    run = ScrapeRun(
        source=source,
        sport=sport,
        trigger=trigger,
        mode=mode,
        success=success,
        quotes_count=max(0, int(quotes_count)),
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        error_message=_trim_error(error_message),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def execute_scrape_with_recovery(
    db: Session,
    *,
    source: str,
    scrape_fn: ScrapeFn,
    sport: str = "soccer",
    trigger: str = "scheduled",
    min_quotes_success: int | None = None,
) -> tuple[list[OddsQuote], dict]:
    settings = get_settings()
    required_quotes = max(
        0,
        settings.scrape_min_quotes_success
        if min_quotes_success is None
        else int(min_quotes_success),
    )
    retry_count = max(0, int(settings.scrape_recovery_retry_count))
    backoff_sec = max(0.0, float(settings.scrape_recovery_backoff_sec))
    max_attempts = 1 + retry_count

    attempts_meta: list[dict] = []
    best_quotes: list[OddsQuote] = []
    last_error: str | None = None

    for attempt in range(1, max_attempts + 1):
        mode = "primary" if attempt == 1 else "recovery"
        started_at = _utcnow()
        quotes: list[OddsQuote] = []
        error_message: str | None = None
        success = False
        try:
            quotes = scrape_fn() or []
            success = len(quotes) >= required_quotes
            if not success:
                error_message = f"quotes_below_min:{len(quotes)}<{required_quotes}"
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)

        finished_at = _utcnow()
        run = _record_scrape_run(
            db,
            source=source,
            sport=sport,
            trigger=trigger,
            mode=mode,
            started_at=started_at,
            finished_at=finished_at,
            success=success,
            quotes_count=len(quotes),
            error_message=error_message,
        )
        attempts_meta.append(
            {
                "attempt": attempt,
                "mode": mode,
                "run_id": run.id,
                "success": success,
                "quotes": len(quotes),
                "duration_ms": run.duration_ms,
                "error": error_message,
            }
        )
        if len(quotes) > len(best_quotes):
            best_quotes = quotes
        if success:
            return quotes, {
                "source": source,
                "sport": sport,
                "trigger": trigger,
                "success": True,
                "attempts": attempts_meta,
                "recovered": attempt > 1,
            }

        last_error = error_message
        if attempt < max_attempts and backoff_sec > 0:
            time.sleep(backoff_sec)

    return best_quotes, {
        "source": source,
        "sport": sport,
        "trigger": trigger,
        "success": False,
        "attempts": attempts_meta,
        "recovered": False,
        "error": last_error,
    }


def get_scrape_health_summary(db: Session, window_hours: int = 6, per_source_limit: int = 200) -> dict:
    window_hours = max(1, int(window_hours))
    per_source_limit = max(20, int(per_source_limit))
    now = _utcnow()
    cutoff = now - timedelta(hours=window_hours)

    runs = list(
        db.scalars(
            select(ScrapeRun)
            .where(ScrapeRun.started_at >= cutoff)
            .order_by(desc(ScrapeRun.started_at))
            .limit(per_source_limit * 8)
        )
    )

    by_source: dict[str, list[ScrapeRun]] = {}
    for run in runs:
        if len(by_source.setdefault(run.source, [])) < per_source_limit:
            by_source[run.source].append(run)

    summary: list[dict] = []
    for source, source_runs in sorted(by_source.items()):
        if not source_runs:
            continue
        total = len(source_runs)
        success_count = sum(1 for run in source_runs if run.success)
        avg_quotes = round(sum(run.quotes_count for run in source_runs) / total, 2)
        avg_duration_ms = round(sum(run.duration_ms for run in source_runs) / total, 1)

        consecutive_failures = 0
        for run in source_runs:
            if run.success:
                break
            consecutive_failures += 1

        last_success = next((run.started_at for run in source_runs if run.success), None)
        last_failure = next((run.started_at for run in source_runs if not run.success), None)
        last_error = next((run.error_message for run in source_runs if run.error_message), None)

        summary.append(
            {
                "source": source,
                "window_hours": window_hours,
                "runs": total,
                "success_rate_pct": round((success_count / total) * 100, 2),
                "avg_quotes": avg_quotes,
                "avg_duration_ms": avg_duration_ms,
                "consecutive_failures": consecutive_failures,
                "last_success_at": last_success.isoformat() if last_success else None,
                "last_failure_at": last_failure.isoformat() if last_failure else None,
                "last_error": last_error,
            }
        )

    return {
        "generated_at": now.isoformat(),
        "window_hours": window_hours,
        "sources": summary,
    }


def get_scrape_run_history(
    db: Session,
    hours: int = 24,
    bucket_minutes: int = 15,
    runs: int | None = None,
    sources: tuple[str, ...] = DEFAULT_COMPARISON_SOURCES,
) -> dict:
    now = _utcnow()
    hours = max(1, int(hours))
    bucket_minutes = max(1, int(bucket_minutes))
    cutoff = now - timedelta(hours=hours)

    rows = list(
        db.scalars(
            select(ScrapeRun)
            .where(ScrapeRun.started_at >= cutoff)
            .order_by(ScrapeRun.started_at.asc())
        )
    )

    first_bucket = _floor_bucket(cutoff, bucket_minutes)
    last_bucket = _floor_bucket(now, bucket_minutes)
    buckets: list[datetime] = []
    cursor = first_bucket
    while cursor <= last_bucket:
        buckets.append(cursor)
        cursor = cursor + timedelta(minutes=bucket_minutes)

    bucket_index = {bucket: idx for idx, bucket in enumerate(buckets)}
    observed_sources = sorted({run.source for run in rows})
    source_list = sorted(set(sources) | set(observed_sources))
    attempts = {source: [0 for _ in buckets] for source in source_list}
    successes = {source: [0 for _ in buckets] for source in source_list}
    quote_sums = {source: [0 for _ in buckets] for source in source_list}

    for run in rows:
        bucket = _floor_bucket(run.started_at, bucket_minutes)
        idx = bucket_index.get(bucket)
        if idx is None:
            continue
        source = run.source
        attempts[source][idx] += 1
        successes[source][idx] += 1 if run.success else 0
        quote_sums[source][idx] += int(run.quotes_count)

    runs_limit = max(1, int(runs)) if runs is not None else None
    if runs_limit is not None:
        buckets = buckets[-runs_limit:]

    series = []
    for source in source_list:
        source_attempts = attempts[source]
        source_successes = successes[source]
        source_quote_sums = quote_sums[source]
        if runs_limit is not None:
            source_attempts = source_attempts[-runs_limit:]
            source_successes = source_successes[-runs_limit:]
            source_quote_sums = source_quote_sums[-runs_limit:]
        success_rate_pct = [
            round((source_successes[i] / source_attempts[i]) * 100, 2)
            if source_attempts[i] > 0
            else None
            for i in range(len(source_attempts))
        ]
        avg_quotes = [
            round(source_quote_sums[i] / source_attempts[i], 2)
            if source_attempts[i] > 0
            else None
            for i in range(len(source_attempts))
        ]
        series.append(
            {
                "source": source,
                "attempt_counts": source_attempts,
                "success_counts": source_successes,
                "success_rate_pct": success_rate_pct,
                "avg_quotes": avg_quotes,
            }
        )

    return {
        "generated_at": now.isoformat(),
        "hours": hours,
        "bucket_minutes": bucket_minutes,
        "runs": runs_limit,
        "buckets": [bucket.isoformat() for bucket in buckets],
        "series": series,
    }
