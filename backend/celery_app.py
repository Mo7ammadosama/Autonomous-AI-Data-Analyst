"""
Celery application — async task queue for heavy background processing.

Queues:
  default   — general tasks
  pipeline  — dataset analysis pipeline (CPU-heavy)
  alerts    — alert evaluation (I/O-bound, frequent)

Usage (from FastAPI):
  from celery_app import celery_app
  celery_app.send_task("tasks.run_pipeline", args=[dataset_id])
"""

import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "datamind",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task routing
    task_routes={
        "tasks.run_pipeline_task": {"queue": "pipeline"},
        "tasks.run_autonomous_task": {"queue": "pipeline"},
        "tasks.evaluate_alerts_task": {"queue": "alerts"},
        "tasks.send_scheduled_report_task": {"queue": "alerts"},
        "tasks.proactive_scan_all": {"queue": "alerts"},
        "tasks.proactive_scan_user": {"queue": "alerts"},
        "tasks.send_digest_all": {"queue": "alerts"},
    },

    # Retry policy
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_max_retries=3,

    # Result expiry (24 hours)
    result_expires=86400,

    # Beat schedule — periodic tasks
    beat_schedule={
        # Evaluate all active alerts every 15 minutes
        "evaluate-all-alerts": {
            "task": "tasks.evaluate_all_active_alerts",
            "schedule": crontab(minute="*/15"),
        },
        # Send scheduled reports daily at 08:00 UTC
        "send-scheduled-reports": {
            "task": "tasks.send_scheduled_reports",
            "schedule": crontab(hour=8, minute=0),
        },
        # Phase 9: Proactive Intelligence — scan every 30 minutes
        "proactive-intelligence-scan": {
            "task": "tasks.proactive_scan_all",
            "schedule": crontab(minute="*/30"),
        },
        # Phase 14: Personalized Digest — daily at 08:00 UTC
        "send-digest-daily": {
            "task": "tasks.send_digest_all",
            "schedule": crontab(hour=8, minute=5),
        },
    },
)
