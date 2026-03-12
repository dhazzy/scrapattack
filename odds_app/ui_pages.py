def render_admin_page() -> str:
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Admin Control Center</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            void: '#05070f',
            panel: '#0b1220',
            line: '#25324d',
          },
          boxShadow: {
            glow: '0 0 0 1px rgba(96,165,250,0.15), 0 10px 40px rgba(2,8,23,0.8)',
          },
        },
      },
    };
  </script>
  <style>
    :root {
      --bg: #05070f;
      --panel: #0b1220;
      --panel-2: #0f1729;
      --text: #e5edf7;
      --muted: #9eb0c9;
      --border: #233452;
      --success: #1dbf73;
      --danger: #e45858;
      --table-head: #14213b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      background:
        radial-gradient(circle at top, rgba(56, 189, 248, 0.16), transparent 40%),
        radial-gradient(circle at 20% 20%, rgba(96, 165, 250, 0.12), transparent 35%),
        var(--bg);
      color: var(--text);
      padding: 18px;
    }
    .container { max-width: 1500px; margin: 0 auto; }
    .header { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; margin-bottom: 14px; flex-wrap: wrap; }
    h1 { margin: 0; font-size: 28px; }
    .meta { color: var(--muted); font-size: 13px; margin-top: 4px; }
    a { color: #8dc0ff; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; margin-bottom: 14px; }
    .card { background: linear-gradient(180deg, rgba(11,18,32,0.88), rgba(15,23,41,0.88)); border: 1px solid var(--border); border-radius: 14px; padding: 12px; margin-bottom: 12px; box-shadow: 0 0 0 1px rgba(96,165,250,0.10), 0 15px 40px rgba(2,8,23,0.55); backdrop-filter: blur(4px); }
    .label { color: var(--muted); font-size: 12px; margin-bottom: 4px; }
    .value { font-size: 18px; font-weight: 700; }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; align-items: center; }
    button { border: 1px solid var(--border); background: linear-gradient(180deg, rgba(37,99,235,0.95), rgba(30,64,175,0.9)); color: white; padding: 9px 12px; border-radius: 10px; cursor: pointer; font-weight: 600; box-shadow: 0 0 0 1px rgba(96,165,250,0.2), 0 8px 22px rgba(2,8,23,0.55); }
    button:hover { filter: brightness(1.08); }
    button.danger { background: #532222; border-color: #7b2f2f; }
    .status { color: var(--muted); font-size: 12px; align-self: center; }
    .section-title { margin: 22px 0 8px; font-size: 18px; }
    .table-wrap { border: 1px solid var(--border); border-radius: 14px; overflow: auto; background: rgba(15,23,41,0.72); backdrop-filter: blur(6px); margin-bottom: 18px; }
    .status-pill { border: 1px solid var(--border); border-radius: 999px; padding: 2px 8px; font-size: 11px; font-weight: 700; display: inline-block; }
    .status-good { color: #9df7bc; background: rgba(29, 191, 115, 0.18); border-color: rgba(29, 191, 115, 0.45); }
    .status-warn { color: #ffe5a0; background: rgba(242, 182, 58, 0.18); border-color: rgba(242, 182, 58, 0.45); }
    .status-bad { color: #ffb0b0; background: rgba(228, 88, 88, 0.2); border-color: rgba(228, 88, 88, 0.45); }
    .positive { color: var(--success); font-weight: 700; }
    .negative { color: var(--danger); font-weight: 700; }
    table { border-collapse: collapse; width: 100%; min-width: 980px; }
    th, td { border-bottom: 1px solid #1f2f4d; padding: 8px; font-size: 12px; vertical-align: top; white-space: nowrap; }
    th { background: var(--table-head); text-align: left; position: sticky; top: 0; z-index: 1; }
    tr:hover td { background: #13213f; }
    .hint { color: var(--muted); font-size: 12px; }
    .grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 12px; }
    .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    input, select {
      background: #0b1220;
      color: #e5edf7;
      border: 1px solid #233452;
      border-radius: 8px;
      padding: 7px;
      font-size: 12px;
    }
    pre {
      margin: 8px 0 0;
      padding: 10px;
      border: 1px solid #233452;
      border-radius: 8px;
      background: #0b1220;
      color: #c7d7ee;
      font-size: 12px;
      max-height: 260px;
      overflow: auto;
      white-space: pre-wrap;
    }
    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(2, 6, 23, 0.75);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 1000;
      padding: 16px;
    }
    .modal-backdrop.show { display: flex; }
    .modal {
      width: min(520px, 100%);
      background: linear-gradient(180deg, rgba(21,35,63,0.97), rgba(15,24,42,0.96));
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      box-shadow: 0 0 0 1px rgba(96,165,250,0.12), 0 15px 60px rgba(2,8,23,0.65);
    }
    .modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
    #scrape-run-history-wrap { position: relative; width: 100%; height: 220px; }
    #scrape-run-history-canvas { width: 100% !important; height: 100% !important; display: block; }
  </style>
</head>
<body class="min-h-screen bg-void text-slate-100 antialiased">
<div class="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_top,rgba(56,189,248,0.14),transparent_45%)]"></div>
<div class="container relative mx-auto max-w-[1500px] space-y-4">
  <div class="header">
    <div>
      <h1>Admin Control Center</h1>
      <div class="meta">Operations, diagnostics, reliability, probe testing, and runtime controls.</div>
    </div>
    <div><a href="/markets" class="rounded-xl border border-line bg-panel/60 px-4 py-2 text-sm text-cyan-300 shadow-glow transition hover:border-cyan-400 hover:text-cyan-200">Open Markets & Alerts page</a></div>
  </div>

  <div class="cards">
    <div class="card">
      <div class="label">Next scheduled scrape</div>
      <div id="next-scrape-time" class="value">-</div>
      <div id="next-scrape-countdown" class="hint">-</div>
    </div>
    <div class="card">
      <div class="label">Last scrape</div>
      <div id="last-scrape-time" class="value">-</div>
      <div id="scrape-interval" class="hint">-</div>
    </div>
  </div>

  <div class="actions">
    <button onclick="forceRefresh()">Force refresh now</button>
    <button onclick="forceCompare()">Force compare now</button>
    <button onclick="runCanaryNow()">Run canary now</button>
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

  <h2 class="section-title">Coverage trend (last 24h)</h2>
  <div id="coverage-trend-meta" class="meta">Loading trend...</div>
  <div class="table-wrap">
    <table id="coverage-trend-table">
      <thead><tr><th>Source</th><th>Events trend</th><th>Future 72h trend</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <h2 class="section-title">Coverage gaps</h2>
  <div class="actions" style="margin-bottom:8px;">
    <label class="hint" for="coverage-gap-days">Days</label>
    <input id="coverage-gap-days" type="number" min="1" value="14" style="width:90px;" />
    <button onclick="refreshCoverageGaps()">Refresh gaps</button>
  </div>
  <div id="coverage-gaps-meta" class="meta">Loading coverage gaps...</div>
  <div class="table-wrap">
    <table id="coverage-gaps-table">
      <thead><tr><th>Source</th><th>Sport</th><th>24h</th><th>72h</th><th>7d</th><th>14d</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <h2 class="section-title">Scrape reliability (last 6h)</h2>
  <div id="scrape-health-meta" class="meta">Loading scrape health...</div>
  <div class="table-wrap">
    <table id="scrape-health-table">
      <thead><tr>
        <th>Source</th><th>Runs</th><th>Success %</th><th>Status</th><th>Consecutive Failures</th><th>Avg Quotes</th><th>Avg Duration ms</th><th>Last Success</th><th>Last Failure</th><th>Last Error</th>
      </tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <h2 class="section-title">Scrape run history (success rate)</h2>
  <div id="scrape-run-history-meta" class="meta">Loading scrape run history...</div>
  <div class="card" style="margin-bottom:18px;">
    <div class="row" style="justify-content:flex-end; margin-bottom:8px;">
      <label for="scrape-run-source-filter" class="hint">Source</label>
      <select id="scrape-run-source-filter"><option value="all">All sources</option></select>
    </div>
    <div id="scrape-run-history-wrap"><canvas id="scrape-run-history-canvas"></canvas></div>
    <div id="scrape-run-history-empty" class="hint" style="display:none;">No scrape run history available in selected window.</div>
  </div>

  <h2 class="section-title">Runtime overrides</h2>
  <div id="runtime-overrides-meta" class="meta">Loading runtime overrides...</div>
  <div class="card" style="margin-bottom:18px;">
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;">
      <label class="hint">Scrape retries <input id="ovr-scrape-recovery-retry-count" type="number" min="0" /></label>
      <label class="hint">Backoff sec <input id="ovr-scrape-recovery-backoff-sec" type="number" step="0.1" min="0" /></label>
      <label class="hint">Min quotes success <input id="ovr-scrape-min-quotes-success" type="number" min="0" /></label>
      <label class="hint">Degraded fail count <input id="ovr-scrape-degraded-consecutive-failures" type="number" min="1" /></label>
      <label class="hint">Degraded cooldown sec <input id="ovr-scrape-degraded-cooldown-sec" type="number" min="0" /></label>
      <label class="hint">Drop threshold % <input id="ovr-odds-drop-threshold-pct" type="number" step="0.1" min="0" /></label>
      <label class="hint">Opening drop threshold % <input id="ovr-odds-drop-opening-threshold-pct" type="number" step="0.1" min="0" /></label>
      <label class="hint">Drop confirmations <input id="ovr-odds-drop-confirmation-count" type="number" min="1" /></label>
      <label class="hint">Confirmation window min <input id="ovr-odds-drop-confirmation-window-min" type="number" min="1" /></label>
      <label class="hint">Renotify improvement % <input id="ovr-odds-drop-renotify-improvement-pct" type="number" step="0.1" min="0" /></label>
    </div>
    <div class="actions" style="justify-content:flex-end; margin-top:10px;">
      <button onclick="saveRuntimeOverrides()">Apply overrides</button>
      <button onclick="resetRuntimeOverrides()">Reset overrides</button>
    </div>
  </div>

  <h2 class="section-title">Recent scrape runs</h2>
  <div id="scrape-runs-meta" class="meta">Loading scrape runs...</div>
  <div class="table-wrap">
    <table id="scrape-runs-table">
      <thead><tr><th>Start (UTC)</th><th>Source</th><th>Sport</th><th>Trigger</th><th>Mode</th><th>Success</th><th>Quotes</th><th>Duration ms</th><th>Error</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <h2 class="section-title">Canary summary</h2>
  <div class="actions" style="margin-bottom:8px;">
    <label class="hint"><input id="canary-create-alerts" type="checkbox" /> create alerts</label>
    <button onclick="runCanaryNow()">Run canary now</button>
  </div>
  <div id="canary-meta" class="meta">Loading canary...</div>
  <div class="table-wrap">
    <table id="canary-table">
      <thead><tr><th>Source</th><th>Status</th><th>Failing checks</th><th>Success %</th><th>Avg quotes</th><th>Upcoming 72h</th><th>Upcoming 168h</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <h2 class="section-title">Probe tools</h2>
  <div class="grid-2">
    <div class="card">
      <div class="label">e-stave probe</div>
      <div class="row">
        <label class="hint">Sports <input id="probe-estave-sports" value="soccer,tennis,basketball" /></label>
        <label class="hint">Min days <input id="probe-estave-min-days" type="number" step="0.5" value="0" /></label>
        <label class="hint">Max days <input id="probe-estave-max-days" type="number" step="0.5" value="14" /></label>
        <label class="hint">Max pages <input id="probe-estave-max-pages" type="number" value="90" /></label>
        <label class="hint">Page size <input id="probe-estave-page-size" type="number" value="25" /></label>
      </div>
      <div class="row" style="margin-top:8px;">
        <label class="hint">g values <input id="probe-estave-g-values" value="25" /></label>
        <label class="hint">extra b values <input id="probe-estave-b-values" value="" /></label>
        <label class="hint"><input id="probe-estave-persist" type="checkbox" /> persist to DB</label>
        <button onclick="runEstaveProbe()">Run e-stave probe</button>
      </div>
      <pre id="probe-estave-output">Waiting for run...</pre>
    </div>
    <div class="card">
      <div class="label">Vodds probe</div>
      <div class="row">
        <label class="hint">Sports <input id="probe-vodds-sports" value="soccer,tennis,basketball" /></label>
        <label class="hint">Min days <input id="probe-vodds-min-days" type="number" step="0.5" value="0" /></label>
        <label class="hint">Max days <input id="probe-vodds-max-days" type="number" step="0.5" value="14" /></label>
        <label class="hint">Timeout sec <input id="probe-vodds-timeout" type="number" value="60" /></label>
      </div>
      <div class="row" style="margin-top:8px;">
        <label class="hint">Headless
          <select id="probe-vodds-headless">
            <option value="">default</option>
            <option value="true">true</option>
            <option value="false">false</option>
          </select>
        </label>
        <label class="hint">Proxy URL <input id="probe-vodds-proxy" value="" /></label>
        <label class="hint"><input id="probe-vodds-persist" type="checkbox" /> persist to DB</label>
        <button onclick="runVoddsProbe()">Run Vodds probe</button>
      </div>
      <pre id="probe-vodds-output">Waiting for run...</pre>
    </div>
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

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns"></script>
<script>
  let nextScrapeAtMs = null;
  let scrapeRunHistoryChart = null;
  let scrapeRunHistoryPayload = null;

  async function fetchJson(url, options = {}) {
    const res = await fetch(url, options);
    if (!res.ok) {
      let detail = '';
      try { detail = await res.text(); } catch (_) {}
      throw new Error(`HTTP ${res.status}: ${url}${detail ? ` :: ${detail}` : ''}`);
    }
    return await res.json();
  }

  function formatDateUtc(iso) {
    if (!iso) return '-';
    return new Date(iso).toISOString().replace('T', ' ').replace('Z', '');
  }

  function formatDuration(sec) {
    if (sec == null) return '-';
    const s = Math.max(0, Math.floor(sec));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const r = s % 60;
    return `${h}h ${m}m ${r}s`;
  }

  function csvToList(value) {
    if (!value) return [];
    return value.split(',').map((v) => v.trim()).filter(Boolean);
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
    document.getElementById('next-scrape-time').textContent = formatDateUtc(meta.next_scrape_at);
    document.getElementById('last-scrape-time').textContent = formatDateUtc(meta.last_scrape_at);
    document.getElementById('scrape-interval').textContent = `interval: ${meta.interval_sec}s`;
    nextScrapeAtMs = meta.next_scrape_at ? new Date(meta.next_scrape_at).getTime() : null;
    updateCountdown();
  }

  function sparklineSvg(values, color, width = 220, height = 26) {
    if (!values || values.length === 0) return '<span class="hint">-</span>';
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const points = values.map((v, i) => {
      const x = values.length === 1 ? width / 2 : (i * width) / (values.length - 1);
      const y = height - ((v - min) / range) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="width:${width}px;height:${height}px"><polyline fill="none" stroke="${color}" stroke-width="1.8" points="${points}"/></svg>`;
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
    meta.textContent = `generated=${generated} | latest ps3838=${latest.ps3838 ?? '-'} e_stave=${latest.e_stave ?? '-'} | snapshots 30m ps3838=${snap30.ps3838 ?? 0} e_stave=${snap30.e_stave ?? 0}`;
    tbody.innerHTML = '';
    for (const row of (payload.coverage ?? [])) {
      const st = coverageStatus(row);
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.source}</td><td>${row.sport}</td><td>${row.active_events ?? 0}</td>
        <td>${row.upcoming_24h ?? 0}</td><td>${row.upcoming_72h ?? 0}</td><td>${row.upcoming_168h ?? 0}</td><td>${row.upcoming_336h ?? 0}</td>
        <td><span class="status-pill ${st.cls}">${st.label}</span></td>
      `;
      tbody.appendChild(tr);
    }
  }

  function renderCoverageTrend(payload) {
    const meta = document.getElementById('coverage-trend-meta');
    const tbody = document.querySelector('#coverage-trend-table tbody');
    const generated = payload.generated_at ? formatDateUtc(payload.generated_at) : '-';
    meta.textContent = `generated=${generated} | runs=${payload.runs ?? '-'} | hours=${payload.hours ?? 24} | bucket=${payload.bucket_minutes ?? 30}m`;
    tbody.innerHTML = '';
    for (const row of (payload.series ?? [])) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${row.source}</td><td>${sparklineSvg(row.event_counts ?? [], '#4ea1ff')}</td><td>${sparklineSvg(row.future_72h_counts ?? [], '#f6a75a')}</td>`;
      tbody.appendChild(tr);
    }
  }

  function horizonStatusBadge(item) {
    const status = item?.status || 'red';
    const cls = status === 'green' ? 'status-good' : (status === 'yellow' ? 'status-warn' : 'status-bad');
    const text = `${item?.count ?? 0} (${status.toUpperCase()})`;
    return `<span class="status-pill ${cls}">${text}</span>`;
  }

  function renderCoverageGaps(payload) {
    const meta = document.getElementById('coverage-gaps-meta');
    const tbody = document.querySelector('#coverage-gaps-table tbody');
    const generated = payload.generated_at ? formatDateUtc(payload.generated_at) : '-';
    const summary = (payload.summary_by_source ?? []).map((s) => `${s.source}: red=${s.red}, yellow=${s.yellow}, green=${s.green}`).join(' | ');
    meta.textContent = `generated=${generated} | days=${payload.days ?? '-'} | ${summary || 'no data'}`;
    tbody.innerHTML = '';
    for (const row of (payload.rows ?? [])) {
      const byHour = {};
      for (const h of (row.horizons ?? [])) byHour[h.horizon_hours] = h;
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.source}</td><td>${row.sport}</td>
        <td>${horizonStatusBadge(byHour[24])}</td><td>${horizonStatusBadge(byHour[72])}</td><td>${horizonStatusBadge(byHour[168])}</td><td>${horizonStatusBadge(byHour[336])}</td>
      `;
      tbody.appendChild(tr);
    }
  }

  function renderScrapeHealth(payload) {
    const meta = document.getElementById('scrape-health-meta');
    const tbody = document.querySelector('#scrape-health-table tbody');
    const generated = payload.generated_at ? formatDateUtc(payload.generated_at) : '-';
    meta.textContent = `generated=${generated} | window=${payload.window_hours ?? 6}h | degraded_threshold=${payload.degraded_threshold ?? '-'}`;
    tbody.innerHTML = '';
    for (const row of (payload.sources ?? [])) {
      const status = row.status ?? 'GOOD';
      const statusClass = status === 'DEGRADED' ? 'status-bad' : (status === 'WARN' ? 'status-warn' : 'status-good');
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.source}</td><td>${row.runs ?? 0}</td><td>${row.success_rate_pct ?? 0}</td>
        <td><span class="status-pill ${statusClass}">${status}</span></td>
        <td>${row.consecutive_failures ?? 0}</td><td>${row.avg_quotes ?? 0}</td><td>${row.avg_duration_ms ?? 0}</td>
        <td>${formatDateUtc(row.last_success_at)}</td><td>${formatDateUtc(row.last_failure_at)}</td><td>${row.last_error ?? '-'}</td>
      `;
      tbody.appendChild(tr);
    }
  }

  function runHistoryColor(source) {
    return source === 'e_stave' ? '#f6a75a' : '#4ea1ff';
  }

  function selectedRunHistorySource() {
    const el = document.getElementById('scrape-run-source-filter');
    return el ? (el.value || 'all') : 'all';
  }

  function syncRunHistoryFilterOptions(payload) {
    const el = document.getElementById('scrape-run-source-filter');
    if (!el) return;
    const current = el.value || 'all';
    const sources = [...new Set((payload.series ?? []).map((r) => r.source).filter(Boolean))].sort();
    const desired = ['all', ...sources];
    const same = el.options.length === desired.length && desired.every((v, i) => el.options[i].value === v);
    if (!same) {
      el.innerHTML = '';
      for (const value of desired) {
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = value === 'all' ? 'All sources' : value;
        el.appendChild(opt);
      }
    }
    el.value = desired.includes(current) ? current : 'all';
  }

  function renderScrapeRunHistory(payload) {
    scrapeRunHistoryPayload = payload;
    syncRunHistoryFilterOptions(payload);
    const meta = document.getElementById('scrape-run-history-meta');
    const empty = document.getElementById('scrape-run-history-empty');
    const canvas = document.getElementById('scrape-run-history-canvas');
    const sourceFilter = selectedRunHistorySource();
    const generated = payload.generated_at ? formatDateUtc(payload.generated_at) : '-';
    meta.textContent = `generated=${generated} | source=${sourceFilter} | runs=${payload.runs ?? '-'} | hours=${payload.hours ?? 24} | bucket=${payload.bucket_minutes ?? 15}m`;

    if (scrapeRunHistoryChart) {
      scrapeRunHistoryChart.destroy();
      scrapeRunHistoryChart = null;
    }
    const buckets = payload.buckets ?? [];
    const filteredSeries = (payload.series ?? []).filter((row) => sourceFilter === 'all' || row.source === sourceFilter);
    const datasets = filteredSeries.map((row) => ({
      label: `${row.source} success %`,
      data: buckets.map((bucket, idx) => ({ x: bucket, y: row.success_rate_pct?.[idx] ?? null })),
      borderColor: runHistoryColor(row.source),
      backgroundColor: runHistoryColor(row.source),
      borderWidth: 2,
      pointRadius: 0,
      tension: 0.18,
      spanGaps: true,
    }));
    const hasPoints = datasets.some((ds) => ds.data.some((p) => p.y != null));
    if (!hasPoints) {
      empty.style.display = 'block';
      canvas.style.display = 'none';
      return;
    }
    empty.style.display = 'none';
    canvas.style.display = 'block';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    scrapeRunHistoryChart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { datasets },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { type: 'time', ticks: { color: '#c6d3e8' }, grid: { color: '#223450' } },
          y: { min: 0, max: 100, ticks: { color: '#c6d3e8' }, grid: { color: '#223450' } },
        },
        plugins: { legend: { labels: { color: '#dce8f8' } } },
      },
    });
  }

  function renderScrapeRuns(payload) {
    const meta = document.getElementById('scrape-runs-meta');
    const tbody = document.querySelector('#scrape-runs-table tbody');
    const rows = payload.runs ?? [];
    meta.textContent = `runs=${rows.length}`;
    tbody.innerHTML = '';
    for (const row of rows) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${formatDateUtc(row.started_at)}</td><td>${row.source}</td><td>${row.sport ?? '-'}</td><td>${row.trigger ?? '-'}</td><td>${row.mode ?? '-'}</td>
        <td class="${row.success ? 'positive' : 'negative'}">${row.success ? 'YES' : 'NO'}</td>
        <td>${row.quotes_count ?? 0}</td><td>${row.duration_ms ?? 0}</td><td>${row.error_message ?? '-'}</td>
      `;
      tbody.appendChild(tr);
    }
  }

  function renderCanary(payload) {
    const meta = document.getElementById('canary-meta');
    const tbody = document.querySelector('#canary-table tbody');
    const generated = payload.generated_at ? formatDateUtc(payload.generated_at) : '-';
    meta.textContent = `generated=${generated} | status=${payload.status ?? '-'} | alerts_created=${payload.alerts_created ?? 0}`;
    tbody.innerHTML = '';
    for (const row of (payload.sources ?? [])) {
      const statusClass = row.status === 'pass' ? 'status-good' : 'status-bad';
      const failing = (row.failing_checks ?? []).map((c) => `${c.name}:${c.value}<${c.threshold}`).join(' | ') || '-';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.source}</td><td><span class="status-pill ${statusClass}">${(row.status || '-').toUpperCase()}</span></td>
        <td>${failing}</td><td>${row.health?.success_rate_pct ?? '-'}</td><td>${row.health?.avg_quotes ?? '-'}</td>
        <td>${row.upcoming?.upcoming_72h ?? '-'}</td><td>${row.upcoming?.upcoming_168h ?? '-'}</td>
      `;
      tbody.appendChild(tr);
    }
  }

  function setInputValue(id, value) {
    const el = document.getElementById(id);
    if (!el || document.activeElement === el) return;
    el.value = value == null ? '' : String(value);
  }

  function renderRuntimeOverrides(payload) {
    const meta = document.getElementById('runtime-overrides-meta');
    const overrides = payload.overrides ?? {};
    meta.textContent = `active_overrides=${Object.keys(overrides).length} | allowed=${(payload.allowed_keys ?? []).length}`;
    setInputValue('ovr-scrape-recovery-retry-count', overrides.scrape_recovery_retry_count);
    setInputValue('ovr-scrape-recovery-backoff-sec', overrides.scrape_recovery_backoff_sec);
    setInputValue('ovr-scrape-min-quotes-success', overrides.scrape_min_quotes_success);
    setInputValue('ovr-scrape-degraded-consecutive-failures', overrides.scrape_degraded_consecutive_failures);
    setInputValue('ovr-scrape-degraded-cooldown-sec', overrides.scrape_degraded_cooldown_sec);
    setInputValue('ovr-odds-drop-threshold-pct', overrides.odds_drop_threshold_pct);
    setInputValue('ovr-odds-drop-opening-threshold-pct', overrides.odds_drop_opening_threshold_pct);
    setInputValue('ovr-odds-drop-confirmation-count', overrides.odds_drop_confirmation_count);
    setInputValue('ovr-odds-drop-confirmation-window-min', overrides.odds_drop_confirmation_window_min);
    setInputValue('ovr-odds-drop-renotify-improvement-pct', overrides.odds_drop_renotify_improvement_pct);
  }

  function collectRuntimeOverridePayload() {
    const readNum = (id) => {
      const el = document.getElementById(id);
      if (!el) return null;
      const raw = (el.value || '').trim();
      if (!raw) return null;
      const n = Number(raw);
      return Number.isFinite(n) ? n : null;
    };
    const payload = {};
    const put = (k, v) => { if (v != null) payload[k] = v; };
    put('scrape_recovery_retry_count', readNum('ovr-scrape-recovery-retry-count'));
    put('scrape_recovery_backoff_sec', readNum('ovr-scrape-recovery-backoff-sec'));
    put('scrape_min_quotes_success', readNum('ovr-scrape-min-quotes-success'));
    put('scrape_degraded_consecutive_failures', readNum('ovr-scrape-degraded-consecutive-failures'));
    put('scrape_degraded_cooldown_sec', readNum('ovr-scrape-degraded-cooldown-sec'));
    put('odds_drop_threshold_pct', readNum('ovr-odds-drop-threshold-pct'));
    put('odds_drop_opening_threshold_pct', readNum('ovr-odds-drop-opening-threshold-pct'));
    put('odds_drop_confirmation_count', readNum('ovr-odds-drop-confirmation-count'));
    put('odds_drop_confirmation_window_min', readNum('ovr-odds-drop-confirmation-window-min'));
    put('odds_drop_renotify_improvement_pct', readNum('ovr-odds-drop-renotify-improvement-pct'));
    return payload;
  }

  async function saveRuntimeOverrides() {
    const status = document.getElementById('run-status');
    status.textContent = 'Applying runtime overrides...';
    try {
      await fetchJson('/admin/runtime-overrides', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(collectRuntimeOverridePayload()) });
      status.textContent = 'Runtime overrides updated';
      await refresh();
    } catch (err) {
      status.textContent = `Override update failed: ${err}`;
    }
  }

  async function resetRuntimeOverrides() {
    const status = document.getElementById('run-status');
    status.textContent = 'Resetting runtime overrides...';
    try {
      await fetchJson('/admin/runtime-overrides/reset', { method: 'POST' });
      status.textContent = 'Runtime overrides reset';
      await refresh();
    } catch (err) {
      status.textContent = `Override reset failed: ${err}`;
    }
  }

  async function runEstaveProbe() {
    const status = document.getElementById('run-status');
    const output = document.getElementById('probe-estave-output');
    const persist = document.getElementById('probe-estave-persist').checked;
    const payload = {
      sports: csvToList(document.getElementById('probe-estave-sports').value),
      min_days: Number(document.getElementById('probe-estave-min-days').value || 0),
      max_days: Number(document.getElementById('probe-estave-max-days').value || 14),
      max_pages_per_query: Number(document.getElementById('probe-estave-max-pages').value || 0),
      page_size: Number(document.getElementById('probe-estave-page-size').value || 0),
      g_values: document.getElementById('probe-estave-g-values').value || null,
      extra_b_values: document.getElementById('probe-estave-b-values').value || null,
    };
    status.textContent = 'Running e-stave probe...';
    output.textContent = 'Running...';
    try {
      const out = await fetchJson(`/admin/probe/estave?persist=${persist ? 'true' : 'false'}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      output.textContent = JSON.stringify(out, null, 2);
      status.textContent = `e-stave probe done: filtered=${out.summary?.filtered_quotes_total ?? '-'} alerts=${out.alerts_created ?? 0}`;
      if (persist) await refresh();
    } catch (err) {
      output.textContent = String(err);
      status.textContent = `e-stave probe failed: ${err}`;
    }
  }

  async function runVoddsProbe() {
    const status = document.getElementById('run-status');
    const output = document.getElementById('probe-vodds-output');
    const persist = document.getElementById('probe-vodds-persist').checked;
    const headlessRaw = document.getElementById('probe-vodds-headless').value;
    const payload = {
      sports: csvToList(document.getElementById('probe-vodds-sports').value),
      min_days: Number(document.getElementById('probe-vodds-min-days').value || 0),
      max_days: Number(document.getElementById('probe-vodds-max-days').value || 14),
      timeout_sec: Number(document.getElementById('probe-vodds-timeout').value || 60),
      headless: headlessRaw === '' ? null : headlessRaw,
      proxy_url: document.getElementById('probe-vodds-proxy').value || null,
    };
    status.textContent = 'Running Vodds probe...';
    output.textContent = 'Running...';
    try {
      const out = await fetchJson(`/admin/probe/vodds?persist=${persist ? 'true' : 'false'}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      output.textContent = JSON.stringify(out, null, 2);
      status.textContent = `Vodds probe done: filtered=${out.summary?.filtered_quotes_total ?? '-'} alerts=${out.alerts_created ?? 0}`;
      if (persist) await refresh();
    } catch (err) {
      output.textContent = String(err);
      status.textContent = `Vodds probe failed: ${err}`;
    }
  }

  async function runCanaryNow() {
    const status = document.getElementById('run-status');
    const createAlerts = document.getElementById('canary-create-alerts').checked;
    status.textContent = 'Running canary checks...';
    try {
      const payload = await fetchJson(`/admin/canary?create_alerts=${createAlerts ? 'true' : 'false'}`);
      renderCanary(payload);
      status.textContent = `Canary ${payload.status ?? '-'} | alerts_created=${payload.alerts_created ?? 0}`;
      if (createAlerts) await refresh();
    } catch (err) {
      status.textContent = `Canary failed: ${err}`;
    }
  }

  async function refreshCoverageGaps() {
    const days = Math.max(1, Math.floor(Number(document.getElementById('coverage-gap-days').value || 14)));
    const payload = await fetchJson(`/admin/coverage-gaps?days=${days}`);
    renderCoverageGaps(payload);
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
    } catch (err) {
      status.textContent = `Force compare failed: ${err}`;
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
      status.textContent = `Database cleared: snapshots=${out.deleted.odds_snapshots}, alerts=${out.deleted.alerts}, source_events=${out.deleted.source_events}, canonical_matches=${out.deleted.canonical_matches}, scrape_runs=${out.deleted.scrape_runs ?? 0}`;
      await refresh();
    } catch (err) {
      status.textContent = `Clear DB failed: ${err}`;
    }
  }

  async function refresh() {
    const days = Math.max(1, Math.floor(Number(document.getElementById('coverage-gap-days').value || 14)));
    const [schedule, coverage, coverageTrend, coverageGaps, scrapeHealth, scrapeRunHistory, scrapeRuns, runtimeOverrides, canary] = await Promise.all([
      fetchJson('/admin/next-scrape'),
      fetchJson('/admin/coverage'),
      fetchJson('/admin/coverage-trend?runs=72&bucket_minutes=5'),
      fetchJson(`/admin/coverage-gaps?days=${days}`),
      fetchJson('/admin/scrape-health?window_hours=6'),
      fetchJson('/admin/scrape-runs/history?hours=24&bucket_minutes=5&runs=288'),
      fetchJson('/admin/scrape-runs/recent?limit=150'),
      fetchJson('/admin/runtime-overrides'),
      fetchJson('/admin/canary?create_alerts=false'),
    ]);
    renderSchedule(schedule);
    renderCoverage(coverage);
    renderCoverageTrend(coverageTrend);
    renderCoverageGaps(coverageGaps);
    renderScrapeHealth(scrapeHealth);
    renderScrapeRunHistory(scrapeRunHistory);
    renderScrapeRuns(scrapeRuns);
    renderRuntimeOverrides(runtimeOverrides);
    renderCanary(canary);
  }

  document.getElementById('clear-db-modal').addEventListener('click', (event) => {
    if (event.target.id === 'clear-db-modal') closeClearDbModal();
  });

  const scrapeRunFilterEl = document.getElementById('scrape-run-source-filter');
  if (scrapeRunFilterEl) {
    scrapeRunFilterEl.addEventListener('change', () => {
      if (scrapeRunHistoryPayload) renderScrapeRunHistory(scrapeRunHistoryPayload);
    });
  }

  refresh();
  setInterval(refresh, 30000);
  setInterval(updateCountdown, 1000);
</script>
</body>
</html>
"""


def render_markets_page() -> str:
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Markets & Alerts</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            void: '#05070f',
            panel: '#0b1220',
            line: '#25324d',
          },
          boxShadow: {
            glow: '0 0 0 1px rgba(96,165,250,0.15), 0 10px 40px rgba(2,8,23,0.8)',
          },
        },
      },
    };
  </script>
  <style>
    :root {
      --bg: #05070f;
      --panel: #0b1220;
      --panel-2: #0f1729;
      --text: #e5edf7;
      --muted: #9eb0c9;
      --border: #233452;
      --success: #1dbf73;
      --danger: #e45858;
      --table-head: #14213b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      background:
        radial-gradient(circle at top, rgba(56, 189, 248, 0.16), transparent 40%),
        radial-gradient(circle at 20% 20%, rgba(96, 165, 250, 0.12), transparent 35%),
        var(--bg);
      color: var(--text);
      padding: 18px;
    }
    .container { max-width: 1500px; margin: 0 auto; }
    .header { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; margin-bottom: 14px; flex-wrap: wrap; }
    h1 { margin: 0; font-size: 28px; }
    .meta { color: var(--muted); font-size: 13px; margin-top: 4px; }
    a { color: #8dc0ff; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; align-items: center; }
    button { border: 1px solid var(--border); background: linear-gradient(180deg, rgba(37,99,235,0.95), rgba(30,64,175,0.9)); color: white; padding: 9px 12px; border-radius: 10px; cursor: pointer; font-weight: 600; box-shadow: 0 0 0 1px rgba(96,165,250,0.2), 0 8px 22px rgba(2,8,23,0.55); }
    button:hover { filter: brightness(1.08); }
    .status { color: var(--muted); font-size: 12px; align-self: center; }
    .section-title { margin: 22px 0 8px; font-size: 18px; }
    .table-wrap { border: 1px solid var(--border); border-radius: 14px; overflow: auto; background: rgba(15,23,41,0.72); backdrop-filter: blur(6px); margin-bottom: 18px; }
    table { border-collapse: collapse; width: 100%; min-width: 980px; }
    th, td { border-bottom: 1px solid #1f2f4d; padding: 8px; font-size: 12px; vertical-align: top; white-space: nowrap; }
    th { background: var(--table-head); text-align: left; position: sticky; top: 0; z-index: 1; }
    tr:hover td { background: #13213f; }
    .spark-cell { min-width: 110px; }
    .spark-row { display: flex; align-items: center; gap: 4px; line-height: 1; margin-bottom: 2px; }
    .spark-row:last-child { margin-bottom: 0; }
    .spark-tag { width: 18px; font-size: 10px; color: var(--muted); }
    .positive { color: var(--success); font-weight: 700; }
    .negative { color: var(--danger); font-weight: 700; }
    .modal-backdrop { position: fixed; inset: 0; background: rgba(2, 6, 23, 0.75); display: none; align-items: center; justify-content: center; z-index: 1000; padding: 16px; backdrop-filter: blur(4px); }
    .modal-backdrop.show { display: flex; }
    .modal { width: min(980px, 100%); background: linear-gradient(180deg, rgba(21,35,63,0.97), rgba(15,24,42,0.96)); border: 1px solid var(--border); border-radius: 14px; padding: 16px; box-shadow: 0 0 0 1px rgba(96,165,250,0.12), 0 15px 60px rgba(2,8,23,0.65); }
    #history-chart-wrap { position: relative; width: 100%; height: 320px; }
    #odds-history-canvas { width: 100% !important; height: 100% !important; display: block; }
  </style>
</head>
<body class="min-h-screen bg-void text-slate-100 antialiased">
<div class="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_top,rgba(56,189,248,0.14),transparent_45%)]"></div>
<div class="container relative mx-auto max-w-[1500px] space-y-4">
  <div class="header">
    <div>
      <h1>Markets & Alerts</h1>
      <div class="meta">Match tables, overlap/edge view, and alerts.</div>
    </div>
    <div><a href="/admin" class="rounded-xl border border-line bg-panel/60 px-4 py-2 text-sm text-cyan-300 shadow-glow transition hover:border-cyan-400 hover:text-cyan-200">Back to Admin</a></div>
  </div>

  <div class="actions">
    <button onclick="refresh()">Refresh now</button>
    <button onclick="exportOverlapCsv()">Export overlap CSV</button>
    <button onclick="exportAlertsCsv()">Export alerts CSV</button>
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
          <th>Edge H %</th><th>Better (H)</th><th>Kickoff (UTC)</th><th>Trend (H)</th><th>Chart</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <h2 class="section-title">PS3838 matches</h2>
  <div class="table-wrap">
    <table id="ps-table">
      <thead><tr><th>Sport</th><th>Match ID</th><th>External ID</th><th>Match</th><th>League</th><th>Home</th><th>Draw</th><th>Away</th><th>Kickoff (UTC)</th><th>Last Scraped</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <h2 class="section-title">e-stave matches</h2>
  <div class="table-wrap">
    <table id="es-table">
      <thead><tr><th>Sport</th><th>Match ID</th><th>External ID</th><th>Match</th><th>League</th><th>Home</th><th>Draw</th><th>Away</th><th>Kickoff (UTC)</th><th>Last Scraped</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <h2 class="section-title">Recent odds-drop alerts</h2>
  <div class="table-wrap">
    <table id="odds-drop-table">
      <thead><tr><th>Time</th><th>Sport</th><th>Source</th><th>Match</th><th>Market</th><th>Selection</th><th>Baseline</th><th>Current</th><th>Drop %</th><th>Kickoff</th><th>Message</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <h2 class="section-title">Recent alerts (all)</h2>
  <div class="table-wrap">
    <table id="alerts-table">
      <thead><tr><th>Time</th><th>Sport</th><th>Type</th><th>Source</th><th>Market</th><th>Selection</th><th>Match</th><th>Kickoff</th><th>Sent</th><th>Message</th><th>Details</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</div>

<div id="history-modal" class="modal-backdrop" aria-hidden="true">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="history-title">
    <h3 id="history-title">Odds movement history</h3>
    <div id="history-subtitle" class="meta"></div>
    <div id="history-chart-wrap"><canvas id="odds-history-canvas"></canvas></div>
    <div id="history-empty" class="meta" style="display:none;">No odds history found for this match yet.</div>
    <div class="actions"><button onclick="closeHistoryModal()">Close</button></div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns"></script>
<script>
  let oddsHistoryChart = null;

  async function fetchJson(url, options = {}) {
    const res = await fetch(url, options);
    if (!res.ok) {
      let detail = '';
      try { detail = await res.text(); } catch (_) {}
      throw new Error(`HTTP ${res.status}: ${url}${detail ? ` :: ${detail}` : ''}`);
    }
    return await res.json();
  }

  function formatDateUtc(iso) {
    if (!iso) return '-';
    return new Date(iso).toISOString().replace('T', ' ').replace('Z', '');
  }

  function sparklineSvg(values, color, width = 76, height = 18) {
    if (!values || values.length === 0) return '<span class="meta">-</span>';
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const points = values.map((v, i) => {
      const x = values.length === 1 ? width / 2 : (i * width) / (values.length - 1);
      const y = height - ((v - min) / range) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="width:${width}px;height:${height}px"><polyline fill="none" stroke="${color}" stroke-width="1.8" points="${points}"/></svg>`;
  }

  function renderTrendCell(trend) {
    const ps = trend?.ps3838_home ?? [];
    const es = trend?.estave_home ?? [];
    return `<div class="spark-cell"><div class="spark-row"><span class="spark-tag">PS</span>${sparklineSvg(ps, '#4ea1ff')}</div><div class="spark-row"><span class="spark-tag">ES</span>${sparklineSvg(es, '#f6a75a')}</div></div>`;
  }

  function renderSourceTable(tableId, rows) {
    const tbody = document.querySelector(`#${tableId} tbody`);
    tbody.innerHTML = '';
    for (const row of rows) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.sport ?? '-'}</td>
        <td><a href="/matches/${row.canonical_match_id}/details" target="_blank">${row.canonical_match_id}</a></td>
        <td>${row.external_event_id}</td><td>${row.home_team} vs ${row.away_team}</td><td>${row.league ?? '-'}</td>
        <td>${row.latest_home_odds ?? '-'}</td><td>${row.latest_draw_odds ?? '-'}</td><td>${row.latest_away_odds ?? '-'}</td>
        <td>${row.kickoff_utc ?? '-'}</td><td>${row.last_scraped_at ?? '-'}</td>
      `;
      tbody.appendChild(tr);
    }
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
        <td>${row.ps3838_home_odds ?? '-'}</td><td>${row.ps3838_draw_odds ?? '-'}</td><td>${row.ps3838_away_odds ?? '-'}</td>
        <td>${row.estave_home_odds ?? '-'}</td><td>${row.estave_draw_odds ?? '-'}</td><td>${row.estave_away_odds ?? '-'}</td>
        <td class="${edgeClass}">${edge == null ? '-' : edge.toFixed(2) + '%'}</td>
        <td>${row.better_source_home ?? '-'}</td><td>${row.kickoff_utc ?? '-'}</td>
        <td>${renderTrendCell(trendByMatch[row.canonical_match_id])}</td>
        <td><button onclick="openHistoryChart(${row.canonical_match_id})">Chart</button></td>
      `;
      tbody.appendChild(tr);
    }
  }

  function formatCompactDetails(details) {
    if (!details || Object.keys(details).length === 0) return '-';
    return Object.entries(details).slice(0, 8).map(([k, v]) => `${k}=${v}`).join(' | ') || '-';
  }

  function renderOddsDropAlerts(rows) {
    const tbody = document.querySelector('#odds-drop-table tbody');
    tbody.innerHTML = '';
    for (const row of rows) {
      const details = row.details ?? {};
      const dropPct = details.drop_pct ?? details.drop_from_opening_pct ?? null;
      const baseline = details.baseline_odds_decimal ?? details.opening_odds_decimal ?? '-';
      const current = details.current_odds_decimal ?? '-';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${formatDateUtc(row.created_at)}</td><td>${row.sport ?? '-'}</td><td>${row.source ?? '-'}</td><td>${row.home_team} vs ${row.away_team}</td>
        <td>${row.market_type ?? '-'}</td><td>${row.selection ?? '-'}</td><td>${baseline}</td><td>${current}</td>
        <td>${dropPct == null ? '-' : Number(dropPct).toFixed(2) + '%'}</td><td>${formatDateUtc(row.kickoff_utc)}</td><td>${row.message}</td>
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
        <td>${formatDateUtc(row.created_at)}</td><td>${row.sport ?? '-'}</td><td>${row.alert_type}</td><td>${row.source ?? '-'}</td>
        <td>${row.market_type ?? '-'}</td><td>${row.selection ?? '-'}</td><td>${row.home_team} vs ${row.away_team}</td>
        <td>${formatDateUtc(row.kickoff_utc)}</td><td>${row.is_sent ? formatDateUtc(row.sent_at) : '-'}</td><td>${row.message}</td>
        <td>${formatCompactDetails(row.details ?? {})}</td>
      `;
      tbody.appendChild(tr);
    }
  }

  function exportOverlapCsv() { window.open('/admin/export/overlap.csv?limit=1000', '_blank'); }
  function exportAlertsCsv() { window.open('/admin/export/alerts.csv?limit=2000', '_blank'); }

  function chartColorForSeries(source, selection) {
    const bySource = { ps3838: { home: '#4ea1ff', draw: '#7eb9ff', away: '#b3d7ff' }, e_stave: { home: '#f6a75a', draw: '#f7c485', away: '#fde0b6' } };
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
    if (oddsHistoryChart) {
      oddsHistoryChart.destroy();
      oddsHistoryChart = null;
    }
    subtitle.textContent = `${payload.home_team} vs ${payload.away_team} | sport=${payload.sport} | kickoff=${payload.kickoff_utc ?? '-'}`;
    if (!payload.series || payload.series.length === 0) {
      empty.style.display = 'block';
      canvas.style.display = 'none';
      return;
    }
    empty.style.display = 'none';
    canvas.style.display = 'block';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    const datasets = payload.series.map((series) => ({
      label: series.label,
      data: series.points.map((point) => ({ x: point.scraped_at, y: Number(point.odds_decimal) })),
      borderColor: chartColorForSeries(series.source, series.selection),
      backgroundColor: chartColorForSeries(series.source, series.selection),
      borderWidth: 2,
      pointRadius: 0,
      tension: 0.2,
      spanGaps: true,
      borderDash: series.selection === 'draw' ? [6, 4] : [],
    }));
    oddsHistoryChart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { datasets },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { type: 'time', time: { tooltipFormat: 'yyyy-LL-dd HH:mm:ss' }, ticks: { color: '#c6d3e8' }, grid: { color: '#223450' } },
          y: { ticks: { color: '#c6d3e8' }, grid: { color: '#223450' } },
        },
        plugins: { legend: { labels: { color: '#dce8f8' } } },
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

  async function refresh() {
    const status = document.getElementById('run-status');
    status.textContent = 'Refreshing market tables...';
    const [overlap, overlapTrends, psRows, esRows, oddsDropAlerts, alerts] = await Promise.all([
      fetchJson('/matches/overlap?limit=200'),
      fetchJson('/matches/overlap-trends?limit=200&hours=72&max_points=18'),
      fetchJson('/matches/source/ps3838?limit=300'),
      fetchJson('/matches/source/e_stave?limit=300'),
      fetchJson('/alerts/odds-drops?limit=120'),
      fetchJson('/alerts/recent?limit=80'),
    ]);
    const trendByMatch = {};
    for (const trend of (overlapTrends.trends ?? [])) trendByMatch[trend.canonical_match_id] = trend;
    renderOverlapTable(overlap, trendByMatch);
    renderSourceTable('ps-table', psRows);
    renderSourceTable('es-table', esRows);
    renderOddsDropAlerts(oddsDropAlerts);
    renderAlerts(alerts);
    status.textContent = `Updated at ${new Date().toISOString().replace('T', ' ').replace('Z', '')}`;
  }

  document.getElementById('history-modal').addEventListener('click', (event) => {
    if (event.target.id === 'history-modal') closeHistoryModal();
  });

  refresh();
  setInterval(refresh, 30000);
</script>
</body>
</html>
"""
