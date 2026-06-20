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
