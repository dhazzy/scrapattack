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
        "scrape-ps3838-backfill-near": {
            "task": "odds_app.tasks.scrape_ps3838_backfill_near",
            "schedule": float(settings.scrape_backfill_near_interval_sec),
        },
        "scrape-ps3838-backfill-far": {
            "task": "odds_app.tasks.scrape_ps3838_backfill_far",
            "schedule": float(settings.scrape_backfill_far_interval_sec),
        },
        "scrape-estave-backfill-near": {
            "task": "odds_app.tasks.scrape_estave_backfill_near",
            "schedule": float(settings.scrape_backfill_near_interval_sec),
        },
        "scrape-estave-backfill-far": {
            "task": "odds_app.tasks.scrape_estave_backfill_far",
            "schedule": float(settings.scrape_backfill_far_interval_sec),
        },
        "dispatch-alerts": {
            "task": "odds_app.tasks.dispatch_pending_alerts",
            "schedule": float(settings.alert_dispatch_interval_sec),
        },
        "cleanup-old-data": {
            "task": "odds_app.tasks.cleanup_old_data",
            "schedule": float(settings.retention_cleanup_interval_sec),
        },
        "run-scrape-canary-checks": {
            "task": "odds_app.tasks.run_scrape_canary_checks",
            "schedule": float(settings.canary_interval_sec),
        },
    },
)

celery.autodiscover_tasks(["odds_app"])
