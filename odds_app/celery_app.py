from celery import Celery

from odds_app.config import get_settings

settings = get_settings()

celery = Celery("odds_app", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "scrape-ps3838-every-5-min": {
            "task": "odds_app.tasks.scrape_ps3838_soccer",
            "schedule": float(settings.scrape_interval_sec),
        },
        "scrape-estave-every-5-min": {
            "task": "odds_app.tasks.scrape_estave_soccer",
            "schedule": float(settings.scrape_interval_sec),
        },
        "run-reconciliation-and-comparison-every-5-min": {
            "task": "odds_app.tasks.reconcile_and_compare_matches",
            "schedule": float(settings.compare_interval_sec),
        },
        "dispatch-alerts": {
            "task": "odds_app.tasks.dispatch_pending_alerts",
            "schedule": float(settings.alert_dispatch_interval_sec),
        },
    },
)

celery.autodiscover_tasks(["odds_app"])
