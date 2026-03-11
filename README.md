# scrapattack

24/7 soccer odds scraping, cross-source matching, and alerting.

## What is now implemented

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

## Why canonical IDs matter

`ps3838` and `e-stave` have different external event IDs.  
The app now creates one internal match record (`canonical_matches.id`) and maps both source events into it (`source_events`), so both sites point to the same match ID.

## Parser mode

### Mock mode (default)

```env
USE_MOCK_SCRAPE_DATA=true
```

### Live extraction mode

```env
USE_MOCK_SCRAPE_DATA=false
SCRAPER_REQUEST_TIMEOUT_SEC=30
SCRAPER_ENABLE_PLAYWRIGHT=false
```

Live extraction flow:
1. Pull page HTML
2. Parse embedded JSON/script payloads
3. Optionally capture JSON XHR/fetch payloads with Playwright (`SCRAPER_ENABLE_PLAYWRIGHT=true`)

> If Playwright mode is enabled, install browser binaries:
>
> ```bash
> python -m playwright install chromium
> ```

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
