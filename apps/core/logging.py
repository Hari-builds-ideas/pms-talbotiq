"""
RequestContextFilter — enrich every log record with request context.

A ``logging.Filter`` that stamps the current request id and tenant id onto each
``LogRecord``. The orchestrator attaches this filter to the console handler and
adds ``%(request_id)s %(tenant_id)s`` to the JsonFormatter format, so every
emitted log line carries correlation + tenant attribution. Both default to
``"-"`` when nothing is bound (e.g. logs from outside a request, like startup
or Celery bootstrap), which keeps the JSON shape stable.
"""
import logging

from .request_context import get_request_id


class RequestContextFilter(logging.Filter):
    def filter(self, record):
        # Imported lazily to avoid an import cycle at module load: tenancy
        # imports may pull in app machinery before logging is fully configured.
        from apps.tenancy.context import get_current_tenant_id

        record.request_id = get_request_id() or "-"
        record.tenant_id = get_current_tenant_id() or "-"
        return True
