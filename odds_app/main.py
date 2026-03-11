import time

from fastapi import Body, Depends, FastAPI
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
    RunOnceResponse,
    PS3838DiagnosticsOverrides,
)
from odds_app.services.match_views import list_recent_matches
from odds_app.services.diagnostics import run_ps3838_diagnostics_sync
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
        except Exception as exc:  # pragma: no cover - startup resilience path
            last_error = exc
            time.sleep(settings.db_startup_retry_delay_sec)
    if last_error is not None:
        raise last_error


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Soccer Odds Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; background: #f7f7f7; }
    h1 { margin-bottom: 6px; }
    .meta { color: #555; margin-bottom: 18px; }
    button { padding: 8px 12px; margin-right: 10px; }
    table { border-collapse: collapse; width: 100%; background: white; margin-bottom: 24px; }
    th, td { border: 1px solid #ddd; padding: 8px; font-size: 13px; vertical-align: top; }
    th { background: #111; color: white; text-align: left; }
    .small { color: #666; font-size: 12px; }
    .box { margin-bottom: 18px; }
    code { background: #efefef; padding: 1px 4px; border-radius: 4px; }
  </style>
</head>
<body>
  <h1>Soccer Odds Dashboard</h1>
  <div class="meta">Live view of canonical matches (shared IDs) and recent alerts.</div>
  <div class="box">
    <button onclick="runOnce(false)">Run once</button>
    <button onclick="runOnce(true)">Run once + simulate drop</button>
    <span id="run-status" class="small"></span>
  </div>

  <h2>Matches</h2>
  <table id="matches-table">
    <thead>
      <tr>
        <th>Match ID</th>
        <th>Match</th>
        <th>Kickoff Bucket (UTC)</th>
        <th>Source Events</th>
        <th>Updated</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>

  <h2>Recent Alerts</h2>
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

    function renderMatches(rows) {
      const tbody = document.querySelector("#matches-table tbody");
      tbody.innerHTML = "";
      for (const row of rows) {
        const eventLines = row.source_events.map(ev =>
          `<div><code>${ev.source}</code> id=${ev.external_event_id} home_odds=${ev.latest_home_odds ?? "-"} <span class="small">${ev.last_scraped_at ?? ""}</span></div>`
        ).join("");
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${row.match_id}</td>
          <td>${row.home_team} vs ${row.away_team}</td>
          <td>${row.kickoff_bucket_utc ?? "unknown"}</td>
          <td>${eventLines || "-"}</td>
          <td>${row.updated_at}</td>`;
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
          <td>${row.message}</td>`;
        tbody.appendChild(tr);
      }
    }

    async function refresh() {
      const [matches, alerts] = await Promise.all([
        fetchJson("/matches/recent?limit=80"),
        fetchJson("/alerts/recent?limit=80")
      ]);
      renderMatches(matches);
      renderAlerts(alerts);
    }

    async function runOnce(simulate) {
      const status = document.getElementById("run-status");
      status.textContent = "Running...";
      try {
        const out = await fetchJson(`/admin/run-once?simulate_drop=${simulate}`, { method: "POST" });
        status.textContent = `Done: quotes ps=${out.ps3838_quotes}, es=${out.estave_quotes}, alerts=${out.total_alerts_created}`;
        await refresh();
      } catch (err) {
        status.textContent = `Run failed: ${err}`;
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
