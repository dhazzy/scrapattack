from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from odds_app.constants import DEFAULT_COMPARISON_SOURCES
from odds_app.models import OddsSnapshot, SourceEvent

DEFAULT_HORIZONS_HOURS = (24, 72, 168, 336)


def _floor_bucket(value: datetime, bucket_minutes: int) -> datetime:
    minute_bucket = (value.minute // bucket_minutes) * bucket_minutes
    return value.replace(minute=minute_bucket, second=0, microsecond=0)


def get_scrape_coverage_metrics(
    db: Session,
    sources: tuple[str, str] = DEFAULT_COMPARISON_SOURCES,
    horizons_hours: tuple[int, ...] = DEFAULT_HORIZONS_HOURS,
    active_window_hours: int = 12,
) -> dict:
    now = datetime.now(timezone.utc)
    active_cutoff = now - timedelta(hours=active_window_hours)

    sports = [
        row[0]
        for row in db.execute(
            select(SourceEvent.sport)
            .where(SourceEvent.source.in_(list(sources)))
            .distinct()
            .order_by(SourceEvent.sport.asc())
        ).all()
    ]
    if not sports:
        sports = ["soccer", "basketball", "tennis"]

    latest_scrape_by_source = {
        source: latest
        for source, latest in db.execute(
            select(OddsSnapshot.source, func.max(OddsSnapshot.scraped_at))
            .where(OddsSnapshot.source.in_(list(sources)))
            .group_by(OddsSnapshot.source)
        ).all()
    }

    snapshot_count_30m = {
        source: int(count)
        for source, count in db.execute(
            select(OddsSnapshot.source, func.count(OddsSnapshot.id))
            .where(OddsSnapshot.source.in_(list(sources)))
            .where(OddsSnapshot.scraped_at >= now - timedelta(minutes=30))
            .group_by(OddsSnapshot.source)
        ).all()
    }

    by_source_sport: list[dict] = []
    for source in sources:
        for sport in sports:
            active_events = int(
                db.scalar(
                    select(func.count(func.distinct(SourceEvent.external_event_id)))
                    .where(SourceEvent.source == source)
                    .where(SourceEvent.sport == sport)
                    .where(SourceEvent.last_seen_at >= active_cutoff)
                )
                or 0
            )

            upcoming = {}
            for horizon in horizons_hours:
                horizon_end = now + timedelta(hours=horizon)
                count = int(
                    db.scalar(
                        select(func.count(func.distinct(SourceEvent.external_event_id)))
                        .where(SourceEvent.source == source)
                        .where(SourceEvent.sport == sport)
                        .where(SourceEvent.last_seen_at >= active_cutoff)
                        .where(SourceEvent.kickoff_utc.is_not(None))
                        .where(SourceEvent.kickoff_utc >= now)
                        .where(SourceEvent.kickoff_utc <= horizon_end)
                    )
                    or 0
                )
                upcoming[f"upcoming_{horizon}h"] = count

            by_source_sport.append(
                {
                    "source": source,
                    "sport": sport,
                    "active_events": active_events,
                    **upcoming,
                }
            )

    return {
        "generated_at": now.isoformat(),
        "active_window_hours": active_window_hours,
        "horizons_hours": list(horizons_hours),
        "latest_scrape_by_source": {
            source: latest_scrape_by_source.get(source).isoformat()
            if latest_scrape_by_source.get(source) is not None
            else None
            for source in sources
        },
        "snapshot_count_last_30m": {
            source: snapshot_count_30m.get(source, 0) for source in sources
        },
        "coverage": by_source_sport,
    }


def get_scrape_coverage_trend(
    db: Session,
    sources: tuple[str, str] = DEFAULT_COMPARISON_SOURCES,
    hours: int = 24,
    bucket_minutes: int = 30,
    runs: int | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    hours = max(1, hours)
    bucket_minutes = max(5, bucket_minutes)
    cutoff = now - timedelta(hours=hours)

    snapshots = list(
        db.scalars(
            select(OddsSnapshot)
            .where(OddsSnapshot.source.in_(list(sources)))
            .where(OddsSnapshot.market_type == "1x2")
            .where(OddsSnapshot.selection == "home")
            .where(OddsSnapshot.scraped_at >= cutoff)
            .order_by(OddsSnapshot.scraped_at.asc())
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
    event_sets = {
        source: [set() for _ in buckets]
        for source in sources
    }
    future72_sets = {
        source: [set() for _ in buckets]
        for source in sources
    }

    for snap in snapshots:
        bucket = _floor_bucket(snap.scraped_at, bucket_minutes)
        idx = bucket_index.get(bucket)
        if idx is None:
            continue
        event_sets[snap.source][idx].add(snap.external_event_id)

        if snap.kickoff_utc is not None:
            horizon_end = snap.scraped_at + timedelta(hours=72)
            if snap.scraped_at <= snap.kickoff_utc <= horizon_end:
                future72_sets[snap.source][idx].add(snap.external_event_id)

    runs_limit = max(1, int(runs)) if runs is not None else None
    series = []
    for source in sources:
        event_counts = [len(s) for s in event_sets[source]]
        future_72h_counts = [len(s) for s in future72_sets[source]]
        if runs_limit is not None:
            event_counts = event_counts[-runs_limit:]
            future_72h_counts = future_72h_counts[-runs_limit:]
        series.append(
            {
                "source": source,
                "event_counts": event_counts,
                "future_72h_counts": future_72h_counts,
            }
        )
    if runs_limit is not None:
        buckets = buckets[-runs_limit:]

    return {
        "generated_at": now.isoformat(),
        "hours": hours,
        "bucket_minutes": bucket_minutes,
        "runs": runs_limit,
        "buckets": [bucket.isoformat() for bucket in buckets],
        "series": series,
    }


def get_scrape_coverage_gaps(
    db: Session,
    *,
    days: int = 14,
    sources: tuple[str, str] = DEFAULT_COMPARISON_SOURCES,
) -> dict:
    days = max(1, int(days))
    horizon_hours = tuple(hour for hour in DEFAULT_HORIZONS_HOURS if hour <= days * 24)
    metrics = get_scrape_coverage_metrics(db, sources=sources, horizons_hours=horizon_hours)
    coverage_rows = metrics.get("coverage", [])

    maxima: dict[tuple[str, int], int] = {}
    for row in coverage_rows:
        sport = row["sport"]
        for hour in horizon_hours:
            key = (sport, hour)
            maxima[key] = max(maxima.get(key, 0), int(row.get(f"upcoming_{hour}h", 0) or 0))

    rows: list[dict] = []
    summary_by_source: dict[str, dict[str, int]] = {}
    for row in coverage_rows:
        source = row["source"]
        sport = row["sport"]
        source_summary = summary_by_source.setdefault(
            source, {"green": 0, "yellow": 0, "red": 0, "horizons": 0}
        )
        horizon_items = []
        for hour in horizon_hours:
            count = int(row.get(f"upcoming_{hour}h", 0) or 0)
            baseline = maxima.get((sport, hour), 0)
            ratio = (count / baseline) if baseline > 0 else 0.0
            if baseline == 0 or ratio < 0.4:
                status = "red"
            elif ratio < 0.8:
                status = "yellow"
            else:
                status = "green"
            source_summary[status] += 1
            source_summary["horizons"] += 1
            horizon_items.append(
                {
                    "horizon_hours": hour,
                    "count": count,
                    "baseline_max_for_sport": baseline,
                    "ratio_vs_sport_max": round(ratio, 4),
                    "gap_count": max(0, baseline - count),
                    "status": status,
                }
            )
        rows.append(
            {
                "source": source,
                "sport": sport,
                "horizons": horizon_items,
            }
        )

    summary = []
    for source, source_row in sorted(summary_by_source.items()):
        horizons = max(1, int(source_row["horizons"]))
        summary.append(
            {
                "source": source,
                "green": source_row["green"],
                "yellow": source_row["yellow"],
                "red": source_row["red"],
                "red_ratio": round(source_row["red"] / horizons, 4),
            }
        )

    return {
        "generated_at": metrics.get("generated_at"),
        "days": days,
        "horizons_hours": list(horizon_hours),
        "rows": rows,
        "summary_by_source": summary,
    }
