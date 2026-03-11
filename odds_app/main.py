import time

from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from odds_app.config import get_settings
from odds_app.db import Base, engine, get_db, ping_db
from odds_app.models import Alert, OddsSnapshot
from odds_app.schemas import AlertResponse, HealthResponse, OddsSnapshotResponse

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
