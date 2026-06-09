"""
Gunicorn configuration for the PMS web tier.

The web tier is stateless, so it scales horizontally as N identical replicas
behind nginx. Each replica runs this gunicorn config. Tune via env (sane
container defaults below).
"""
import multiprocessing
import os


def _int_env(name, default):
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")

# (2 × cores) + 1 is the classic gunicorn sizing for mixed CPU/IO workloads.
workers = _int_env("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1)
# >1 thread switches gunicorn to the gthread worker, letting a worker overlap
# IO-bound requests. Factor threads into DB max_connections sizing (see settings).
threads = _int_env("GUNICORN_THREADS", 2)

# Kill+replace a worker stuck longer than this (seconds).
timeout = _int_env("GUNICORN_TIMEOUT", 60)
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
