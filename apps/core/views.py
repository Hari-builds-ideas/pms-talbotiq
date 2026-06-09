from django.http import JsonResponse


def healthz(request):
    """Liveness probe. Intentionally dependency-free: returns 200 as long as
    the WSGI app can serve a request. Readiness (DB/cache) checks belong to a
    separate probe so a transient datastore blip doesn't kill the pod."""
    return JsonResponse({"status": "ok", "service": "pms"})
