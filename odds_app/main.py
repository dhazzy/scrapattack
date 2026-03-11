import time

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from odds_app.config import get_settings
from odds_app.db import Base, engine, get_db, ping_db
from odds_app.models import Alert, OddsSnapshot
from odds_app.schemas import (
    AlertResponse,
    HealthResponse,
    MatchSummaryResponse,
    OddsSnapshotResponse,
    OverlapMatchRow,
    PS3838DiagnosticsOverrides,
    RunOnceResponse,
    SourceMatchRow,
)
from odds_app.services.diagnostics import run_ps3838_diagnostics_sync
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


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Odds Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; background: #f7f7f7; }
    h1 { margin-bottom: 6px; }
    h2 { margin-top: 30px; }
    .meta { color: #555; margin-bottom: 10px; }
    button { padding: 8px 12px; margin-right: 10px; }
    table { border-collapse: collapse; width: 100%; background: white; margin-bottom: 24px; }
    th, td { border: 1px solid #ddd; padding: 8px; font-size: 12px; vertical-align: top; }
    th { background: #111; color: white; text-align: left; }
    .small { color: #666; font-size: 12px; }
    .box { margin-bottom: 18px; }
    .positive { color: #0a7a0a; font-weight: bold; }
    .negative { color: #b20000; font-weight: bold; }
  </style>
</head>
<body>
  <h1>Sports Odds Dashboard</h1>
  <div class="meta">Football/Soccer, Tennis, Basketball | Home/Draw/Away odds | PS3838 + e-stave + overlap.</div>
  <div class="box">
    <button onclick="forceRefresh()">Force refresh now</button>
    <span id="run-status" class="small"></span>
  </div>

  <h2>Matches on both sources (comparison)</h2>
  <table id="overlap-table">
    <thead>
      <tr>
        <th>Sport</th>
        <th>Match ID</th>
        <th>Match</th>
        <th>PS H</th>
        <th>PS D</th>
        <th>PS A</th>
        <th>ES H</th>
        <th>ES D</th>
        <th>ES A</th>
        <th>Edge H % (ES vs PS)</th>
        <th>Better (H)</th>
        <th>Kickoff (UTC)</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>

  <h2>PS3838 matches</h2>
  <table id="ps-table">
    <thead>
      <tr>
        <th>Sport</th>
        <th>Match ID</th>
        <th>External ID</th>
        <th>Match</th>
        <th>League</th>
        <th>Home</th>
        <th>Draw</th>
        <th>Away</th>
        <th>Kickoff (UTC)</th>
        <th>Last Scraped</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>

  <h2>e-stave matches</h2>
  <table id="es-table">
    <thead>
      <tr>
        <th>Sport</th>
        <th>Match ID</th>
        <th>External ID</th>
        <th>Match</th>
        <th>League</th>
        <th>Home</th>
        <th>Draw</th>
        <th>Away</th>
        <th>Kickoff (UTC)</th>
        <th>Last Scraped</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>

  <h2>Recent alerts</h2>
  <table id="alerts-table">
    <thead>
      <tr>
        <th>Time</th>
        <th>Type</th>
        <th>Match</th>
        <th>Message</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>

  <script>
    async function fetchJson(url, options = {}) {
      const res = await fetch(url, options);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${url}`);
      return await res.json();
    }

    function renderSourceTable(tableId, rows) {
      const tbody = document.querySelector(`#${tableId} tbody`);
      tbody.innerHTML = "";
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${row.sport ?? "-"}</td>
          <td>${row.canonical_match_id}</td>
          <td>${row.external_event_id}</td>
          <td>${row.home_team} vs ${row.away_team}</td>
          <td>${row.league ?? "-"}</td>
          <td>${row.latest_home_odds ?? "-"}</td>
          <td>${row.latest_draw_odds ?? "-"}</td>
          <td>${row.latest_away_odds ?? "-"}</td>
          <td>${row.kickoff_utc ?? "-"}</td>
          <td>${row.last_scraped_at ?? "-"}</td>
        `;
        tbody.appendChild(tr);
      }
    }

    function renderOverlapTable(rows) {
      const tbody = document.querySelector("#overlap-table tbody");
      tbody.innerHTML = "";
      for (const row of rows) {
        const edge = row.edge_pct_estave_vs_ps3838_home;
        const edgeClass = edge == null ? "" : (edge >= 0 ? "positive" : "negative");
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${row.sport ?? "-"}</td>
          <td>${row.canonical_match_id}</td>
          <td>${row.home_team} vs ${row.away_team}</td>
          <td>${row.ps3838_home_odds ?? "-"}</td>
          <td>${row.ps3838_draw_odds ?? "-"}</td>
          <td>${row.ps3838_away_odds ?? "-"}</td>
          <td>${row.estave_home_odds ?? "-"}</td>
          <td>${row.estave_draw_odds ?? "-"}</td>
          <td>${row.estave_away_odds ?? "-"}</td>
          <td class="${edgeClass}">${edge == null ? "-" : edge.toFixed(2) + "%"}</td>
          <td>${row.better_source_home ?? "-"}</td>
          <td>${row.kickoff_utc ?? "-"}</td>
        `;
        tbody.appendChild(tr);
      }
    }

    function renderAlerts(rows) {
      const tbody = document.querySelector("#alerts-table tbody");
      tbody.innerHTML = "";
      for (const row of rows) {
        const tr = document.createElement("tr");
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
      const [overlap, psRows, esRows, alerts] = await Promise.all([
        fetchJson("/matches/overlap?limit=200"),
        fetchJson("/matches/source/ps3838?limit=300"),
        fetchJson("/matches/source/e_stave?limit=300"),
        fetchJson("/alerts/recent?limit=80"),
      ]);
      renderOverlapTable(overlap);
      renderSourceTable("ps-table", psRows);
      renderSourceTable("es-table", esRows);
      renderAlerts(alerts);
    }

    async function forceRefresh() {
      const status = document.getElementById("run-status");
      status.textContent = "Refreshing sources...";
      try {
        const out = await fetchJson("/admin/force-refresh", { method: "POST" });
        status.textContent = `Done: ps=${out.ps3838_quotes}, es=${out.estave_quotes}, alerts=${out.total_alerts_created}`;
        await refresh();
      } catch (err) {
        status.textContent = `Force refresh failed: ${err}`;
      }
    }

    refresh();
    setInterval(refresh, 30000);
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
    if source not in {"ps3838", "e_stave"}:
        raise HTTPException(status_code=400, detail="source must be ps3838 or e_stave")
    return list_source_matches(db, source=source, limit=limit)


@app.get("/matches/overlap", response_model=list[OverlapMatchRow])
def overlap_matches(limit: int = 100, db: Session = Depends(get_db)) -> list[OverlapMatchRow]:
    return list_overlap_matches(db, limit=limit)


@app.post("/admin/force-refresh", response_model=RunOnceResponse)
def admin_force_refresh(db: Session = Depends(get_db)) -> dict:
    return run_pipeline_once(db, simulate_drop=False)


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
