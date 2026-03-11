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

- `e-stave`: scraper uses live mobile endpoint (`_MobileService.aspx`) and parses soccer events/odds.
- `ps3838`: often Cloudflare-protected. Scraper has bypass options (proxy + cookie + stealth browser retries).

## PS3838 bypass options

Set in `.env`:

```env
PS3838_PROXY_URL=http://username:password@proxy-host:proxy-port
PS3838_COOKIE_HEADER=cf_clearance=...; session=...
PS3838_BROWSER_ONLY=false
PS3838_ENABLE_STEALTH=true
PS3838_RETRY_COUNT=2
SCRAPER_ENABLE_PLAYWRIGHT=true
```

Notes:
- If your host IP is blocked, you usually need a **residential proxy**.
- Cookie header should come from a valid browser session.
- Browser mode may still fail without good IP/session reputation.

Install browser binaries for Playwright:

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
- `GET /admin/diagnostics/ps3838`
- `POST /admin/diagnostics/ps3838`

## DB table check

```bash
docker compose exec api python -m odds_app.check_db
```

Expected key tables:
- `odds_snapshots`
- `alerts`
- `canonical_matches`
- `source_events`


## PS3838 diagnostics endpoint

Run:

```bash
curl http://localhost:8000/admin/diagnostics/ps3838
```

It reports each bypass layer separately:
- proxy reachability
- direct HTML access
- Playwright navigation behavior
- extraction quote count
- recommended next tuning steps

Override run (without restart):

```bash
curl -X POST http://localhost:8000/admin/diagnostics/ps3838 \
  -H "Content-Type: application/json" \
  -d '{
    "scraper_enable_playwright": true,
    "ps3838_enable_stealth": true,
    "ps3838_proxy_url": "http://user:pass@proxy-host:proxy-port",
    "ps3838_cookie_header": "cf_clearance=...; session=..."
  }'
```

Supported override fields:
- `scraper_enable_playwright`
- `scraper_request_timeout_sec`
- `scraper_proxy_url`
- `ps3838_proxy_url`
- `ps3838_cookie_header`
- `ps3838_referer_url`
- `ps3838_browser_only`
- `ps3838_enable_stealth`
- `ps3838_retry_count`
