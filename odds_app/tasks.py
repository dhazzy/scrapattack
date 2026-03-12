import asyncio
import logging
from datetime import datetime, timedelta, timezone

from odds_app.celery_app import celery
from odds_app.config import get_settings
from odds_app.db import SessionLocal
from odds_app.models import Alert, OddsSnapshot, ScrapeRun
from odds_app.scrapers.estave import EStaveScraper
from odds_app.scrapers.ps3838 import PS3838Scraper
from odds_app.services.alerts import TelegramNotifier, list_unsent_alerts, mark_alert_sent
from odds_app.services.comparison import run_match_comparison_cycle
from odds_app.services.ingest import persist_quotes_and_detect_drops
from odds_app.services.orchestrator import run_pipeline_once
from odds_app.services.reliability import execute_scrape_with_recovery
from odds_app.services.value_scan import scan_value_edges

logger = logging.getLogger(__name__)


@celery.task(name="odds_app.tasks.scrape_ps3838_soccer")
def scrape_ps3838_soccer() -> dict:
    scraper = PS3838Scraper()
    with SessionLocal() as db:
        quotes, scrape_meta = execute_scrape_with_recovery(
            db,
            source=scraper.source,
            sport="soccer",
            trigger="scheduled",
            scrape_fn=lambda: asyncio.run(scraper.scrape_soccer()),
        )
        alert_count = persist_quotes_and_detect_drops(db, quotes)
    result = {
        "source": scraper.source,
        "quotes": len(quotes),
        "alerts_created": alert_count,
        "scrape": scrape_meta,
    }
    logger.info("PS3838 task result: %s", result)
    return result


@celery.task(name="odds_app.tasks.scrape_estave_soccer")
def scrape_estave_soccer() -> dict:
    scraper = EStaveScraper()
    with SessionLocal() as db:
        quotes, scrape_meta = execute_scrape_with_recovery(
            db,
            source=scraper.source,
            sport="soccer",
            trigger="scheduled",
            scrape_fn=lambda: asyncio.run(scraper.scrape_soccer()),
        )
        alert_count = persist_quotes_and_detect_drops(db, quotes)
    result = {
        "source": scraper.source,
        "quotes": len(quotes),
        "alerts_created": alert_count,
        "scrape": scrape_meta,
    }
    logger.info("e-stave task result: %s", result)
    return result


@celery.task(name="odds_app.tasks.compare_value_edges")
def compare_value_edges() -> dict:
    with SessionLocal() as db:
        alerts = scan_value_edges(db)
    result = {"alerts_created": alerts}
    logger.info("Value comparison result: %s", result)
    return result


@celery.task(name="odds_app.tasks.reconcile_and_compare_matches")
def reconcile_and_compare_matches() -> dict:
    with SessionLocal() as db:
        result = run_match_comparison_cycle(db)
    logger.info("Reconcile+compare result: %s", result)
    return result


@celery.task(name="odds_app.tasks.dispatch_pending_alerts")
def dispatch_pending_alerts() -> dict:
    notifier = TelegramNotifier()
    sent = 0
    with SessionLocal() as db:
        alerts = list_unsent_alerts(db, limit=100)
        for alert in alerts:
            if asyncio.run(notifier.send(alert.message)):
                mark_alert_sent(db, alert)
                sent += 1
        db.commit()
    result = {"alerts_checked": len(alerts), "alerts_sent": sent}
    logger.info("Alert dispatcher result: %s", result)
    return result


@celery.task(name="odds_app.tasks.cleanup_old_data")
def cleanup_old_data() -> dict:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    snapshot_cutoff = now - timedelta(days=settings.odds_snapshot_retention_days)
    scrape_run_cutoff = now - timedelta(days=settings.scrape_run_retention_days)
    alert_cutoff = now - timedelta(days=settings.alert_retention_days)

    with SessionLocal() as db:
        deleted_snapshots = (
            db.query(OddsSnapshot)
            .filter(OddsSnapshot.scraped_at < snapshot_cutoff)
            .delete(synchronize_session=False)
        )
        deleted_scrape_runs = (
            db.query(ScrapeRun)
            .filter(ScrapeRun.started_at < scrape_run_cutoff)
            .delete(synchronize_session=False)
        )
        deleted_alerts = (
            db.query(Alert)
            .filter(Alert.created_at < alert_cutoff)
            .filter(Alert.is_sent.is_(True))
            .delete(synchronize_session=False)
        )
        db.commit()

    result = {
        "deleted_odds_snapshots": int(deleted_snapshots),
        "deleted_scrape_runs": int(deleted_scrape_runs),
        "deleted_sent_alerts": int(deleted_alerts),
        "snapshot_cutoff": snapshot_cutoff.isoformat(),
        "scrape_run_cutoff": scrape_run_cutoff.isoformat(),
        "alert_cutoff": alert_cutoff.isoformat(),
    }
    logger.info("Retention cleanup result: %s", result)
    return result


@celery.task(name="odds_app.tasks.run_full_pipeline_once")
def run_full_pipeline_once(simulate_drop: bool = False) -> dict:
    with SessionLocal() as db:
        result = run_pipeline_once(db, simulate_drop=simulate_drop)
    logger.info("Full pipeline run result: %s", result)
    return result
