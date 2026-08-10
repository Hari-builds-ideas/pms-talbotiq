"""
Gunicorn configuration for the PMS web tier.

The web tier is stateless, so it scales horizontally as N identical replicas
behind nginx. Each replica runs this gunicorn config. Tune via env (sane
container defaults below).
"""
import os


def _int_env(name, default):
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


# PaaS platforms (Railway, Heroku, Cloud Run) inject the port to listen on as
# PORT and route to it; a process bound to a fixed 8000 there is never reached
# and fails its health check. `or` rather than a get() default so a defined-but-
# empty PORT falls back too, instead of binding the invalid "0.0.0.0:".
bind = f"0.0.0.0:{os.environ.get('PORT') or '8000'}"

# A FIXED small default — never (2 × cores) + 1.
#
# cpu_count() reports the HOST's cores, not the container's share. On a Railway
# box that is ~24, so the old formula forked 49 gunicorn workers, each a full
# Django process; the container hit its memory limit, got SIGKILLed before it
# could bind, and the health check never passed. Scale this deliberately with
# WEB_CONCURRENCY (the name Railway/Heroku already use) once the real per-worker
# footprint is known — and keep it inside the DB max_connections budget:
# replicas × workers × threads + celery concurrency (see config/settings/base.py).
workers = _int_env("WEB_CONCURRENCY", 2)
# >1 thread switches gunicorn to the gthread worker, letting a worker overlap
# IO-bound requests — cheap concurrency that costs memory the way a worker does not.
threads = _int_env("GUNICORN_THREADS", 4)

# Gunicorn heartbeats through a file in worker_tmp_dir. On a container runtime
# /tmp is often disk-backed (and can be slow or read-only), which makes the
# arbiter kill healthy workers; /dev/shm is tmpfs and is the standard fix.
worker_tmp_dir = "/dev/shm"

# Kill+replace a worker stuck longer than this (seconds). 120 leaves room for the
# slow LLM-backed requests to finish rather than being recycled mid-call.
timeout = _int_env("GUNICORN_TIMEOUT", 120)
graceful_timeout = _int_env("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = _int_env("GUNICORN_KEEPALIVE", 5)

# Recycle workers periodically to bound any slow memory growth; jitter staggers
# recycling across workers so they don't all restart at once.
max_requests = _int_env("GUNICORN_MAX_REQUESTS", 1000)
max_requests_jitter = _int_env("GUNICORN_MAX_REQUESTS_JITTER", 100)

# Structured logging to stdout/stderr (collected by the container runtime).
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")
