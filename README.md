# scrapattack

24/7 soccer odds scraping and alerting MVP.

## What is included

- FastAPI service (`odds_app.main`) with health + data inspection endpoints
- Celery workers + Celery Beat scheduler
- PostgreSQL persistence for odds snapshots + alert history
- Redis broker/result backend for async jobs
- Initial scraper adapters for:
  - `https://www.ps3838.com/en/sports/soccer`
  - `https://www.e-stave.com/stave`
- Odds drop detector (same source, over time)
- Cross-site value edge detector (`e-stave` vs `ps3838`)
- Telegram notifier for alert delivery

## Architecture

1. Scraper jobs run periodically (`beat`)
2. Quotes are normalized and stored in `odds_snapshots`
3. Price-drop logic creates `odds_drop` alerts
4. Cross-bookmaker comparison creates `value_edge` alerts
5. Alert dispatcher sends unsent alerts to Telegram

## Quick start

1. Copy environment file:

```bash
cp .env.example .env
```

2. (Optional) set Telegram credentials in `.env`:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

3. Run stack:

```bash
docker compose up --build
```

4. Verify API:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/db
curl http://localhost:8000/odds/recent
curl http://localhost:8000/alerts/recent
curl -X POST "http://localhost:8000/admin/run-once?simulate_drop=false"
```

5. Verify DB tables exist:

```bash
docker compose exec api python -m odds_app.check_db
```

Expected output includes:

- `alerts`
- `odds_snapshots`

## Current parser status

For safe local development, `USE_MOCK_SCRAPE_DATA=true` by default.  
This generates deterministic soccer odds data so ingestion and alert flow work immediately.

To scrape live pages, set:

```env
USE_MOCK_SCRAPE_DATA=false
```

Then update selectors/API parsing in:

- `odds_app/scrapers/ps3838.py`
- `odds_app/scrapers/estave.py`

Both scrapers currently look for generic HTML attributes (`data-event-id`, `data-odds`, etc.) and should be adapted to each site's real payload structure.

## API endpoints

- `GET /health`
- `GET /health/db`
- `GET /odds/recent?limit=50`
- `GET /alerts/recent?limit=50`
- `POST /admin/run-once?simulate_drop=false`

## Useful make targets

```bash
make up
make logs
make health
make db-check
make run-once
make smoke
```

## Troubleshooting startup

- If services start before Postgres is ready, retries are built in (`DB_STARTUP_MAX_RETRIES` and `DB_STARTUP_RETRY_DELAY_SEC` in `.env`).
- Inspect container logs:

```bash
docker compose logs -f api worker beat db redis
```

## Legal and operational notes

- Review each site's Terms of Service and applicable law before running 24/7 scraping.
- Use rotating sessions/proxies if target sites apply anti-bot protections.
- Keep historical records and evaluate strategy performance before placing real bets.
