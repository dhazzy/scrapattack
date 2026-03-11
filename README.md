# scrapattack

24/7 soccer odds scraping, cross-source matching, and alerting.

## What is implemented

- FastAPI API + lightweight dashboard UI (`/`)
- Celery worker + beat scheduler
- PostgreSQL + Redis stack via Docker Compose
- Odds snapshots (`odds_snapshots`)
- Alerts (`alerts`)
- Canonical match mapping:
  - `canonical_matches` (internal shared match IDs)
  - `source_events` (source event IDs mapped to canonical IDs)
- Price drop detection
- Cross-site value-edge detection (`ps3838` vs `e-stave`)
- Telegram alert sender

## Scrape/compare cadence (5 minutes)

Configured by env vars:

```env
SCRAPE_INTERVAL_SEC=300
COMPARE_INTERVAL_SEC=300
ALERT_DISPATCH_INTERVAL_SEC=30
```

This means:
- ps3838 scrape every 5 min
- e-stave scrape every 5 min
- value comparison every 5 min
- alert dispatch every 30 sec

## Why canonical IDs matter

`ps3838` and `e-stave` use different external event IDs.  
The app creates one internal match (`canonical_matches.id`) and maps each source event into it (`source_events`), so same real-world match shares one ID.

## Parser mode

### Mock mode

```env
USE_MOCK_SCRAPE_DATA=true
```

### Live mode

```env
USE_MOCK_SCRAPE_DATA=false
SCRAPER_REQUEST_TIMEOUT_SEC=30
SCRAPER_ENABLE_PLAYWRIGHT=false
```

### Source notes

- `e-stave`: scraper now uses the live mobile endpoint (`_MobileService.aspx`) and parses soccer events/odds.
- `ps3838`: may return Cloudflare 403 from some server IPs. In that case no live quotes are returned (no mock fallback in live mode).

If Playwright mode is enabled, install browser binaries:

```bash
python -m playwright install chromium
```

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

## Useful commands

```bash
make health
make db-check
make run-once
make smoke
```

## API endpoints

- `GET /` dashboard UI
- `GET /health`
- `GET /health/db`
- `GET /odds/recent?limit=50`
- `GET /alerts/recent?limit=50`
- `GET /matches/recent?limit=50`
- `POST /admin/run-once?simulate_drop=false`

## DB table check

```bash
docker compose exec api python -m odds_app.check_db
```

Expected key tables:
- `odds_snapshots`
- `alerts`
- `canonical_matches`
- `source_events`
