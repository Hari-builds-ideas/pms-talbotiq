# Open questions & known rough edges

Product decisions and known-but-not-blocking rough edges that live in someone's head, not in code — so
they survive the handoff. None of these block the v1 demo. Each says the current behaviour, why, and the
follow-up if you want to change it.

## Product decisions made during v1 (change if you disagree)
- **Goals lead line wording.** The spec wanted "On track to hit 3 of 4 goals." A precise "X of Y on track"
  needs per-goal attainment thresholds threaded up to the person header, which isn't wired there today.
  v1 uses the honest, simpler lead: the person's overall status in words + goal count ("On track this
  cycle · 2 goals"). *Follow-up:* compute per-goal Ahead/On-track/Behind counts for the exact phrasing.
- **How far to demote the T-score.** Demoted on the per-person **headline** surfaces (Employee dashboard
  card, profile) — status leads, the number is a caption. The **Analytics** tables and the manager
  team-table keep the T-score as a *secondary* column (they already show the status badge next to it),
  because those are "insights" screens where an expert reader wants the number. *Follow-up:* demote it
  there too if non-expert managers find it noisy.
- **Which features to hide in v1.** Nine-box/calibration, succession, career roadmaps, and the raw-JSON
  tenant config are hidden (not deleted) — see `V1_VS_V2.md` for the exact re-enable steps. If a
  stakeholder wants any of these in the demo, it's a one-line change in `frontend/src/app/v1.ts`.
- **Raw-JSON tenant config is hidden, not redesigned.** v1 hides it rather than building a friendly
  labeled-toggle admin screen. *Follow-up for v2:* build the friendly version instead of exposing raw JSON.

## Known rough edges (documented, not blocking)
- **AI budget is a call-count cap, not a $/token cap.** Per-tenant `AgentBudget` + a global `LLM_MAX_CALLS`
  ceiling limit the *number* of calls, reserved atomically across replicas; there is no true dollar-based
  cap on token spend yet. Fine for a demo and for coarse cost control; add a token-cost cap before AI cost
  matters at scale. (`apps/billing/`.)
- **Budget fail-open on Redis-down.** If Redis is unavailable the budget reserve **fails open** (logs +
  allows, emits `pms_ai_budget_total{outcome="redis_down"}`) rather than 500-ing the user. This is a
  deliberate availability-over-strictness choice — *alert on that metric* in production.
- **Integrations (Slack/Jira) are scaffolded, not connected.** `apps/integrations/` has the seams but no
  live wiring. Don't demo them as working.
- **A stray root-level `npx vitest` reports 2 failures.** Running vitest from the **repo root** (wrong cwd)
  picks up a non-frontend config and shows 2 failures. The real frontend suite is green when run from
  `frontend/` (`cd frontend && npm test` → ~118 passing). *Follow-up:* remove/rename the stray root config
  so nobody is misled.
- **Free demo is not durable.** Ephemeral MySQL (reseeds on boot), the web service sleeps, Celery runs
  eagerly. All expected on the free tier — see `DEPLOYMENT.md`. Not a bug; don't rely on demo data persisting.

## Deferred to v2 (tracked elsewhere, noted here so nothing is lost)
- **Mobile** — real Expo app, backend-ready, needs the v1 simplification + brand pass + tests. See
  `MOBILE.md`.
- **The hidden enterprise features** — nine-box, succession, career, raw tenant config. See `V1_VS_V2.md`.
- **Production provisioning** — durable DB, real Celery worker, secrets manager, always-on + replicas,
  observability. See `DEPLOYMENT.md` Part 2. It's provisioning + config, not a rewrite.

## If you're unsure about anything
The invariants in `SYSTEM_OVERVIEW.md` ("must NOT break") are the hard lines — tenant isolation, server-
side RBAC, HITL, append-only audit, one LLM gateway, no fabrication. Everything else is a product choice
you're free to revisit. When a decision isn't covered by these docs, the build rule was: *make the
simplest choice a non-expert SME user would understand, and write it down* — keep doing that.
