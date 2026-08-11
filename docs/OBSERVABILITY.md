# OBSERVABILITY — Talbotiq PMS (BUILD_4)

Health probes, the `/metrics` exporter, structured logs, and Sentry — plus the
SLIs to watch and suggested alert thresholds, so when a monitoring stack is added
the thresholds are already reasoned.

## Probes

| Probe | Purpose | Behaviour |
|---|---|---|
| `GET /healthz` | liveness | dependency-free, always 200 if the WSGI app serves. Never gate liveness on a datastore blip. |
| `GET /readyz` | readiness | runs every health-check backend; 200 only if all pass, else 503 with per-check `up`/`down`. An LB/orchestrator drains on 503. |

`/readyz` checks: `DatabaseBackend` (primary), **`DatabaseReplica`** (the BUILD_3
read-replica alias), `Cache backend: default` + `: sessions`, `RedisHealthCheck`,
`CeleryBroker` (broker reachable — not a live worker), `MigrationsHealthCheck`.
Body carries `up`/`down` only — no secrets or stack traces.

## `/metrics` (Prometheus text, token-gated)

`GET /metrics` with `Authorization: Bearer <METRICS_TOKEN>` (or `?token=`).
**Fail-closed**: with `METRICS_TOKEN` unset the endpoint is `404` (disabled); set
it to a long random value the scraper presents. System-level aggregates only —
**no per-tenant labels** (no cross-tenant detail leaks).

| Metric | Type | Meaning |
|---|---|---|
| `pms_requests_total{route,status}` | counter | HTTP requests by coarse route class + status class (2xx/4xx/5xx). Cache-backed → aggregates across gunicorn workers/replicas. |
| `pms_celery_queue_depth` | gauge | tasks waiting in the default Celery queue (broker LLEN). |
| `pms_aijob_total{status}` | gauge | async AI jobs by status across all tenants (QUEUED/RUNNING/SUCCEEDED/DEGRADED/FAILED). |
| `pms_token_usage_total{agent}` | counter | LLM tokens metered per agent across all tenants (the TokenLedger total). |
| `pms_tenants_total` | gauge | tenant count. |

Live sample (dev): `pms_requests_total{route="readyz",status="2xx"}`,
`pms_celery_queue_depth 0`, `pms_aijob_total{status="SUCCEEDED"}`,
`pms_token_usage_total{agent="agent1"}`, `pms_tenants_total 22`.

## SLIs & suggested alert thresholds

| SLI | Source | Suggested alert |
|---|---|---|
| Error rate | `pms_requests_total` 5xx ÷ total | > 1% over 5m → page; > 5% → critical |
| Latency | LB/proxy p95 (add request histograms when a monitoring stack lands) | p95 > 1s over 10m → warn |
| Celery backlog | `pms_celery_queue_depth` | > 100 sustained 10m → warn (AI jobs delayed) |
| AI degraded/failed | `pms_aijob_total{status="DEGRADED"\|"FAILED"}` rising | FAILED rate > 0 sustained → investigate provider |
| AI quota | `pms_token_usage_total` vs the per-tenant budget / Groq tier | approaching tier limit → warn |
| DB connections | MySQL `Threads_connected` vs `max_connections` | > 80% → warn (scale DB or reduce replicas — see RUNBOOK sizing) |
| Readiness | `/readyz` 503 rate | any sustained 503 → the failing check names the dependency |

(Request-latency histograms and live DB-connection gauges are intentionally left
to the monitoring stack / a future `prometheus_client` multiprocess setup — the
exporter here stays dependency-free.)

## Structured logging & Sentry

Every log line carries the `request_id` (and `tenant_id` when bound) via
`RequestIDMiddleware` + the logging filter — JSON to stdout, correlatable across
hops. Sentry is opt-in (no-op without `SENTRY_DSN`) and wires BOTH the Django and
**Celery** integrations, so async task failures (the BUILD_2 AI jobs) are
captured too; `before_send` scrubs Authorization/JWT/passwords and tags events
with tenant + request id.

## Reading the logs

Everything goes to stdout, so the container runtime is the log store — there is no
file to rotate and nothing to configure.

```bash
docker compose logs -f web                  # follow the API
docker compose logs -f celery-worker        # async AI jobs land here, not in web
docker compose logs --since 15m web         # the last quarter hour
docker compose logs --tail 200 web caddy    # several services, interleaved
```

Application lines carry a `[req=<request_id> tenant=<tenant_id>]` prefix (`-` when
unbound, e.g. before authentication):

```
2026-08-11 18:39:57,557 WARNING django.request [req=- tenant=-] Unauthorized: /metrics
```

**Following one request across services.** The request id is the join key — grab it
from a Sentry event or a response, then:

```bash
docker compose logs web celery-worker | grep 'req=8f3c1a2b'
```

That is the point of the correlation id: a chat turn that fails inside a Celery task
shares an id with the HTTP request that started it, so one grep spans both.

**Under prod settings the format is JSON**, which is what you want in a log platform
(Loki/CloudWatch/Datadog) and awkward by eye — pipe it through `jq`:

```bash
docker compose logs --no-log-prefix web | jq -r 'select(.levelname=="ERROR") | "\(.asctime) \(.name) \(.message)"'
```

**Triage order for "the app is down":**

1. `curl -s https://<domain>/readyz | jq` — names the failing dependency (database,
   replica, cache, sessions, Celery broker, migrations) instead of leaving you guessing.
   `/healthz` only proves the process is alive.
2. `docker compose ps` — is anything restarting?
3. `docker compose logs --since 10m web` — the first ERROR is usually the real one; the
   rest are consequences.
4. `docker compose logs caddy` — a 502 with a healthy `web` is a routing or
   certificate problem, not an application one.

**Retention.** Docker's local driver keeps logs until the container is removed, so a
redeploy loses them. Ship to a platform (or set a logging driver) before you need to
investigate something that happened last week.
