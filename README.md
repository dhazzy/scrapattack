# scrapattack

24/7 sports odds scraping, cross-source matching, and alerting.

## What you have now

- Live scrapers (no mock mode):
  - `ps3838`
  - `e_stave`
- Sports in pipeline/UI:
  - Football/Soccer
  - Tennis
  - Basketball
- Canonical same-match mapping across sources:
  - `canonical_matches`
  - `source_events`
- Odds snapshots + alerts
- Dashboard UI with:
  - **PS3838 matches table**
  - **e-stave matches table**
  - **matches on both sources** with odds comparison
  - Home/Draw/Away odds columns where available
- PS3838 diagnostics endpoint (GET + POST overrides)
- Vodds diagnostics endpoint (GET + POST overrides)
- Force-refresh endpoint/button to scrape now

## Schedule (every 5 min)

Configured via:

```env
SCRAPE_INTERVAL_SEC=300
COMPARE_INTERVAL_SEC=300
ALERT_DISPATCH_INTERVAL_SEC=30
RETENTION_CLEANUP_INTERVAL_SEC=3600
```

## Force refresh now (instant scrape)

API:

```bash
curl -X POST http://localhost:8000/admin/force-refresh
```

UI:
- Open `/admin` and click **Force refresh now**

## Main API endpoints

- `GET /` landing page (links to admin)
- `GET /admin` admin dashboard UI
- `GET /health`
- `GET /health/db`
- `GET /alerts/recent?limit=50`
- `GET /odds/recent?limit=50`
- `GET /matches/source/{source}?limit=100` (`source=ps3838|e_stave`)
- `GET /matches/overlap?limit=100`
- `GET /admin/coverage`
- `GET /admin/coverage-trend?runs=72&bucket_minutes=5`
- `GET /admin/scrape-health?window_hours=6`
- `GET /admin/scrape-runs/history?hours=24&bucket_minutes=5&runs=288`
- `POST /admin/force-refresh`
- `GET /admin/diagnostics/ps3838`
- `POST /admin/diagnostics/ps3838`
- `GET /admin/diagnostics/vodds`
- `POST /admin/diagnostics/vodds`

## PS3838 access options

PS3838 is often Cloudflare-protected. Use one or more:

```env
PS3838_PROXY_URL=http://user:pass@proxy-host:proxy-port
PS3838_COOKIE_HEADER=cf_clearance=...; session=...
PS3838_BROWSER_ONLY=false
PS3838_ENABLE_STEALTH=true
SCRAPER_ENABLE_PLAYWRIGHT=true
```

Alternative provider-based access (optional):

```env
PS3838_ZENROWS_API_KEY=...
PS3838_SCRAPINGBEE_API_KEY=...
```

PS3838 via Vodds dashboard login (primary fallback path):

```env
VODDS_DASHBOARD_URL=https://vodds.com/member/dashboard
VODDS_USERNAME=...
VODDS_PASSWORD=...
VODDS_PROXY_URL=http://user:pass@proxy-host:proxy-port
VODDS_HEADLESS=true
VODDS_TIMEOUT_SEC=60
```

e-stave depth controls (for more than the first 10-15 matches):

```env
ESTAVE_PAGE_SIZE=25
ESTAVE_MAX_PAGES_PER_QUERY=40
```


## Reliability + self-healing

Scrape runs are now tracked in `scrape_runs` with success/failure, duration, quote counts, and error details.

- Scheduled and manual scrapes use a recovery wrapper:
  - primary attempt
  - configurable retry attempts with backoff
- Health endpoint for quick source-level reliability:

```bash
curl "http://localhost:8000/admin/scrape-health?window_hours=6"
```

Config:

```env
SCRAPE_MIN_QUOTES_SUCCESS=1
SCRAPE_RECOVERY_RETRY_COUNT=1
SCRAPE_RECOVERY_BACKOFF_SEC=2
```

## Odds-drop confirmation + dedupe

Odds-drop alerts now require confirmation points over a window and re-notify only on meaningful further moves.

```env
ODDS_DROP_CONFIRMATION_COUNT=2
ODDS_DROP_CONFIRMATION_WINDOW_MIN=180
ODDS_DROP_RENOTIFY_IMPROVEMENT_PCT=1.5
```

## Retention cleanup

Automated cleanup task removes old snapshots/scrape-runs and old sent alerts.

```env
ODDS_SNAPSHOT_RETENTION_DAYS=45
SCRAPE_RUN_RETENTION_DAYS=14
ALERT_RETENTION_DAYS=60
RETENTION_CLEANUP_INTERVAL_SEC=3600
```

## PS3838 diagnostics

Baseline:

```bash
curl http://localhost:8000/admin/diagnostics/ps3838
```

Try overrides without restart:

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

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

## Playwright setup

```bash
python -m playwright install chromium
```


## Vodds diagnostics

Baseline:

```bash
curl http://localhost:8000/admin/diagnostics/vodds
```

Try overrides without restart:

```bash
curl -X POST http://localhost:8000/admin/diagnostics/vodds \
  -H "Content-Type: application/json" \
  -d '{
    "vodds_username": "...",
    "vodds_password": "...",
    "vodds_proxy_url": "http://user:pass@proxy-host:proxy-port",
    "vodds_headless": true
  }'
```
