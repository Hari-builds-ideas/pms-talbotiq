# PROD_READINESS_STATUS — grounded snapshot (OVERNIGHT_E5)

The doc to hand whoever owns procurement/infra. Each item from
`docs/SYSTEM_DESIGN_AND_READINESS.md §9` marked **DONE / IN PROGRESS / OPEN**, with a code reference.
Nothing is claimed complete without one. Status today: **pilot-ready, not real-load-ready.**

## Must-have before ANY real users

| Item | Status | Grounding / next step |
|---|---|---|
| Secrets → a vault (LLM key, tokens, `SECRET_KEY`); rotate demo key | **OPEN** | keys are env-provided today (`OPENAI_API_KEY` in `.env`); needs a real vault + rotation — infra |
| Managed MySQL + automated backups + tested restore | **OPEN** | infra procurement; app is DB-agnostic (MySQL 8) |
| Bake the prod image (drop the `.:/app` dev mount); run `config.settings.prod` | **OPEN** | `config/settings/prod.py` exists; the compose dev mount is still used — build task |
| TLS + load balancer in front of web | **OPEN** | `prod.py` already assumes a TLS-terminating proxy — infra |
| Controlled migration step (not `migrate` on every worker boot) | **OPEN (E2 not attempted this run)** | needs a one-shot deploy job / mgmt command; flagged for a careful pass |
| Separate Redis for cache vs broker | **OPEN** | env-only split (broker `noeviction`, cache `allkeys-lru`) — infra |
| `select_related` on paginated list views (N+1) | **DONE (guarded)** | list views use `select_related`/`prefetch_related`; regression-guarded by the **`[query-budget] … [BOUNDED]` tests** (goals, org-positions, jd-library, career-roadmaps, succession-bench, feedback-cycles show Δ=0 across 5→25 rows). E1's audit is effectively already enforced by these tests. |
| Pick & wire a real LLM provider | **IN PROGRESS** | `OpenAIProvider` is wired and LIVE-verified this run (agentic planner ran on `gpt-4o-mini`); confirm budgets/tier before opening to users — see `NEEDS_HARI_llm_provider.md` |

## Before scale (load)

| Item | Status | Grounding / next step |
|---|---|---|
| Move AI off the request thread (Celery + poll) | **DONE** | the async AI seams enqueue `AIJob` (BUILD_2) + Celery; chat/planner are the only sync LLM routes (AI-throttled) |
| Atomic budget/throttle across replicas (Redis Lua) | **OPEN (E3 not attempted this run)** | per-tenant budgets exist (`check_and_reserve_budget`) but aren't multi-replica-atomic yet; flagged for a careful pass |
| Paid LLM tier + per-tenant budget sizing | **IN PROGRESS** | budgets enforced by the gateway (`AgentBudget`); tier/limits are a spend decision |
| Read replica + DB router | **OPEN** | infra + a router; no code today |
| Metrics + dashboards + alerting + uptime | **OPEN** | biggest ops gap; no code today |
| Autoscale Celery workers; size the broker | **OPEN** | infra |

## Verified green this run

- Backend suite **1375 passed** (incl. the new agentic-chat V2 + safety matrix + seed_demo_rich tests).
- N+1 query-budget tests **BOUNDED** (no regressions).
- `seed_demo_rich` proven **idempotent + weight-correct + ACME-only + no-live-AI** (`apps/core/tests/test_seed_demo_rich.py`).
- LLM provider **live-verified** (planner ran on `gpt-4o-mini`; ~8 calls total this run).

## Not attempted this overnight run (need a careful, dedicated pass)

- **E2 controlled migration command** — extracting migrations into a one-shot deploy job. Risk: touches
  boot/deploy behavior; wants its own review + idempotency tests.
- **E3 atomic Redis-Lua budget counters** — replacing the current budget reserve with a Lua script for
  multi-replica correctness + a 100-concurrent test. Risk: touches the metering hot path.

Both are backend-only and testable; deferred here only to protect "never push red" under the run's
time cap, not because they're blocked.
