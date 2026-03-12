import asyncio
import csv
import json
import time
from io import StringIO
from datetime import datetime, timedelta, timezone

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from odds_app.config import get_settings
from odds_app.constants import DEFAULT_COMPARISON_SOURCES
from odds_app.db import Base, engine, get_db, ping_db
from odds_app.models import Alert, CanonicalMatch, OddsSnapshot, ScrapeRun, SourceEvent
from odds_app.schemas import (
    AlertResponse,
    ForceCompareResponse,
    HealthResponse,
    MatchSummaryResponse,
    MatchOddsHistoryResponse,
    MatchOddsSnapshotsResponse,
    OddsSnapshotResponse,
    OverlapMatchRow,
    PS3838DiagnosticsOverrides,
    RunOnceResponse,
    SourceMatchRow,
)
from odds_app.services.comparison import (
    get_match_odds_history,
    get_match_odds_snapshots,
    get_overlap_home_trends,
    run_match_comparison_cycle,
)
from odds_app.services.coverage import (
    get_scrape_coverage_gaps,
    get_scrape_coverage_metrics,
    get_scrape_coverage_trend,
)
from odds_app.services.diagnostics import run_ps3838_diagnostics_sync, run_vodds_diagnostics_sync
from odds_app.services.match_views import list_overlap_matches, list_recent_matches, list_source_matches
from odds_app.services.canary import run_scrape_canary_checks
from odds_app.services.ingest import persist_quotes_and_detect_drops
from odds_app.services.orchestrator import run_pipeline_once
from odds_app.services.probing import probe_estave_scrape, probe_vodds_scrape
from odds_app.services.reliability import (
    get_scrape_health_summary,
    get_scrape_run_history,
    list_recent_scrape_runs,
)
from odds_app.ui_pages import render_admin_page, render_markets_page
from odds_app.services.runtime_overrides import (
    ALLOWED_OVERRIDE_KEYS,
    clear_runtime_overrides,
    get_runtime_overrides,
    set_runtime_overrides,
)

settings = get_settings()
app = FastAPI(title=settings.app_name)


@app.on_event("startup")
def on_startup() -> None:
    last_error: Exception | None = None
    for _ in range(settings.db_startup_max_retries):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(settings.db_startup_retry_delay_sec)
    if last_error is not None:
        raise last_error


def _next_scrape_payload(db: Session) -> dict:
    interval_sec = int(settings.scrape_interval_sec)
    last_scraped = db.scalar(select(func.max(OddsSnapshot.scraped_at)))
    if last_scraped is None:
        return {
            "interval_sec": interval_sec,
            "last_scrape_at": None,
            "next_scrape_at": None,
            "seconds_until_next": None,
        }

    if last_scraped.tzinfo is None:
        last_scraped = last_scraped.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    next_at = last_scraped + timedelta(seconds=interval_sec)
    seconds_left = max(0, int((next_at - now).total_seconds()))

    return {
        "interval_sec": interval_sec,
        "last_scrape_at": last_scraped.isoformat(),
        "next_scrape_at": next_at.isoformat(),
        "seconds_until_next": seconds_left,
    }


def _sports_from_probe_payload(payload: dict) -> list[str] | None:
    raw = payload.get("sports")
    if raw is None:
        return None
    if isinstance(raw, str):
        items = [part.strip() for part in raw.split(",")]
    elif isinstance(raw, list):
        items = [str(item).strip() for item in raw]
    else:
        raise HTTPException(
            status_code=400,
            detail="sports must be an array or comma-separated string",
        )
    normalized = [item for item in items if item]
    return normalized or None


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    raise HTTPException(status_code=400, detail="headless must be boolean")


