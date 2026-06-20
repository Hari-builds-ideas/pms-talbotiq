# BUILD_0_READ_FIRST.md — Operating contract for the production-hardening build series

> This is the shared rulebook for BUILD_1 … BUILD_5. Claude Code MUST read this file IN FULL at the
> start of EVERY build run, before doing anything else. The numbered build files (BUILD_1_…, etc.)
> each assume these rules and do not repeat them. Run the builds STRICTLY IN ORDER: 1 → 2 → 3 → 4 → 5.
> Do not start BUILD_N until BUILD_(N-1) is committed, pushed, and green.

---

## 0. What this series is

A sequential, code-only production-hardening of the Talbotiq PMS. Scope is REPOSITORY-LEVEL ONLY:
changes that can be built, tested, and verified inside the repo against the EXISTING stack (Django+DRF,
the existing MySQL, the existing Redis, the existing Celery, the existing React app). 

**Explicitly OUT OF SCOPE (do NOT attempt — these need infrastructure Hari provisions separately):**
cloud load-balancer provisioning, managed-database provisioning, creating a real read replica,
Kubernetes, TLS certificates, a secrets vault. Where the work touches these, write the CODE that is
READY for them (e.g. the DB router, the prod settings, the secret-resolution seam) and verify it
against the single existing instance — never block on infra that doesn't exist.

The order of work (this is the series order):
1. BUILD_1 — N+1 / ORM optimization + the DB query foundation.
2. BUILD_2 — Move AI workloads to asynchronous Celery (off the request thread).
3. BUILD_3 — Redis-backed ATOMIC budget + rate limiting; DATABASE_ROUTERS for future read-replica.
4. BUILD_4 — Production settings separation + deploy-readiness; metrics/observability/health;
   optimistic locking + concurrency; response caching for hot endpoints.
5. BUILD_5 — Web application UX completion (the Tier-1 redesign), then it ends with a MOBILE readiness
   gate. (Mobile itself is a SEPARATE later series — only after web is complete and verified.)

---

## 1. Running model

- Claude Code runs UNATTENDED in AUTO MODE on **Claude Opus (do NOT switch models)**, extra effort.
- Do NOT stop to ask. When a genuine decision is needed: append it to `QUESTIONS.md`, choose the safe
  default, record the choice in `DECISIONS.md`, and CONTINUE.
- Do NOT stop after a single feature. Within a build file, complete EVERY phase in order. Continue until
  the whole build file is done (or a hard blocker stops one phase — then continue with the next
  independent phase).
- Work SEQUENTIALLY. Never start a phase that depends on an unfinished earlier phase.

## 2. Sources of truth (read before coding; never invent against them)

`CLAUDE.md`, `docs/PRODUCT_STATE.md`, `docs/SYSTEM_DESIGN_AND_READINESS.md` (this series implements its
§9 build-task checklist), `docs/BUILD_NOTES.md`, `docs/frontend-contract/*`, `docs/frontend-redesign/*`
(ux-spec §8.3 drives BUILD_5), `docs/RUNBOOK.md`, `docs/AI_GOLIVE.md`. The backend `apps/*/serializers.py`,
`apps/*/models.py`, `apps/*/urls.py`, the RBAC matrix, and `config/settings/*` are the AUTHORITY for
real shapes/scope/config. The frontend `src/lib/api/*` + types are the client authority. NEVER invent an
endpoint, field, enum, status code, or setting — verify against the code; if something needed is missing,
log it in QUESTIONS.md, pick the safe default, continue.

## 3. The three living documents (create if absent; UPDATE CONTINUOUSLY)

- **PROGRESS.md** — append-only log. For every phase/task: a timestamp-ish ordinal, what was done, the
  files touched, the verification performed (with the live result / test count), and the commit hash.
  Keep a running "current build / current phase" header at top.
- **DECISIONS.md** — every non-trivial choice: the decision, the options considered, why, and the
  safe-default rationale. Reference the QUESTIONS.md item it resolves if any.
- **QUESTIONS.md** — every open question for Hari: the question, why it matters, the default you took so
  you could continue, and what choosing differently would change. NEVER block on a question — default +
  continue.

