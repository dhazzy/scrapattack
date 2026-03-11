import asyncio
import logging

from odds_app.celery_app import celery
from odds_app.db import SessionLocal
from odds_app.scrapers.estave import EStaveScraper
from odds_app.scrapers.ps3838 import PS3838Scraper
from odds_app.services.alerts import TelegramNotifier, list_unsent_alerts, mark_alert_sent
from odds_app.services.ingest import persist_quotes_and_detect_drops
from odds_app.services.value_scan import scan_value_edges

logger = logging.getLogger(__name__)


@celery.task(name="odds_app.tasks.scrape_ps3838_soccer")
def scrape_ps3838_soccer() -> dict:
    scraper = PS3838Scraper()
    quotes = asyncio.run(scraper.scrape_soccer())
    with SessionLocal() as db:
        alert_count = persist_quotes_and_detect_drops(db, quotes)
    result = {"source": scraper.source, "quotes": len(quotes), "alerts_created": alert_count}
    logger.info("PS3838 task result: %s", result)
    return result


@celery.task(name="odds_app.tasks.scrape_estave_soccer")
def scrape_estave_soccer() -> dict:
    scraper = EStaveScraper()
    quotes = asyncio.run(scraper.scrape_soccer())
    with SessionLocal() as db:
        alert_count = persist_quotes_and_detect_drops(db, quotes)
    result = {"source": scraper.source, "quotes": len(quotes), "alerts_created": alert_count}
    logger.info("e-stave task result: %s", result)
    return result


@celery.task(name="odds_app.tasks.compare_value_edges")
def compare_value_edges() -> dict:
    with SessionLocal() as db:
        alerts = scan_value_edges(db)
    result = {"alerts_created": alerts}
    logger.info("Value comparison result: %s", result)
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
