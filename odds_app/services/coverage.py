from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from odds_app.constants import DEFAULT_COMPARISON_SOURCES
from odds_app.models import OddsSnapshot, SourceEvent

DEFAULT_HORIZONS_HOURS = (24, 72, 168, 336)


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
