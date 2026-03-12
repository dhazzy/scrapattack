import time
from datetime import datetime, timedelta, timezone

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from odds_app.config import get_settings
from odds_app.constants import DEFAULT_COMPARISON_SOURCES
from odds_app.db import Base, engine, get_db, ping_db
from odds_app.models import Alert, CanonicalMatch, OddsSnapshot, SourceEvent
from odds_app.schemas import (
    AlertResponse,
    ForceCompareResponse,
    HealthResponse,
    MatchSummaryResponse,
    MatchOddsHistoryResponse,
    OddsSnapshotResponse,
    OverlapMatchRow,
    PS3838DiagnosticsOverrides,
    RunOnceResponse,
    SourceMatchRow,
)
from odds_app.services.comparison import get_match_odds_history, run_match_comparison_cycle
from odds_app.services.diagnostics import run_ps3838_diagnostics_sync, run_vodds_diagnostics_sync
from odds_app.services.match_views import list_overlap_matches, list_recent_matches, list_source_matches
from odds_app.services.orchestrator import run_pipeline_once

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


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Odds Dashboard</title>
  <style>
    :root {
      --bg: #0b1220;
      --panel: #101a2e;
      --panel-2: #0f1729;
      --text: #e5edf7;
      --muted: #9eb0c9;
      --border: #233452;
      --accent: #4ea1ff;
      --success: #1dbf73;
      --danger: #e45858;
      --table-head: #14213b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      background: radial-gradient(circle at top, #12203b, var(--bg) 45%);
      color: var(--text);
      padding: 18px;
    }
    .container { max-width: 1500px; margin: 0 auto; }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 14px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }
    h1 { margin: 0; font-size: 28px; }
    .meta { color: var(--muted); font-size: 13px; margin-top: 4px; }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .card {
      background: linear-gradient(180deg, var(--panel), var(--panel-2));
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px;
    }
    .label { color: var(--muted); font-size: 12px; margin-bottom: 4px; }
    .value { font-size: 18px; font-weight: 700; }
    .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }
    button {
      border: 1px solid var(--border);
      background: #17305d;
      color: white;
      padding: 9px 12px;
      border-radius: 8px;
      cursor: pointer;
      font-weight: 600;
    }
    button:hover { filter: brightness(1.08); }
    button.danger { background: #532222; border-color: #7b2f2f; }
    .status { color: var(--muted); font-size: 12px; align-self: center; }
    .section-title { margin: 22px 0 8px; font-size: 18px; }
    .table-wrap {
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: auto;
      background: var(--panel-2);
      margin-bottom: 18px;
    }
    table { border-collapse: collapse; width: 100%; min-width: 980px; }
    th, td {
      border-bottom: 1px solid #1f2f4d;
      padding: 8px;
      font-size: 12px;
      vertical-align: top;
      white-space: nowrap;
    }
    th {
      background: var(--table-head);
      text-align: left;
      position: sticky;
      top: 0;
      z-index: 1;
    }
    tr:hover td { background: #13213f; }
    .positive { color: var(--success); font-weight: 700; }
    .negative { color: var(--danger); font-weight: 700; }
    .muted { color: var(--muted); }
    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.6);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 1000;
      padding: 16px;
    }
    .modal-backdrop.show { display: flex; }
    .modal {
      width: min(520px, 100%);
      background: linear-gradient(180deg, #15233f, #0f182a);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
    }
    .modal p { color: #d3deee; margin: 0 0 10px; font-size: 14px; }
    .modal .hint { color: var(--muted); font-size: 12px; }
    .modal input {
      width: 100%;
      margin: 8px 0 12px;
      padding: 10px;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: #0b1220;
      color: #eef3fb;
    }
    .modal-actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
    }
    .chart-modal {
      width: min(980px, 100%);
    }
    #history-subtitle { margin-bottom: 8px; }
    #history-empty { margin-top: 10px; }
  </style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>Sports Odds Dashboard</h1>
      <div class="meta">Football/Soccer, Tennis, Basketball | Home/Draw/Away | PS3838 + e-stave + overlap</div>
    </div>
  </div>

  <div class="cards">
    <div class="card">
      <div class="label">Next scheduled scrape</div>
      <div id="next-scrape-time" class="value">-</div>
      <div id="next-scrape-countdown" class="muted">-</div>
    </div>
    <div class="card">
      <div class="label">Last scrape</div>
      <div id="last-scrape-time" class="value">-</div>
      <div id="scrape-interval" class="muted">-</div>
    </div>
  </div>

  <div class="actions">
    <button onclick="forceRefresh()">Force refresh now</button>
    <button onclick="forceCompare()">Force compare now</button>
    <button class="danger" onclick="openClearDbModal()">Clear whole DB</button>
    <span id="run-status" class="status"></span>
  </div>

  <h2 class="section-title">Matches on both sources (comparison)</h2>
  <div class="table-wrap">
    <table id="overlap-table">
      <thead>
        <tr>
          <th>Sport</th><th>Match ID</th><th>Match</th>
          <th>PS H</th><th>PS D</th><th>PS A</th>
          <th>ES H</th><th>ES D</th><th>ES A</th>
          <th>Edge H %</th><th>Better (H)</th><th>Kickoff (UTC)</th><th>Chart</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <h2 class="section-title">PS3838 matches</h2>
  <div class="table-wrap">
    <table id="ps-table">
      <thead>
        <tr>
          <th>Sport</th><th>Match ID</th><th>External ID</th><th>Match</th><th>League</th>
          <th>Home</th><th>Draw</th><th>Away</th><th>Kickoff (UTC)</th><th>Last Scraped</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <h2 class="section-title">e-stave matches</h2>
  <div class="table-wrap">
    <table id="es-table">
      <thead>
        <tr>
          <th>Sport</th><th>Match ID</th><th>External ID</th><th>Match</th><th>League</th>
          <th>Home</th><th>Draw</th><th>Away</th><th>Kickoff (UTC)</th><th>Last Scraped</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <h2 class="section-title">Recent alerts</h2>
  <div class="table-wrap">
    <table id="alerts-table">
      <thead>
        <tr>
          <th>Time</th><th>Type</th><th>Match</th><th>Message</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>
</div>
<div id="clear-db-modal" class="modal-backdrop" aria-hidden="true">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="clear-db-title">
    <h3 id="clear-db-title">Clear whole DB?</h3>
    <p>This will permanently delete odds snapshots, alerts, source events, and canonical matches.</p>
    <p class="hint">Type <strong>CLEAR DB</strong> to enable deletion.</p>
    <input id="clear-db-confirm-input" type="text" autocomplete="off" placeholder="Type: CLEAR DB" oninput="onClearDbInput()" />
    <div class="modal-actions">
      <button onclick="closeClearDbModal()">Cancel</button>
      <button id="clear-db-confirm-btn" class="danger" onclick="confirmClearDatabase()" disabled>Delete everything</button>
    </div>
  </div>
</div>

<div id="history-modal" class="modal-backdrop" aria-hidden="true">
  <div class="modal chart-modal" role="dialog" aria-modal="true" aria-labelledby="history-title">
    <h3 id="history-title">Odds movement history</h3>
    <div id="history-subtitle" class="hint"></div>
    <canvas id="odds-history-canvas" height="130"></canvas>
    <div id="history-empty" class="hint" style="display:none;">No odds history found for this match yet.</div>
    <div class="modal-actions">
      <button onclick="closeHistoryModal()">Close</button>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns"></script>

<script>
  let nextScrapeAtMs = null;
  let oddsHistoryChart = null;

  async function fetchJson(url, options = {}) {
    const res = await fetch(url, options);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${url}`);
    return await res.json();
  }

  function formatDateUtc(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toISOString().replace('T', ' ').replace('Z', '');
  }

  function formatDuration(sec) {
    if (sec == null) return '-';
    const s = Math.max(0, Math.floor(sec));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const r = s % 60;
    return `${h}h ${m}m ${r}s`;
  }

  function updateCountdown() {
    const el = document.getElementById('next-scrape-countdown');
    if (!nextScrapeAtMs) {
      el.textContent = '-';
      return;
    }
    const sec = Math.max(0, Math.floor((nextScrapeAtMs - Date.now()) / 1000));
    el.textContent = `in ${formatDuration(sec)}`;
  }

  function renderSchedule(meta) {
    const next = document.getElementById('next-scrape-time');
    const last = document.getElementById('last-scrape-time');
    const interval = document.getElementById('scrape-interval');

    next.textContent = formatDateUtc(meta.next_scrape_at);
    last.textContent = formatDateUtc(meta.last_scrape_at);
    interval.textContent = `interval: ${meta.interval_sec}s`;

    nextScrapeAtMs = meta.next_scrape_at ? new Date(meta.next_scrape_at).getTime() : null;
    updateCountdown();
  }

  function renderSourceTable(tableId, rows) {
    const tbody = document.querySelector(`#${tableId} tbody`);
    tbody.innerHTML = '';
    for (const row of rows) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.sport ?? '-'}</td>
        <td>${row.canonical_match_id}</td>
        <td>${row.external_event_id}</td>
        <td>${row.home_team} vs ${row.away_team}</td>
        <td>${row.league ?? '-'}</td>
        <td>${row.latest_home_odds ?? '-'}</td>
        <td>${row.latest_draw_odds ?? '-'}</td>
        <td>${row.latest_away_odds ?? '-'}</td>
        <td>${row.kickoff_utc ?? '-'}</td>
        <td>${row.last_scraped_at ?? '-'}</td>
      `;
      tbody.appendChild(tr);
    }
  }

  function renderOverlapTable(rows) {
    const tbody = document.querySelector('#overlap-table tbody');
    tbody.innerHTML = '';
    for (const row of rows) {
      const edge = row.edge_pct_estave_vs_ps3838_home;
      const edgeClass = edge == null ? '' : (edge >= 0 ? 'positive' : 'negative');
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.sport ?? '-'}</td>
        <td>${row.canonical_match_id}</td>
        <td>${row.home_team} vs ${row.away_team}</td>
        <td>${row.ps3838_home_odds ?? '-'}</td>
        <td>${row.ps3838_draw_odds ?? '-'}</td>
        <td>${row.ps3838_away_odds ?? '-'}</td>
        <td>${row.estave_home_odds ?? '-'}</td>
        <td>${row.estave_draw_odds ?? '-'}</td>
        <td>${row.estave_away_odds ?? '-'}</td>
        <td class="${edgeClass}">${edge == null ? '-' : edge.toFixed(2) + '%'}</td>
        <td>${row.better_source_home ?? '-'}</td>
        <td>${row.kickoff_utc ?? '-'}</td>
        <td><button onclick="openHistoryChart(${row.canonical_match_id})">Chart</button></td>
      `;
      tbody.appendChild(tr);
    }
  }

  function renderAlerts(rows) {
    const tbody = document.querySelector('#alerts-table tbody');
    tbody.innerHTML = '';
    for (const row of rows) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.created_at}</td>
        <td>${row.alert_type}</td>
        <td>${row.home_team} vs ${row.away_team}</td>
        <td>${row.message}</td>
      `;
      tbody.appendChild(tr);
    }
  }

  async function refresh() {
    const [schedule, overlap, psRows, esRows, alerts] = await Promise.all([
      fetchJson('/admin/next-scrape'),
      fetchJson('/matches/overlap?limit=200'),
      fetchJson('/matches/source/ps3838?limit=300'),
      fetchJson('/matches/source/e_stave?limit=300'),
      fetchJson('/alerts/recent?limit=80'),
    ]);
    renderSchedule(schedule);
    renderOverlapTable(overlap);
    renderSourceTable('ps-table', psRows);
    renderSourceTable('es-table', esRows);
    renderAlerts(alerts);
  }

  async function forceRefresh() {
    const status = document.getElementById('run-status');
    status.textContent = 'Refreshing sources...';
    try {
      const out = await fetchJson('/admin/force-refresh', { method: 'POST' });
      status.textContent = `Done: ps=${out.ps3838_quotes}, es=${out.estave_quotes}, alerts=${out.total_alerts_created}`;
      await refresh();
    } catch (err) {
      status.textContent = `Force refresh failed: ${err}`;
    }
  }

  async function forceCompare() {
    const status = document.getElementById('run-status');
    status.textContent = 'Reconciling and comparing matches...';
    try {
      const out = await fetchJson('/admin/force-compare', { method: 'POST' });
      status.textContent = `Compare done: reconciled=${out.reconciled_events}, overlaps=${out.overlap_matches}, value_alerts=${out.value_edge_alerts}`;
      await refresh();
    } catch (err) {
      status.textContent = `Force compare failed: ${err}`;
    }
  }

  function chartColorForSeries(source, selection) {
    const bySource = {
      ps3838: { home: '#4ea1ff', draw: '#7eb9ff', away: '#b3d7ff' },
      e_stave: { home: '#f6a75a', draw: '#f7c485', away: '#fde0b6' },
    };
    return (bySource[source] && bySource[source][selection]) || '#c8d2e2';
  }

  function closeHistoryModal() {
    const modal = document.getElementById('history-modal');
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
    if (oddsHistoryChart) {
      oddsHistoryChart.destroy();
      oddsHistoryChart = null;
    }
  }

  function renderHistoryChart(payload) {
    const subtitle = document.getElementById('history-subtitle');
    const empty = document.getElementById('history-empty');
    const canvas = document.getElementById('odds-history-canvas');

    subtitle.textContent = `${payload.home_team} vs ${payload.away_team} | sport=${payload.sport} | kickoff=${payload.kickoff_utc ?? '-'}`;

    if (!payload.series || payload.series.length === 0) {
      empty.style.display = 'block';
      canvas.style.display = 'none';
      return;
    }

    empty.style.display = 'none';
    canvas.style.display = 'block';

    const datasets = payload.series.map((series) => ({
      label: series.label,
      data: series.points.map((point) => ({
        x: point.scraped_at,
        y: Number(point.odds_decimal),
      })),
      borderColor: chartColorForSeries(series.source, series.selection),
      backgroundColor: chartColorForSeries(series.source, series.selection),
      borderWidth: 2,
      pointRadius: 0,
      tension: 0.2,
      spanGaps: true,
      borderDash: series.selection === 'draw' ? [6, 4] : [],
    }));

    if (oddsHistoryChart) {
      oddsHistoryChart.destroy();
    }

    oddsHistoryChart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { type: 'time', time: { tooltipFormat: 'yyyy-LL-dd HH:mm:ss' }, ticks: { color: '#c6d3e8' }, grid: { color: '#223450' } },
          y: { ticks: { color: '#c6d3e8' }, grid: { color: '#223450' } },
        },
        plugins: {
          legend: { labels: { color: '#dce8f8' } },
        },
      },
    });
  }

  async function openHistoryChart(canonicalMatchId) {
    const status = document.getElementById('run-status');
    status.textContent = `Loading chart for match ${canonicalMatchId}...`;
    const modal = document.getElementById('history-modal');
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');

    try {
      const payload = await fetchJson(`/matches/${canonicalMatchId}/odds-history?hours=240`);
      renderHistoryChart(payload);
      status.textContent = `Loaded odds history for match ${canonicalMatchId}`;
    } catch (err) {
      status.textContent = `Failed to load chart: ${err}`;
      document.getElementById('history-empty').style.display = 'block';
      document.getElementById('odds-history-canvas').style.display = 'none';
    }
  }

  function openClearDbModal() {
    const modal = document.getElementById('clear-db-modal');
    const input = document.getElementById('clear-db-confirm-input');
    document.getElementById('clear-db-confirm-btn').disabled = true;
    input.value = '';
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');
    setTimeout(() => input.focus(), 30);
  }

  function closeClearDbModal() {
    const modal = document.getElementById('clear-db-modal');
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
  }

  function onClearDbInput() {
    const input = document.getElementById('clear-db-confirm-input').value.trim().toUpperCase();
    document.getElementById('clear-db-confirm-btn').disabled = input !== 'CLEAR DB';
  }

  async function confirmClearDatabase() {
    const status = document.getElementById('run-status');
    closeClearDbModal();
    status.textContent = 'Clearing database...';
    try {
      const out = await fetchJson('/admin/clear-db', { method: 'POST' });
      status.textContent = `Database cleared: snapshots=${out.deleted.odds_snapshots}, alerts=${out.deleted.alerts}, source_events=${out.deleted.source_events}, canonical_matches=${out.deleted.canonical_matches}`;
      await refresh();
    } catch (err) {
      status.textContent = `Clear DB failed: ${err}`;
    }
  }

  document.getElementById('clear-db-modal').addEventListener('click', (event) => {
    if (event.target.id === 'clear-db-modal') {
      closeClearDbModal();
    }
  });

  document.getElementById('history-modal').addEventListener('click', (event) => {
    if (event.target.id === 'history-modal') {
      closeHistoryModal();
    }
  });

  refresh();
  setInterval(refresh, 30000);
  setInterval(updateCountdown, 1000);
</script>
</body>
</html>
"""


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


@app.post("/admin/clear-db")
def admin_clear_db(db: Session = Depends(get_db)) -> dict:
    deleted = {
        "alerts": int(db.scalar(select(func.count()).select_from(Alert)) or 0),
        "odds_snapshots": int(db.scalar(select(func.count()).select_from(OddsSnapshot)) or 0),
        "source_events": int(db.scalar(select(func.count()).select_from(SourceEvent)) or 0),
        "canonical_matches": int(db.scalar(select(func.count()).select_from(CanonicalMatch)) or 0),
    }

    db.query(Alert).delete(synchronize_session=False)
    db.query(OddsSnapshot).delete(synchronize_session=False)
    db.query(SourceEvent).delete(synchronize_session=False)
    db.query(CanonicalMatch).delete(synchronize_session=False)
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
