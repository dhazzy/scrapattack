from celery import Celery

from odds_app.config import get_settings

settings = get_settings()

celery = Celery("odds_app", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "scrape-ps3838-every-minute": {
            "task": "odds_app.tasks.scrape_ps3838_soccer",
            "schedule": 60.0,
        },
        "scrape-estave-every-minute": {
            "task": "odds_app.tasks.scrape_estave_soccer",
            "schedule": 60.0,
        },
        "run-value-comparison-every-2-minutes": {
            "task": "odds_app.tasks.compare_value_edges",
            "schedule": 120.0,
        },
        "dispatch-alerts-every-30-seconds": {
            "task": "odds_app.tasks.dispatch_pending_alerts",
            "schedule": 30.0,
        },
    },
)

celery.autodiscover_tasks(["odds_app"])
