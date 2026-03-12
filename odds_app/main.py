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
from odds_app.services.coverage import get_scrape_coverage_metrics
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
    .spark-cell { min-width: 110px; }
    .spark-row { display: flex; align-items: center; gap: 4px; line-height: 1; margin-bottom: 2px; }
    .spark-row:last-child { margin-bottom: 0; }
    .spark-tag { width: 18px; font-size: 10px; color: var(--muted); }
    .sparkline { width: 76px; height: 18px; display: block; }
    .status-pill { border: 1px solid var(--border); border-radius: 999px; padding: 2px 8px; font-size: 11px; font-weight: 700; display: inline-block; }
    .status-good { color: #9df7bc; background: rgba(29, 191, 115, 0.18); border-color: rgba(29, 191, 115, 0.45); }
    .status-warn { color: #ffe5a0; background: rgba(242, 182, 58, 0.18); border-color: rgba(242, 182, 58, 0.45); }
    .status-bad { color: #ffb0b0; background: rgba(228, 88, 88, 0.2); border-color: rgba(228, 88, 88, 0.45); }
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

  <h2 class="section-title">Coverage health</h2>
  <div id="coverage-meta" class="meta">Loading coverage...</div>
  <div class="table-wrap">
    <table id="coverage-table">
      <thead>
        <tr>
          <th>Source</th><th>Sport</th><th>Active Events</th><th>Upcoming 24h</th><th>Upcoming 72h</th><th>Upcoming 7d</th><th>Upcoming 14d</th><th>Status</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <h2 class="section-title">Matches on both sources (comparison)</h2>
  <div class="table-wrap">
    <table id="overlap-table">
      <thead>
        <tr>
          <th>Sport</th><th>Match ID</th><th>Match</th>
          <th>PS H</th><th>PS D</th><th>PS A</th>
          <th>ES H</th><th>ES D</th><th>ES A</th>
          <th>Edge H %</th><th>Better (H)</th><th>Kickoff (UTC)</th><th>Trend (H)</th><th>Chart</th>
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

  function coverageStatus(row) {
    const up24 = Number(row.upcoming_24h ?? 0);
    const up72 = Number(row.upcoming_72h ?? 0);
    const active = Number(row.active_events ?? 0);
    if (active <= 0 || up72 <= 0) return { label: 'BAD', cls: 'status-bad' };
    if (up24 < 3) return { label: 'WARN', cls: 'status-warn' };
    return { label: 'GOOD', cls: 'status-good' };
  }

  function renderCoverage(payload) {
    const meta = document.getElementById('coverage-meta');
    const tbody = document.querySelector('#coverage-table tbody');

    const latest = payload.latest_scrape_by_source ?? {};
    const snap30 = payload.snapshot_count_last_30m ?? {};
    const generated = payload.generated_at ? formatDateUtc(payload.generated_at) : '-';
    meta.textContent = `generated=${generated} | latest: ps3838=${latest.ps3838 ?? '-'} e_stave=${latest.e_stave ?? '-'} | snapshots last 30m: ps3838=${snap30.ps3838 ?? 0} e_stave=${snap30.e_stave ?? 0}`;

    tbody.innerHTML = '';
    for (const row of (payload.coverage ?? [])) {
      const st = coverageStatus(row);
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.source}</td>
        <td>${row.sport}</td>
        <td>${row.active_events ?? 0}</td>
        <td>${row.upcoming_24h ?? 0}</td>
        <td>${row.upcoming_72h ?? 0}</td>
        <td>${row.upcoming_168h ?? 0}</td>
        <td>${row.upcoming_336h ?? 0}</td>
        <td><span class="status-pill ${st.cls}">${st.label}</span></td>
      `;
      tbody.appendChild(tr);
    }
  }

  function renderSourceTable(tableId, rows) {
    const tbody = document.querySelector(`#${tableId} tbody`);
    tbody.innerHTML = '';
    for (const row of rows) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.sport ?? '-'}</td>
        <td><a href="/matches/${row.canonical_match_id}/details" target="_blank">${row.canonical_match_id}</a></td>
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

  function sparklineSvg(values, color) {
    if (!values || values.length === 0) {
      return '<span class="muted">-</span>';
    }
    const w = 76;
    const h = 18;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const points = values
      .map((value, idx) => {
        const x = values.length === 1 ? w / 2 : (idx * w) / (values.length - 1);
        const y = h - ((value - min) / range) * h;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
    return `<svg class="sparkline" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline fill="none" stroke="${color}" stroke-width="1.8" points="${points}"/></svg>`;
  }

  function renderTrendCell(trend) {
    const ps = trend?.ps3838_home ?? [];
    const es = trend?.estave_home ?? [];
    const psLine = sparklineSvg(ps, '#4ea1ff');
    const esLine = sparklineSvg(es, '#f6a75a');
    return `
      <div class="spark-cell">
        <div class="spark-row"><span class="spark-tag">PS</span>${psLine}</div>
        <div class="spark-row"><span class="spark-tag">ES</span>${esLine}</div>
      </div>
    `;
  }

  function renderOverlapTable(rows, trendByMatch = {}) {
    const tbody = document.querySelector('#overlap-table tbody');
    tbody.innerHTML = '';
    for (const row of rows) {
      const edge = row.edge_pct_estave_vs_ps3838_home;
      const edgeClass = edge == null ? '' : (edge >= 0 ? 'positive' : 'negative');
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.sport ?? '-'}</td>
        <td><a href="/matches/${row.canonical_match_id}/details" target="_blank">${row.canonical_match_id}</a></td>
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
        <td>${renderTrendCell(trendByMatch[row.canonical_match_id])}</td>
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
    const [schedule, coverage, overlap, overlapTrends, psRows, esRows, alerts] = await Promise.all([
      fetchJson('/admin/next-scrape'),
      fetchJson('/admin/coverage'),
      fetchJson('/matches/overlap?limit=200'),
      fetchJson('/matches/overlap-trends?limit=200&hours=72&max_points=18'),
      fetchJson('/matches/source/ps3838?limit=300'),
      fetchJson('/matches/source/e_stave?limit=300'),
      fetchJson('/alerts/recent?limit=80'),
    ]);
    const trendByMatch = {};
    for (const trend of (overlapTrends.trends ?? [])) {
      trendByMatch[trend.canonical_match_id] = trend;
    }
    renderSchedule(schedule);
    renderCoverage(coverage);
    renderOverlapTable(overlap, trendByMatch);
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
    #movement-canvas { width: 100%; height: 320px; }
    #no-chart-data { display: none; margin-top: 8px; }
  </style>
</head>
<body>
  <div class="container">
    <div style="margin-bottom:8px;"><a href="/">← Back to dashboard</a></div>
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
      <canvas id="movement-canvas"></canvas>
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
        noData.style.display = 'block';
        canvas.style.display = 'none';
      } else {
        noData.style.display = 'none';
        canvas.style.display = 'block';
      }

      if (movementChart) movementChart.destroy();
      movementChart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: { datasets },
        options: {
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
