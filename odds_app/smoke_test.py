import argparse
import json

from sqlalchemy import delete, func, select

from odds_app.db import Base, SessionLocal, engine
from odds_app.models import Alert, OddsSnapshot
from odds_app.services.orchestrator import run_pipeline_once


def _reset_tables() -> None:
    with SessionLocal() as db:
        db.execute(delete(Alert))
        db.execute(delete(OddsSnapshot))
        db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run end-to-end local smoke test.")
    parser.add_argument("--reset", action="store_true", help="Delete alerts/snapshots before running")
    parser.add_argument(
        "--simulate-drop",
        action="store_true",
        help="Inject a second synthetic pass to trigger odds-drop alerts",
    )
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    if args.reset:
        _reset_tables()

    with SessionLocal() as db:
        result = run_pipeline_once(db, simulate_drop=args.simulate_drop)
        snapshot_count = db.scalar(select(func.count()).select_from(OddsSnapshot)) or 0
        alert_count = db.scalar(select(func.count()).select_from(Alert)) or 0

    summary = {
        **result,
        "snapshot_count": int(snapshot_count),
        "alert_count": int(alert_count),
    }
    print(json.dumps(summary, indent=2))

    if summary["snapshot_count"] <= 0:
        raise SystemExit("Smoke test failed: no snapshots were inserted.")
    if summary["total_alerts_created"] <= 0:
        raise SystemExit("Smoke test failed: no alerts were created.")


if __name__ == "__main__":
    main()
