import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

# Redis is the broker AND the result backend for MVP (no Kafka). Concrete URLs
# come from CELERY_* settings (namespace="CELERY") which read REDIS_URL-style env.
app = Celery("pms")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):  # pragma: no cover - operational smoke task
    print(f"Request: {self.request!r}")
