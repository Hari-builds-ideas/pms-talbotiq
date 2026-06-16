# MAKE_IT_REAL_BUILD.md — Turn the PMS into a real, running, AI-powered product (8-hour autonomous run)

> Hari is asleep. You are running unattended in AUTO MODE on **Claude Opus (do NOT switch models)**
> for up to ~8 hours. The PMS today is a correct backend API + a mock-data frontend that are NOT
> connected, with the AI agents returning 503. Your mission: **assemble the parts into ONE running,
> production-grade product** — real backend serving a real frontend with seeded data, the AI agents
> genuinely running on a real LLM (Groq), and the PMS experience deepened so a company could actually
> use it. Read this whole file, then read the docs listed in Phase 0, then begin.
>
> Order of intent (Hari's priority): **(1) wire it real → (2) make the AI alive → (3) deepen the product.**

---

## 0. OPERATING CONTRACT — these rules override convenience

1. **Read first (sources of truth):** `CLAUDE.md`, `docs/BUILD_NOTES.md`, `docs/FRONTEND_READINESS.md`,
   `docs/frontend-contract/*`, the four `NEEDS_HARI_*.md` files at repo root, and
   `FRONTEND_MORNING_REPORT.md`. The backend serializers (`apps/*/serializers.py`) are the authority
   for exact payload shapes. NEVER invent an endpoint/field/enum — verify against the code.

2. **The product must be RUNNABLE and REAL at the end, not mocked.** "Done" for this run means: the
   Django backend runs in Docker, the React frontend talks to it over real HTTP (not MSW), a seeded
   demo tenant lets you log in as each role and actually DO things, and the AI agents return real
   model output through the existing safety pipeline. A screen that only works against mocks is NOT done.

3. **Phase gate.** Finish each phase COMPLETELY before the next. A phase is done only when its
   acceptance checks (listed per phase) pass for REAL (backend test suite still green where touched;
   frontend `npm run build` + `tsc --noEmit` + lint clean; the live end-to-end check described in the
   phase actually performed via curl/HTTP against the running stack and the result captured in your
   notes). If a phase cannot be made real after genuine effort, STOP: write `BLOCKER_<phase>.md`
   (what failed, the exact error, what you tried, what you need from Hari), leave all prior phases
   green + committed + pushed, and do not proceed.

4. **Commit AND push after each green phase.** `git add -A && git commit -m "Make-it-real Phase N —
   <name>"` then `git push origin main`. A synced backup each phase is required for this run. If a push
   is rejected/non-fast-forward, do NOT force — STOP and write a BLOCKER. Keep runtime artifacts and
   any real secrets OUT of git (verify `.env` is gitignored and never staged).

5. **Secrets / the LLM key.** The AI needs a real key. Expect a **Groq** key in the backend
   environment. BEFORE Phase 3, check for it: look for `GROQ_API_KEY` (or `LLM_API_KEY`) in the
   backend `.env` / environment. If it is MISSING, do NOT hardcode or invent one — complete Phases 1–2,
   then write `NEEDS_HARI_groq_key.md` ("put GROQ_API_KEY=... in backend .env, then re-run from Phase 3")
   and CONTINUE into Phase 4+ (deepening) only where it does NOT need the live AI; stop and blocker
   anything that does. NEVER commit a real key.

6. **If you need a human decision,** write `NEEDS_HARI_<topic>.md`, choose the safe sensible default,
   and continue. Don't stall.

7. **At the end** (all phases, or stop/block, or low on capacity) write `MAKE_IT_REAL_MORNING_REPORT.md`
   at repo root: phases completed, what is now genuinely working end-to-end (with the exact verifications
   you ran), the commit/push list, every NEEDS_HARI/BLOCKER file, how to run the full stack, what remains,
   and recommended next steps. Leave the tree clean.

8. **Quality bar = production-grade, the standard already set by the backend.** No `any`-soup, no dead
   buttons, real loading/empty/error states, real data, accessible. Every screen's actions must hit a
   real endpoint and reflect the real result. The existing 1050 backend tests must stay green where you
   touch the backend; add tests for new backend behaviour.

---

## PHASE 1 — Make it RUN as one stack (backend ↔ frontend ↔ seeded data)

The single biggest reason it "feels basic": the frontend renders mock fixtures and nothing is wired to
the real API. Fix that first.

**1a. One-command full stack.** Add the frontend to the Docker setup (or a documented compose profile)
so the whole product comes up together: MySQL + Redis + Django (web, celery worker, celery beat) +
the React frontend (Vite dev or a built static served behind nginx) + nginx routing `/api` → Django and
`/` → frontend. Document the single command to start it all. Verify every service reaches healthy
(`/readyz` 200, frontend served, `/api` reachable through nginx).

**1b. A real demo seed.** Create a management command `seed_demo` (idempotent) that builds a realistic
demo tenant a company would recognise: ~1 Admin, 2 HRBPs, 4–6 Managers, ~20–30 Employees in a real
reporting tree (display_names set), an ACTIVE performance cycle, goals + KPIs (weights summing to 100)
with recorded actuals so CycleScores compute to a spread of ON_TRACK/AT_RISK/CRITICAL, some reviews at
various states, a 360 feedback cycle with submitted feedback, a couple of approval workflows (active),
JD library entries (some PUBLISHED), org positions incl. an OPEN vacancy, critical roles + bench +
nine-box placements + a succession plan, career target selections + roadmaps, an entitlement on STARTER
for one tenant and FULL_AI for another (so the upgrade story is demoable), and a few audit rows. This
seed is what makes every screen show believable data. Verify it runs clean and is re-runnable.

**1c. Flip the frontend to the LIVE API.** Set `VITE_USE_MOCKS=false` by default; keep MSW available
behind the flag for offline dev. Wire the real auth flow against the running backend (login → JWT in
memory, refresh handling, logout), and make EVERY feature's data hooks hit the real endpoints. Walk the
frontend-contract screen by screen and fix every place where a shape, field, enum, status code, or
pagination envelope differs from what the real serializer returns (the morning report flagged
`/api/cycles/` shape as assumed — verify it and all others against the real responses). Handle the real
401/403/404/409/422/429/503 from the live server with the existing error mapper.

**Acceptance (perform for real, capture in notes):** bring up the full stack with one command; log in
over real HTTP as Admin, HRBP, Manager, and Employee from the seed; load the dashboard and at least the
users, reviews, org chart, and succession screens against REAL data; perform at least 3 real mutations
end-to-end and confirm the backend changed (e.g. create a user → it appears + an audit row exists;
approve a review through the HITL gate → state changes + audit row; reassign a reporting line → tree
updates). Frontend builds clean. Commit + push `Make-it-real Phase 1 — one running stack + demo seed + live wiring`.

---

## PHASE 2 — Close the real-data gaps the wiring exposes (backend follow-ups, only if needed)

Wiring against real data will surface genuine gaps (a missing read field a screen needs, an endpoint
that returns a shape the UI can't render, an N+1 that makes a screen slow, a missing list filter).
For each REAL gap found in Phase 1:
- Fix it on the backend the right way (serializer field, query optimisation with `select_related`/
  `prefetch_related`, a filter param) — production-grade, with a test, keeping the suite green and
  tenant-scoping intact. Do NOT widen scope or weaken RBAC to make a screen easier.
- If a gap is actually a product decision (a field that doesn't exist and shouldn't be invented), write
  `NEEDS_HARI_<topic>.md` and render a graceful placeholder.
Keep this phase tightly scoped to what the live wiring genuinely requires — do not gold-plate.

**Acceptance:** every Admin-Hub screen renders real data without a console error or an unhandled state;
backend suite green; new behaviour tested. Commit + push `Make-it-real Phase 2 — real-data gaps closed`.

---

## PHASE 3 — Make the AI ALIVE (real LLM via Groq, through the existing safety pipeline)

This is what makes it "feel AI". The architecture is already built (LLMGateway → budget → PII-scrub →
provider → schema-validate → meter → confidence → HITL lock); you are installing the real provider and
turning the agents on. **Requires the Groq key (rule 5).**

**3a. Install the real stack pieces.** Add `langgraph`, `langsmith`, and the Groq SDK (or an
OpenAI-compatible client pointed at Groq's endpoint) to `requirements.txt`; rebuild the images. Keep the
node functions as-is (they are the real logic); optionally swap `apps/ai/graph.run_graph` for a real
LangGraph `StateGraph` per the existing `NEEDS_HARI_llm_provider.md` (do this only if it stays green —
otherwise leave the faithful runner and note it).

**3b. Implement the Groq provider** behind the existing `LLMProvider` ABC (Groq is OpenAI-compatible:
base URL + `GROQ_API_KEY`, a fast model such as a Llama-3.x instruct). Set `LLM_PROVIDER` to it and the
per-seam provider settings so all agents resolve to it. Confirm `llm_configured()` is now true. Leave
the design so an unset key cleanly falls back to the 503 path (never crash).

**3c. Prove the pipeline on REAL output, one agent at a time** (the smoke test that's never been done):
run Agent 1 (Review Assistant) end-to-end against Groq on a seeded review → confirm a real draft comes
back, passes schema validation, gets a confidence score, locks PENDING_HUMAN_REVIEW, audits, and the
TokenLedger records real usage. Then exercise Agent 3 (feedback summary, incl. the post-LLM breach
check on a planted leak), Agent 4 (succession enrich → new source=AI plan PENDING), JD generator, Career
roadmap, KPI nudge (Agent 2), and Chat (RBAC-bound, returns nothing out of scope, blocks writes). Tighten
prompts/schema only as the real output requires — calibrate confidence, fix any schema mismatch a real
model surfaces. Keep the budgets sane for a free Groq tier (set conservative `DEFAULT_AGENT_BUDGETS`).

**3d. Make the AI VISIBLE in the UI.** The frontend must now show real AI: the review AI-draft button
produces a real draft inline with its confidence + PENDING banner; the chat panel returns real answers;
succession enrich, JD generate, career enrich all produce real content into their HITL gates; the KPI
nudges tile shows real Agent-2 nudges. Replace every "503 AI not configured" state with the real,
working flow when the key is present (and keep the graceful 503 for when it isn't).

**Acceptance (capture real transcripts/outputs in notes):** at least Agent 1 + Chat + one more agent
demonstrably produce REAL Groq output through the full safety pipeline, visible in the UI, locked behind
HITL, metered in the TokenLedger; an out-of-scope chat query returns nothing; budget/429 works; with the
key unset the 503 path still holds. Backend suite green. Commit + push `Make-it-real Phase 3 — AI alive on Groq`.

---

## PHASE 4 — DEEPEN the PMS into something a company would actually use

Now make it feel like a real product, not a screen per endpoint. Work through these in order; each is
independently committable, so bank what you can. For each, build it production-grade against real data
and real endpoints (add backend support only where a genuinely useful capability needs it, with tests +
tenant-scoping; otherwise compose from existing endpoints).

**4a. Role-true home dashboards that drive the work.** Make each role's landing page the cockpit it
should be: an Employee sees their goals/progress, their review status, feedback requests awaiting them,
and their career roadmap; a Manager sees the team's at-risk KPIs (real Agent-2 nudges), reviews awaiting
their drafting/approval, their approval inbox, and team coverage; an HRBP sees feedback summaries to
release, succession coverage gaps, calibration; an Admin sees tenant health, entitlement/usage, audit.
Real counts, real links, real empty states. This is the screen that makes it "feel like a PMS".

**4b. The full review cycle as a guided workflow**, not just a state machine: a manager can run a
review for a report end-to-end (gather self+peer assessments → request AI draft → edit → submit →
route through approvals → finalize), with the timeline, the evidence (goals/KPIs/feedback) shown beside
the draft, and the HITL gates obvious. Make the self-assessment + peer-assessment capture real and usable.

**4c. Goals & KPIs as a living surface:** the weighted goal editor with the live 100% sum, recording
actuals, seeing CycleScores recompute and risk badges change, the manager approve flow. A company should
be able to actually run a cycle here.

**4d. 360 feedback end-to-end:** request feedback, give feedback (with the anonymity/min-volume rules
visible), HRBP review/release of the (real-AI) summary, the subject's released view. Make the safety
properties legible in the UI (anonymised, threshold-gated).

**4e. Succession & talent as an HRBP tool:** the nine-box as an interactive calibration surface, bench
management with readiness, the plan generate→review→publish flow with the real Agent-4 enrichment, and
coverage/risk dashboards. Management-only, employees never see it.

**4f. Org, JD, analytics, integrations polish:** org chart readable and actionable (reassign, vacancies,
link JDs); JD library with the lifecycle + real AI generation; analytics dashboards with real charts and
the min-cohort suppression visible; integrations config that clearly shows connected/not.

**4g. Product-grade cross-cutting:** global search where useful, a notifications/inbox affordance,
consistent breadcrumbs, keyboard-friendliness, responsive-tolerance, and a genuine first-run/empty
experience. Make the AI chat assistant genuinely useful (it can answer "who's at risk on my team",
"show me X's goals" within the caller's scope).

**Acceptance per sub-phase:** the workflow is completable end-to-end against real data + real AI, builds
clean, and is committed + pushed (`Make-it-real Phase 4x — <name>`). If you run low on capacity, STOP
after the current sub-phase (committed, pushed, product still runs) and write the report — a deep,
working subset beats a broad broken one.

---

## CROSS-CUTTING ACCEPTANCE (true at every commit)
- The whole stack starts with one command and is healthy; the frontend talks to the REAL backend.
- Every action hits a real endpoint and reflects the real result; no dead buttons; no mock-only screens.
- RBAC/scope/tenant isolation intact (never weakened to ease a screen); succession invisible to employees.
- HITL gates present and real on every AI/draft surface; AI output is real Groq output, metered, PENDING.
- Backend suite green where touched (+ new tests); frontend `npm run build` + `tsc --noEmit` + lint clean.
- Committed AND pushed; `.env`/secrets never committed; runtime artifacts gitignored.

## END OF RUN
Write `MAKE_IT_REAL_MORNING_REPORT.md`: what is now genuinely working end-to-end (with the exact
verifications/transcripts you captured), phases done, commit + push list, NEEDS_HARI/BLOCKER files, the
one-command run instructions, what remains, and recommended next steps (e.g. provider hardening, the
mobile-web self-service surface, QA sweep). Be honest about what you verified live vs. by build/typecheck.
Leave everything committed and pushed; product running; tree clean.
