import os

from celery import Celery
from celery.signals import task_postrun, task_prerun

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

# Redis is the broker AND the result backend for MVP (no Kafka). Concrete URLs
# come from CELERY_* settings (namespace="CELERY") which read REDIS_URL-style env.
app = Celery("pms")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@task_prerun.connect
def _reset_db_routing(**kwargs):
    """Clear the read-after-write DB-routing flag at the start of each task — a
    worker thread is long-lived and reused, so one task's write must not pin the
    next task's reads to the primary (BUILD_3)."""
    from apps.core.dbrouter import reset_write_state

    reset_write_state()


@task_postrun.connect
def _close_old_connections(**kwargs):
    """Close stale DB connections after each task so long-lived workers don't leak
    or reuse a dropped connection (CONN_MAX_AGE applies per worker; standard Celery
    hygiene). SKIP in eager mode: there the task runs INSIDE the caller's (test)
    transaction, so closing the connection would tear down that transaction."""
    from django.conf import settings

    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        return
    from django.db import close_old_connections

    close_old_connections()


@app.task(bind=True, ignore_result=True)
def debug_task(self):  # pragma: no cover - operational smoke task
    print(f"Request: {self.request!r}")
