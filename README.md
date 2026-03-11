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
- Force-refresh endpoint/button to scrape now

## Schedule (every 5 min)

Configured via:

```env
SCRAPE_INTERVAL_SEC=300
COMPARE_INTERVAL_SEC=300
ALERT_DISPATCH_INTERVAL_SEC=30
```

## Force refresh now (instant scrape)

API:

```bash
curl -X POST http://localhost:8000/admin/force-refresh
```

UI:
- Open `/` and click **Force refresh now**

## Main API endpoints

- `GET /` dashboard UI
- `GET /health`
- `GET /health/db`
- `GET /alerts/recent?limit=50`
- `GET /odds/recent?limit=50`
- `GET /matches/source/{source}?limit=100` (`source=ps3838|e_stave`)
- `GET /matches/overlap?limit=100`
- `POST /admin/force-refresh`
- `GET /admin/diagnostics/ps3838`
- `POST /admin/diagnostics/ps3838`

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
VODDS_HEADLESS=true
VODDS_TIMEOUT_SEC=60
```

e-stave depth controls (for more than the first 10-15 matches):

```env
ESTAVE_PAGE_SIZE=25
ESTAVE_MAX_PAGES_PER_QUERY=40
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