@app.get("/", response_class=HTMLResponse)
def home_page() -> str:
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Odds App</title>
  <style>
    body { font-family: Inter, system-ui, Arial, sans-serif; margin: 0; background: #0b1220; color: #e5edf7; }
    .wrap { max-width: 900px; margin: 48px auto; padding: 24px; }
    .card { border: 1px solid #233452; border-radius: 12px; padding: 18px; background: #101a2e; }
    a { color: #8dc0ff; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .muted { color: #9eb0c9; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1 style="margin-top:0;">Sports Odds App</h1>
      <p class="muted">Operational controls live under /admin, while match/edge/alert tables are on /markets.</p>
      <p><a href="/admin">Open Admin Control Center</a> · <a href="/markets">Open Markets & Alerts</a></p>
      <p><a href="/health">API Health</a> · <a href="/health/db">DB Health</a></p>
    </div>
  </div>
</body>
</html>"""


@app.get("/admin", response_class=HTMLResponse)
def dashboard() -> str:
    return render_admin_page()


@app.get("/markets", response_class=HTMLResponse)
def markets_page() -> str:
    return render_markets_page()


@app.get("/matches/{canonical_match_id}/details", response_class=HTMLResponse)
def match_details_page(canonical_match_id: int) -> str:
    html = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Match Details #__ID__</title>
  <style>
    :root {
      --bg: #0b1220;
      --panel: #101a2e;
      --panel-2: #0f1729;
      --text: #e5edf7;
      --muted: #9eb0c9;
      --border: #233452;
      --table-head: #14213b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      background: radial-gradient(circle at top, #12203b, var(--bg) 45%);
      color: var(--text);
      padding: 16px;
    }
    .container { max-width: 1400px; margin: 0 auto; }
    a { color: #8dc0ff; text-decoration: none; }
    a:hover { text-decoration: underline; }
    h1 { margin: 0 0 6px; }
    .meta { color: var(--muted); margin-bottom: 12px; font-size: 13px; }
    .card {
      background: linear-gradient(180deg, var(--panel), var(--panel-2));
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px;
      margin-bottom: 12px;
    }
    .controls {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
      margin-bottom: 10px;
    }
    .control { display: flex; flex-direction: column; gap: 4px; }
    .control label { color: var(--muted); font-size: 12px; }
    .control select,
    .control input {
      background: #0b1220;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px;
      font-size: 12px;
    }
    .control.actions {
      justify-content: flex-end;
      flex-direction: row;
      align-items: flex-end;
      gap: 8px;
    }
    button {
      border: 1px solid var(--border);
      background: #17305d;
      color: white;
      padding: 8px 12px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 12px;
      height: 34px;
    }
    button:hover { filter: brightness(1.08); }
    .table-wrap {
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: auto;
      background: var(--panel-2);
    }
    table { border-collapse: collapse; width: 100%; min-width: 1000px; }
    th, td {
      border-bottom: 1px solid #1f2f4d;
      padding: 8px;
      font-size: 12px;
      white-space: nowrap;
      text-align: left;
    }
    th { background: var(--table-head); position: sticky; top: 0; z-index: 1; }
    tr:hover td { background: #13213f; }
    .hint { color: var(--muted); font-size: 12px; }
    #movement-chart-wrap { position: relative; width: 100%; height: 320px; }
    #movement-canvas { width: 100% !important; height: 100% !important; display: block; }
    #no-chart-data { display: none; margin-top: 8px; }
  </style>
</head>
<body>
  <div class="container">
    <div style="margin-bottom:8px;"><a href="/markets">← Back to markets</a></div>
    <h1 id="title">Match #__ID__</h1>
    <div id="subtitle" class="meta">Loading match details...</div>

    <div class="card">
      <div class="controls">
        <div class="control">
          <label for="filter-source">Source</label>
          <select id="filter-source">
            <option value="all">All</option>
            <option value="ps3838">ps3838</option>
            <option value="e_stave">e_stave</option>
          </select>
        </div>
        <div class="control">
          <label for="filter-selection">Selection</label>
          <select id="filter-selection">
            <option value="all">All</option>
            <option value="home">home</option>
            <option value="draw">draw</option>
            <option value="away">away</option>
          </select>
        </div>
        <div class="control">
          <label for="filter-from">From (local)</label>
          <input id="filter-from" type="datetime-local" />
        </div>
        <div class="control">
          <label for="filter-to">To (local)</label>
          <input id="filter-to" type="datetime-local" />
        </div>
        <div class="control actions">
          <button id="apply-filters">Apply filters</button>
          <button id="reset-filters">Reset</button>
        </div>
      </div>
      <div id="movement-chart-wrap"><canvas id="movement-canvas"></canvas></div>
      <div id="no-chart-data" class="hint">No chart data for current filters.</div>
      <div class="hint">Odds movement over time (all saved 1x2 snapshots in DB).</div>
    </div>

    <div class="card">
      <div id="counts" class="hint">Loading rows...</div>
      <div class="table-wrap">
        <table id="snapshots-table">
          <thead>
            <tr>
              <th>Saved At (UTC)</th><th>Source</th><th>Market</th><th>Selection</th><th>Odds</th><th>External Event ID</th><th>League</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns"></script>
  <script>
    const MATCH_ID = __ID__;
    let movementChart = null;
    let allSnapshots = [];

    async function fetchJson(url) {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${url}`);
      return await res.json();
    }

    function colorFor(source, selection) {
      const bySource = {
        ps3838: { home: '#4ea1ff', draw: '#7eb9ff', away: '#b3d7ff' },
        e_stave: { home: '#f6a75a', draw: '#f7c485', away: '#fde0b6' },
      };
      return (bySource[source] && bySource[source][selection]) || '#c8d2e2';
    }

    function formatUtc(iso) {
      if (!iso) return '-';
      const d = new Date(iso);
      return d.toISOString().replace('T', ' ').replace('Z', '');
    }

    function parseFilterDate(value) {
      if (!value) return null;
      const d = new Date(value);
      return Number.isNaN(d.getTime()) ? null : d.getTime();
    }

    function filteredSnapshots() {
      const source = document.getElementById('filter-source').value;
      const selection = document.getElementById('filter-selection').value;
      const fromTs = parseFilterDate(document.getElementById('filter-from').value);
      const toTs = parseFilterDate(document.getElementById('filter-to').value);

      return allSnapshots.filter((snap) => {
        if (source !== 'all' && snap.source !== source) return false;
        if (selection !== 'all' && snap.selection !== selection) return false;
        const ts = new Date(snap.scraped_at).getTime();
        if (fromTs !== null && ts < fromTs) return false;
        if (toTs !== null && ts > toTs) return false;
        return true;
      });
    }

    function renderChart(snapshots) {
      const groups = new Map();
      for (const snap of snapshots) {
        const key = `${snap.source}:${snap.selection}`;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push({ x: snap.scraped_at, y: Number(snap.odds_decimal), source: snap.source, selection: snap.selection });
      }

      const datasets = [];
      for (const [key, points] of groups.entries()) {
        const [source, selection] = key.split(':');
        datasets.push({
          label: `${source} ${selection}`,
          data: points,
          borderColor: colorFor(source, selection),
          backgroundColor: colorFor(source, selection),
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.15,
          spanGaps: true,
          borderDash: selection === 'draw' ? [6, 4] : [],
        });
      }

      const noData = document.getElementById('no-chart-data');
      const canvas = document.getElementById('movement-canvas');
      if (datasets.length === 0) {
        if (movementChart) {
          movementChart.destroy();
          movementChart = null;
        }
        noData.style.display = 'block';
        canvas.style.display = 'none';
        return;
      } else {
        noData.style.display = 'none';
        canvas.style.display = 'block';
        canvas.style.width = '100%';
        canvas.style.height = '100%';
      }

      if (movementChart) movementChart.destroy();
      movementChart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: { datasets },
        options: {
          animation: false,
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: { type: 'time', ticks: { color: '#c6d3e8' }, grid: { color: '#223450' } },
            y: { ticks: { color: '#c6d3e8' }, grid: { color: '#223450' } },
          },
          plugins: { legend: { labels: { color: '#dce8f8' } } },
        },
      });
    }

    function renderTable(snapshots) {
      const tbody = document.querySelector('#snapshots-table tbody');
      tbody.innerHTML = '';
      const reversed = [...snapshots].reverse();
      for (const snap of reversed) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${formatUtc(snap.scraped_at)}</td>
          <td>${snap.source}</td>
          <td>${snap.market_type}</td>
          <td>${snap.selection}</td>
          <td>${snap.odds_decimal}</td>
          <td>${snap.external_event_id}</td>
          <td>${snap.league ?? '-'}</td>
        `;
        tbody.appendChild(tr);
      }
      document.getElementById('counts').textContent = `Showing ${snapshots.length} / ${allSnapshots.length} saved odds rows`;
    }

    function applyFilters() {
      const snapshots = filteredSnapshots();
      renderChart(snapshots);
      renderTable(snapshots);
    }

    function resetFilters() {
      document.getElementById('filter-source').value = 'all';
      document.getElementById('filter-selection').value = 'all';
      document.getElementById('filter-from').value = '';
      document.getElementById('filter-to').value = '';
      applyFilters();
    }

    async function init() {
      try {
        const payload = await fetchJson(`/matches/${MATCH_ID}/odds-snapshots?hours=0`);
        allSnapshots = payload.snapshots ?? [];

        document.getElementById('title').textContent = `${payload.home_team} vs ${payload.away_team}`;
        document.getElementById('subtitle').textContent = `Match #${payload.canonical_match_id} | sport=${payload.sport} | kickoff=${payload.kickoff_utc ?? '-'} | all timestamps are saved in UTC`;

        document.getElementById('apply-filters').addEventListener('click', applyFilters);
        document.getElementById('reset-filters').addEventListener('click', resetFilters);
        document.getElementById('filter-source').addEventListener('change', applyFilters);
        document.getElementById('filter-selection').addEventListener('change', applyFilters);
        document.getElementById('filter-from').addEventListener('change', applyFilters);
        document.getElementById('filter-to').addEventListener('change', applyFilters);

        applyFilters();
      } catch (err) {
        document.getElementById('subtitle').textContent = `Failed loading match details: ${err}`;
      }
    }

    init();
  </script>
</body>
</html>
"""
    return html.replace("__ID__", str(canonical_match_id))


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name)


@app.get("/health/db")
def health_db() -> dict:
    return {"status": "ok" if ping_db() else "error"}


@app.get("/alerts/recent", response_model=list[AlertResponse])
def recent_alerts(limit: int = 50, db: Session = Depends(get_db)) -> list[Alert]:
    stmt = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


@app.get("/alerts/odds-drops", response_model=list[AlertResponse])
def recent_odds_drop_alerts(limit: int = 80, db: Session = Depends(get_db)) -> list[Alert]:
    stmt = (
        select(Alert)
        .where(Alert.alert_type == "odds_drop")
        .order_by(Alert.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


@app.get("/odds/recent", response_model=list[OddsSnapshotResponse])
def recent_odds(limit: int = 50, db: Session = Depends(get_db)) -> list[OddsSnapshot]:
    stmt = select(OddsSnapshot).order_by(OddsSnapshot.scraped_at.desc()).limit(limit)
    return list(db.scalars(stmt))


@app.get("/matches/recent", response_model=list[MatchSummaryResponse])
def recent_matches(limit: int = 50, db: Session = Depends(get_db)) -> list[MatchSummaryResponse]:
    return list_recent_matches(db, limit=limit)


@app.get("/matches/source/{source}", response_model=list[SourceMatchRow])
def matches_by_source(
    source: str, limit: int = 100, db: Session = Depends(get_db)
) -> list[SourceMatchRow]:
    if source not in set(DEFAULT_COMPARISON_SOURCES):
        allowed = ", ".join(DEFAULT_COMPARISON_SOURCES)
        raise HTTPException(status_code=400, detail=f"source must be one of: {allowed}")
    return list_source_matches(db, source=source, limit=limit)


@app.get("/matches/overlap", response_model=list[OverlapMatchRow])
def overlap_matches(limit: int = 100, db: Session = Depends(get_db)) -> list[OverlapMatchRow]:
    return list_overlap_matches(db, limit=limit)


@app.get("/matches/overlap-trends")
def overlap_match_trends(
    limit: int = 200,
    hours: int = 72,
    max_points: int = 18,
    db: Session = Depends(get_db),
) -> dict:
    overlap_rows = list_overlap_matches(db, limit=limit)
    canonical_ids = [row.canonical_match_id for row in overlap_rows]
    return {
        "trends": get_overlap_home_trends(
            db,
            canonical_match_ids=canonical_ids,
            hours=hours,
            max_points=max_points,
        )
    }


@app.get("/matches/{canonical_match_id}/odds-snapshots", response_model=MatchOddsSnapshotsResponse)
def match_odds_snapshots(
    canonical_match_id: int,
    hours: int = 0,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return get_match_odds_snapshots(db, canonical_match_id=canonical_match_id, hours=hours)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/matches/{canonical_match_id}/odds-history", response_model=MatchOddsHistoryResponse)
def match_odds_history(
    canonical_match_id: int,
    hours: int = 240,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return get_match_odds_history(db, canonical_match_id=canonical_match_id, hours=hours)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/admin/force-refresh", response_model=RunOnceResponse)
def admin_force_refresh(db: Session = Depends(get_db)) -> dict:
    return run_pipeline_once(db, simulate_drop=False)


@app.post("/admin/force-compare", response_model=ForceCompareResponse)
def admin_force_compare(db: Session = Depends(get_db)) -> dict:
    return run_match_comparison_cycle(db, overlap_limit=300)


@app.get("/admin/next-scrape")
def admin_next_scrape(db: Session = Depends(get_db)) -> dict:
    return _next_scrape_payload(db)


@app.get("/admin/coverage")
def admin_coverage(db: Session = Depends(get_db)) -> dict:
    return get_scrape_coverage_metrics(db)


@app.get("/admin/coverage-trend")
def admin_coverage_trend(
    hours: int = 24,
    bucket_minutes: int = 30,
    runs: int | None = None,
    db: Session = Depends(get_db),
) -> dict:
    return get_scrape_coverage_trend(
        db,
        hours=hours,
        bucket_minutes=bucket_minutes,
        runs=runs,
    )


@app.get("/admin/coverage-gaps")
def admin_coverage_gaps(days: int = 14, db: Session = Depends(get_db)) -> dict:
    return get_scrape_coverage_gaps(db, days=days)


@app.get("/admin/canary")
def admin_canary(create_alerts: bool = False, db: Session = Depends(get_db)) -> dict:
    return run_scrape_canary_checks(db, create_alerts=create_alerts)


@app.post("/admin/probe/estave")
def admin_probe_estave(
    payload: dict = Body(default_factory=dict),
    persist: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    sports = _sports_from_probe_payload(payload)
    try:
        quotes, summary = asyncio.run(
            probe_estave_scrape(
                sports=sports,
                min_days=float(payload.get("min_days", 0.0) or 0.0),
                max_days=float(payload.get("max_days", 14.0) or 14.0),
                max_pages_per_query=(
                    int(payload["max_pages_per_query"])
                    if payload.get("max_pages_per_query") is not None
                    else None
                ),
                page_size=(int(payload["page_size"]) if payload.get("page_size") is not None else None),
                g_values=(str(payload["g_values"]) if payload.get("g_values") is not None else None),
                extra_b_values=(
                    str(payload["extra_b_values"]) if payload.get("extra_b_values") is not None else None
                ),
            )
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid estave probe payload: {exc}") from exc

    alerts_created = 0
    if persist:
        alerts_created = persist_quotes_and_detect_drops(db, quotes)
    return {
        "persisted": bool(persist),
        "alerts_created": alerts_created,
        "summary": summary,
    }


@app.post("/admin/probe/vodds")
def admin_probe_vodds(
    payload: dict = Body(default_factory=dict),
    persist: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    sports = _sports_from_probe_payload(payload)
    try:
        quotes, summary = asyncio.run(
            probe_vodds_scrape(
                sports=sports,
                min_days=float(payload.get("min_days", 0.0) or 0.0),
                max_days=float(payload.get("max_days", 14.0) or 14.0),
                timeout_sec=(
                    float(payload["timeout_sec"]) if payload.get("timeout_sec") is not None else None
                ),
                headless=_optional_bool(payload.get("headless")),
                proxy_url=(str(payload["proxy_url"]) if payload.get("proxy_url") else None),
            )
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid vodds probe payload: {exc}") from exc

    alerts_created = 0
    if persist:
        alerts_created = persist_quotes_and_detect_drops(db, quotes)
    return {
        "persisted": bool(persist),
        "alerts_created": alerts_created,
        "summary": summary,
    }


@app.get("/admin/scrape-health")
def admin_scrape_health(window_hours: int = 6, db: Session = Depends(get_db)) -> dict:
    return get_scrape_health_summary(db, window_hours=window_hours)


@app.get("/admin/scrape-runs/history")
def admin_scrape_runs_history(
    hours: int = 24,
    bucket_minutes: int = 15,
    runs: int | None = None,
    db: Session = Depends(get_db),
) -> dict:
    return get_scrape_run_history(
        db,
        hours=hours,
        bucket_minutes=bucket_minutes,
        runs=runs,
    )


@app.get("/admin/scrape-runs/recent")
def admin_scrape_runs_recent(
    source: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
) -> dict:
    source_norm = (source or "").strip() or None
    return {"runs": list_recent_scrape_runs(db, source=source_norm, limit=limit)}


@app.get("/admin/runtime-overrides")
def admin_runtime_overrides() -> dict:
    return {
        "overrides": get_runtime_overrides(),
        "allowed_keys": sorted(ALLOWED_OVERRIDE_KEYS),
    }


@app.post("/admin/runtime-overrides")
def admin_runtime_overrides_update(payload: dict = Body(default_factory=dict)) -> dict:
    try:
        current = set_runtime_overrides(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "ok",
        "overrides": current,
        "allowed_keys": sorted(ALLOWED_OVERRIDE_KEYS),
    }


@app.post("/admin/runtime-overrides/reset")
def admin_runtime_overrides_reset() -> dict:
    clear_runtime_overrides()
    return {
        "status": "ok",
        "overrides": {},
        "allowed_keys": sorted(ALLOWED_OVERRIDE_KEYS),
    }


@app.get("/admin/export/overlap.csv")
def admin_export_overlap_csv(limit: int = 500, db: Session = Depends(get_db)) -> Response:
    limit = max(1, min(int(limit), 5000))
    rows = list_overlap_matches(db, limit=limit)
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "canonical_match_id",
            "sport",
            "home_team",
            "away_team",
            "kickoff_utc",
            "edge_pct",
            "best_home_source",
            "best_home_odds",
            "best_draw_source",
            "best_draw_odds",
            "best_away_source",
            "best_away_odds",
            "primary_source",
            "secondary_source",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.canonical_match_id,
                row.sport,
                row.home_team,
                row.away_team,
                row.kickoff_utc.isoformat() if row.kickoff_utc else "",
                row.edge_pct,
                row.best_home_source,
                row.best_home_odds,
                row.best_draw_source,
                row.best_draw_odds,
                row.best_away_source,
                row.best_away_odds,
                row.primary_source,
                row.secondary_source,
            ]
        )
    filename = f"overlap_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/admin/export/alerts.csv")
def admin_export_alerts_csv(
    limit: int = 1000,
    alert_type: str = "all",
    db: Session = Depends(get_db),
) -> Response:
    limit = max(1, min(int(limit), 10000))
    stmt = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if alert_type and alert_type != "all":
        stmt = stmt.where(Alert.alert_type == alert_type)
    rows = list(db.scalars(stmt))

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "created_at",
            "alert_type",
            "source",
            "sport",
            "home_team",
            "away_team",
            "market_type",
            "selection",
            "message",
            "is_sent",
            "sent_at",
            "details_json",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.created_at.isoformat() if row.created_at else "",
                row.alert_type,
                row.source,
                row.sport,
                row.home_team,
                row.away_team,
                row.market_type,
                row.selection,
                row.message,
                row.is_sent,
                row.sent_at.isoformat() if row.sent_at else "",
                json.dumps(row.details or {}, ensure_ascii=True),
            ]
        )
    filename = f"alerts_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/admin/clear-db")
def admin_clear_db(db: Session = Depends(get_db)) -> dict:
    deleted = {
        "alerts": int(db.scalar(select(func.count()).select_from(Alert)) or 0),
        "odds_snapshots": int(db.scalar(select(func.count()).select_from(OddsSnapshot)) or 0),
        "source_events": int(db.scalar(select(func.count()).select_from(SourceEvent)) or 0),
        "canonical_matches": int(db.scalar(select(func.count()).select_from(CanonicalMatch)) or 0),
        "scrape_runs": int(db.scalar(select(func.count()).select_from(ScrapeRun)) or 0),
    }

    db.query(Alert).delete(synchronize_session=False)
    db.query(OddsSnapshot).delete(synchronize_session=False)
    db.query(SourceEvent).delete(synchronize_session=False)
    db.query(CanonicalMatch).delete(synchronize_session=False)
    db.query(ScrapeRun).delete(synchronize_session=False)
    db.commit()

    return {"status": "ok", "deleted": deleted}


@app.post("/admin/run-once", response_model=RunOnceResponse)
def admin_run_once(simulate_drop: bool = False, db: Session = Depends(get_db)) -> dict:
    return run_pipeline_once(db, simulate_drop=simulate_drop)


@app.get("/admin/diagnostics/ps3838")
def admin_ps3838_diagnostics() -> dict:
    return run_ps3838_diagnostics_sync(settings)


@app.post("/admin/diagnostics/ps3838")
def admin_ps3838_diagnostics_with_overrides(
    overrides: PS3838DiagnosticsOverrides = Body(default_factory=PS3838DiagnosticsOverrides),
) -> dict:
    return run_ps3838_diagnostics_sync(settings, overrides.model_dump(exclude_none=True))


@app.get("/admin/diagnostics/vodds")
def admin_vodds_diagnostics() -> dict:
    return run_vodds_diagnostics_sync(settings)


@app.post("/admin/diagnostics/vodds")
def admin_vodds_diagnostics_with_overrides(
    overrides: PS3838DiagnosticsOverrides = Body(default_factory=PS3838DiagnosticsOverrides),
) -> dict:
    return run_vodds_diagnostics_sync(settings, overrides.model_dump(exclude_none=True))
