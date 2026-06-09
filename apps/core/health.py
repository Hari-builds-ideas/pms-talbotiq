"""Custom django-health-check backends for the PMS core app.

These plugins are registered in ``CoreConfig.ready()`` and run as part of the
``/readyz`` readiness probe (see ``apps.core.views.ReadyzView``).
"""

from health_check.backends import BaseHealthCheckBackend
from health_check.exceptions import ServiceUnavailable

from config.celery import app as celery_app


class CeleryBrokerHealthCheck(BaseHealthCheckBackend):
    """Check that the Celery *broker* is reachable.

    This deliberately probes broker connectivity rather than pinging a live
    worker: a web replica should be considered ready as long as it can enqueue
    work, even when no worker process happens to be running.
    """

    critical_service = True

    def check_status(self):
        """Open a short-lived broker connection and tear it down again."""
        try:
            conn = celery_app.connection()
            conn.ensure_connection(max_retries=1, timeout=3)
            conn.release()
        except Exception as exc:  # noqa: BLE001 - surface any broker failure
            raise ServiceUnavailable(f"Celery broker unreachable: {exc}")

    def identifier(self):
        """Stable, human-readable key used in the ``/readyz`` JSON body."""
        return "CeleryBroker"
