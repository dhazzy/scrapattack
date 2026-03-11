import asyncio
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from odds_app.scrapers.estave import EStaveScraper
from odds_app.scrapers.ps3838 import PS3838Scraper
from odds_app.services.ingest import persist_quotes_and_detect_drops
from odds_app.services.value_scan import scan_value_edges


def _drop_quote_odds(value: Decimal, ratio: Decimal = Decimal("0.88")) -> Decimal:
    lowered = value * ratio
    return lowered.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def run_pipeline_once(db: Session, simulate_drop: bool = False) -> dict:
    ps_scraper = PS3838Scraper()
    es_scraper = EStaveScraper()

    ps_quotes = asyncio.run(ps_scraper.scrape_soccer())
    es_quotes = asyncio.run(es_scraper.scrape_soccer())

    ps_drop_alerts = persist_quotes_and_detect_drops(db, ps_quotes)
    es_drop_alerts = persist_quotes_and_detect_drops(db, es_quotes)
    value_alerts = scan_value_edges(db)
    simulated_drop_alerts = 0

    if simulate_drop and ps_quotes:
        shifted_quotes = [
            replace(
                q,
                odds_decimal=_drop_quote_odds(q.odds_decimal),
                scraped_at=q.scraped_at + timedelta(minutes=1),
            )
            for q in ps_quotes
        ]
        simulated_drop_alerts = persist_quotes_and_detect_drops(db, shifted_quotes)

    return {
        "ps3838_quotes": len(ps_quotes),
        "estave_quotes": len(es_quotes),
        "drop_alerts_ps3838": ps_drop_alerts,
        "drop_alerts_estave": es_drop_alerts,
        "value_edge_alerts": value_alerts,
        "simulated_drop_alerts": simulated_drop_alerts,
        "total_alerts_created": (
            ps_drop_alerts + es_drop_alerts + value_alerts + simulated_drop_alerts
        ),
    }
