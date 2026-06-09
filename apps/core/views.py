from django.http import JsonResponse
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
