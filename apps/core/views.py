from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.crypto import constant_time_compare
from django.views import View
from health_check.mixins import CheckMixin


def healthz(request):
    """Liveness probe. Intentionally dependency-free: returns 200 as long as
    the WSGI app can serve a request. Readiness (DB/cache) checks belong to a
    separate probe so a transient datastore blip doesn't kill the pod."""
    return JsonResponse({"status": "ok", "service": "pms"})


class ReadyzView(CheckMixin, View):
    """Readiness probe. Runs every registered django-health-check backend and
    reports 200 only when all of them pass, otherwise 503.

    The body is intentionally minimal — per-check ``up``/``down`` only, with no
    secrets, error messages, or stack traces — so it is safe to expose to a load
    balancer or orchestrator.
    """

    def get(self, request, *args, **kwargs):
        # Accessing ``errors`` runs every registered check against the same
        # cached ``self.plugins`` instances, populating each plugin's ``.errors``.
        # ``self.plugins`` is an OrderedDict {identifier: plugin_instance}.
        errors = self.errors
        payload = {
            "status": "ready" if not errors else "not ready",
            "checks": {
                identifier: ("up" if not plugin.errors else "down")
                for identifier, plugin in self.plugins.items()
            },
        }
        return JsonResponse(payload, status=200 if not errors else 503)


class MetricsView(View):
    """Prometheus-text metrics (BUILD_4 4.2). Token-gated + fail-closed: with no
    ``METRICS_TOKEN`` configured the endpoint is hidden (404); otherwise a caller
    must present it as ``Authorization: Bearer <token>`` or ``?token=``. Returns
    the exposition rendered by :mod:`apps.core.metrics` (system-level aggregates;
    no per-tenant detail)."""

    def get(self, request, *args, **kwargs):
        token = getattr(settings, "METRICS_TOKEN", "") or ""
        if not token:
            return HttpResponse(status=404)  # disabled until a token is configured
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        provided = auth[7:].strip() if auth.startswith("Bearer ") else request.GET.get("token", "")
        if not constant_time_compare(provided, token):
            return HttpResponse(status=401)
        from apps.core.metrics import render

        return HttpResponse(render(), content_type="text/plain; version=0.0.4; charset=utf-8")