If blocked on a task: write the blocker into `BLOCKER_<build>_<phase>.md` AND note it in PROGRESS.md,
leave prior work green/committed/pushed, and CONTINUE with the next independent task.

## 4. "Done" means REAL + VERIFIED (not just written)

A task is done only when:
- The change is implemented to production grade (typed, no dead code, no `# TODO leave it` stubs).
- Backend: the FULL `pytest -q` suite is green (it was 1059 passing — it must never regress); you ADD
  tests for every new behaviour (a new task, a router, a lock, a cache path, a serializer change).
- Frontend (where touched): `npm run build` + `tsc --noEmit` + `eslint .` all clean; add Vitest tests
  for new load-bearing logic.
- The behaviour is VERIFIED the way the task specifies — for backend perf/async/concurrency work that
  usually means a test that asserts the property (query count, a task enqueued, a 409 on stale write,
  a cache hit), and where a live HTTP check is specified, run it against the running stack and capture
  the result in PROGRESS.md.
- Mark verification honesty in PROGRESS.md: **[test]** asserted by a test, **[live]** exercised over
  real HTTP, **[build]** build/typecheck/lint only.

## 5. Guardrails that never relax (true at every commit)

- NEVER weaken RBAC / data scope / tenant isolation. The fail-closed `TenantScopedManager`, the
  cross-tenant→404, the server-side RBAC matrix + scope on every endpoint: untouched or strengthened.
- HITL stays real on every AI/automated artifact (PENDING until a human acts). Moving AI to Celery
  (BUILD_2) MUST preserve this: the async result still lands PENDING_HUMAN_REVIEW, metered in the
  TokenLedger, never auto-final.
- Anonymisation guarantees (360 giver identity never egressed; min-volume suppression) stay intact.
- AI output stays REAL provider output through the one `LLMGateway`; with no key the graceful 503 /
  deterministic path must still hold.
- `.env` and secrets NEVER staged — scan the staged diff for key material (`gsk_`, `AIza`, `SECRET`,
  `PASSWORD`, tokens) before EVERY commit. Runtime artifacts stay gitignored.
- `seed_demo` stays idempotent (runs twice clean) — if you extend it, keep that property.

## 6. Protect the Groq free tier (this whole series should need almost no LLM calls)

This is plumbing/perf/UX work — it must NOT burn quota. Do NOT call real agents to "test" things; use
the existing `FakeLLMProvider` in tests (it's already how the suite exercises the AI seams) and reuse
seeded/PENDING artifacts for any live check. If a real LLM call is genuinely unavoidable, keep the model
map + the global ceiling + the 429 back-off, stay to 1 record, and note it. A Groq 429 is expected, not
a failure. BUILD_2 (async AI) MUST be testable end-to-end with the FakeLLMProvider — design it so.

## 7. Commit / push discipline

After each COMPLETE phase (or a coherent group within it): ensure green (tests/build/lint) + the
verification done, then `git add -A && git commit -m "<build> <phase> — <what>" && git push origin main`.
A synced push per phase is required. If a push is rejected / non-fast-forward, do NOT force — STOP, write
`BLOCKER_<build>_push.md`, and continue local-only commits while flagging it loudly in PROGRESS.md.
Before every commit: run the secret scan (rule 5) and confirm `.env` is untracked.

## 8. End of EACH build file

Write/append `<BUILD>_REPORT.md` (e.g. `BUILD_1_REPORT.md`): phases completed, what's verified [test]/
[live]/[build], the commit+push list, every QUESTIONS/DECISIONS/BLOCKER entry added, the backend test
count after, and the recommended check for Hari. Then proceed to the NEXT build file automatically
(unless a hard blocker says otherwise) — the series is meant to run continuously.

## 9. The prime directive

Hari can run Claude Code continuously for days. The goal is to COMPLETE as much real, verified,
production-grade repository work as possible, in order, without stopping for single features. Quality and
correctness over speed; verified over written; honest PROGRESS.md over optimistic claims. When the whole
series (BUILD_1..5) is done, the app should be code-ready such that the remaining work is purely (a) Hari
provisioning infra and (b) plugging in the Gemini key — both of which are out of this series' scope by
design.
