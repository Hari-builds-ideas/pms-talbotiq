# V1_REVIEW — run progress (FINAL.md, production-handover scope)

Run started 2026-07-13, branch `hari/agent-ui-v2`, base commit `1f77c8e`. Scope change vs FINAL.md as
written: **section F is PRODUCTION-grade** (env verified against `config/settings/prod.py`, missing prod
vars added, email/SMTP wired if absent, DEPLOYMENT_HANDOVER.md for a real production setup).

Execution order (per FINAL.md): A1 → D → E → B → C → A2 → F → G → H.

## Status — ALL SECTIONS COMPLETE (2026-07-13)
- [x] **A1** — PROJECT_ASSESSMENT.md (17 modules classified; P0s all fixed this run)
- [x] **D1/D2** — RBAC_MATRIX.md + AUTHZ_UI_ISSUES.md + fix `51eaeeb` (/me capabilities → `can()`;
  Reviews ActionBar gated; pickers scoped via useScopedPeople)
- [x] **E1/E2** — resizable + side-by-side persistent copilot `d7e20bb` (AGENT_CHAT_UX.md)
- [x] **B1/B2** — AUTH_REVIEW.md + fixes `fee090a` (logout revokes; real-MFA contract; cookie pinning)
- [x] **C1/C2** — AGENT_MEMORY_REVIEW.md + fix `2e20745` (read-path memory: context classification,
  deixis + name resolution, refs grounding, count routing, reload-resume; live-verified on Gemini)
- [x] **A2** — QA_CHECKLIST.md (57/57 smoke + 9/9 live probes on the recreated+reseeded stack)
- [x] **F1/F2** — email/SMTP + password reset WIRED `aad7676`; production `.env.example` (+ new
  `DB_SSL_CA` TLS option) + DEPLOYMENT_HANDOVER.md `01418a0`
- [x] **G1/G2** — BRANDING_LOCATIONS.md + FRONTEND_REDESIGN_PLAN.md
- [x] **H** — FINAL_REPORT.md (fixes/commits, remains, human checklist, green confirmation)

**Next (per the extended goal): PHASE2_BUILD.md — LANE 1 build, LANE 2 design-only.**

## Log
- Setup: `docs/V1_REVIEW/` created; stack healthy (:8090 → 200); tree clean at `1f77c8e`.
  4 parallel read-only investigations launched (RBAC matrix+authz-UI audit, auth review, agent
  memory + chat panel architecture, module assessment).
- Prep findings (verified directly, ahead of the agent reports):
  - `config/settings/prod.py` is fail-closed (SECRET_KEY + ALLOWED_HOSTS required, DEBUG hard False,
    HSTS/secure cookies on). Full env-var inventory extracted (61 vars incl. `METRICS_TOKEN`,
    `SENTRY_*`, `DB_REPLICA_*` — already in code).
  - **Email/SMTP is NOT wired**: no `EMAIL_*` settings anywhere; allauth `ACCOUNT_EMAIL_VERIFICATION
    = "none"`; **no password-reset endpoints** in `apps/identity/urls.py` → F must wire EMAIL_* +
    a standard tenant-scoped password-reset (request + confirm) + frontend link.
  - Flower ships an insecure default (`admin:flowerpass`, docker-compose.yml:173) → F1 documents a
    real credential.
  - `GET /api/auth/me` (apps/identity/views.py:141) returns `role` but **no capabilities list** →
    the D2 single-source-of-truth fix will add server-computed `capabilities` to /me and gate the
    frontend on them.
