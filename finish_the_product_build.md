# FINISH_THE_PRODUCT_BUILD.md — Complete the PMS web product, then plan mobile (long autonomous run)

> Hari is away. You are running unattended in AUTO MODE on **Claude Opus (do NOT switch models)** for a
> long session. The PMS already RUNS as one Docker stack: real React frontend on the real API, seeded
> demo data, AI agents alive on Groq through the safety pipeline, and the 360 feedback loop complete.
> Your mission now: **finish the WEB product to a genuinely production-grade, demo-ready standard** —
> close the remaining gaps, make the AI output actually good, polish it, harden it — and then **leave a
> complete, written MOBILE build plan** plus a **TEST-THIS-HARI.md** that Hari walks through when he
> returns. Read this whole file, then read the docs in Phase 0, then begin at Phase A.
>
> The standard is the one the backend already set: real, tested, no dead buttons, no mock-only screens,
> RBAC/scope/tenant isolation never weakened, every AI output real + metered + HITL-gated.

---

## 0. OPERATING CONTRACT — these rules override convenience (read fully)

### 0.1 Sources of truth (read first, never invent against them)
- `CLAUDE.md` — the locked stack + the non-negotiable architecture rules.
- `docs/BUILD_NOTES.md` — every backend module's behaviour, endpoints, enums, safety properties.
- `docs/FRONTEND_READINESS.md` + `docs/frontend-contract/*` (00_overview, 01_screens,
  02_state_machines, 03_data_dictionary, 04_role_journeys, 05_open_questions) — the frontend contract.
- The morning reports: `FRONTEND_MORNING_REPORT.md`, `MAKE_IT_REAL_MORNING_REPORT.md`,
  `PHASE4_MORNING_REPORT.md`, `PHASE4D_MORNING_REPORT.md` — what is already done + verified.
- The `NEEDS_HARI_*.md` files at repo root (analytics scope, llm provider, pack mapping, secrets,
  feedback subject discovery) — open decisions + safe defaults already taken.
- The backend `apps/*/serializers.py` are the AUTHORITY for exact payload shapes. The frontend
  `src/lib/api/endpoints.ts` + types are the authority for the client. NEVER invent an endpoint, field,
  enum value, or status code — verify against the code. If something needed is genuinely missing, write
  `NEEDS_HARI_<topic>.md`, choose the safe default, and continue.

### 0.2 What "done" means for this run
A thing is done ONLY when it is REAL: it runs against the live Docker stack, every action hits a real
endpoint and reflects the real result, all states (loading / empty / populated / error-by-code /
locked-by-feature-flag / pending-HITL / 404-out-of-scope / 429 / 503) are handled, and it is verified
over real HTTP with the result captured in your notes. A screen that only works against MSW mocks is
NOT done. A button that does not call a real endpoint is NOT done.

### 0.3 Phase + sub-phase gating
- Work the phases A → B → C → D → E → F → G → H in order. Within a phase, do the sub-items in order.
- A sub-item is complete only when: backend test suite green where you touched the backend (+ new tests
  for new backend behaviour); frontend `npm run build` + `tsc --noEmit` + `eslint .` all clean; the
  live verification described for it is performed and captured.
- After each COMPLETE sub-phase (or coherent group), commit locally with a clear message AND push:
  `git add -A && git commit -m "Finish-web <phase> — <what>" && git push origin main`.
  A synced backup per sub-phase is required. If a push is rejected / non-fast-forward, do NOT force —
  STOP and write `BLOCKER_<phase>.md`.
- If a sub-phase cannot be made real after genuine effort, STOP that phase: write `BLOCKER_<phase>.md`
  (what failed, exact error, what you tried, what you need), leave all prior work green/committed/pushed,
  and SKIP to the next INDEPENDENT phase only if it does not depend on the blocked one (note the skip in
  the report). Never build on top of a broken sub-phase.

### 0.4 Secrets + Groq free-tier discipline (CRITICAL — protect the key and the quota)
- The Groq key is in the gitignored backend `.env` as `GROQ_API_KEY`. Confirm `.env` is gitignored,
  untracked, and NEVER staged — scan the staged diff for `gsk_` / key material before EVERY commit.
- Two-model strategy already exists in `settings.LLM_MODEL_MAP` (70B for human-read agents, 8B for
  chat). Keep it. Keep the global call ceiling + 429 backoff.
- When PROVING any AI flow, exercise ONE or TWO seeded records — never the whole seed. Keep total real
  LLM calls for THIS ENTIRE RUN well under ~150, within 30 RPM and 12,000 TPM (keep prompts/outputs
  reasonably sized). Treat a Groq 429 as expected (back off, honour Retry-After), not a failure. If you
  approach a limit, switch remaining non-critical proofs to the 8B model and note it.

### 0.5 Standing guardrails (true at every commit)
- Never weaken RBAC / data scope / tenant isolation to make a screen easier. Succession stays invisible
  to employees (404). Own-only where the backend says own-only.
- HITL gates stay real on every draft/AI surface (reviews, feedback summaries, succession plans, JD,
  career): nothing AI is ever presented as final; a human approves/releases/publishes.
- AI output is REAL Groq output, metered in the `TokenLedger`, locked PENDING_HUMAN_REVIEW until a human
  acts. Never fabricate output; with the key unset, the graceful 503 path must still hold.
- Production-grade code: no `any`-soup, typed, accessible (labels/focus/keyboard/aria), real states,
  reusable components, consistent design tokens. Keep runtime artifacts + `.env` out of git.

### 0.6 End of run
Write `FINISH_WEB_MORNING_REPORT.md` AND `TEST-THIS-HARI.md` (Phase H). The morning report: phases done,
what is genuinely working end-to-end (with the exact live verifications you ran), the commit+push list,
every NEEDS_HARI/BLOCKER file, Groq usage consumed (per model), what remains, and recommended next steps.
Be scrupulously honest about what you verified LIVE vs by build/typecheck. Leave the tree clean, the
stack running, everything pushed.

### 0.7 Scope boundary for this run
- IN SCOPE: finishing + polishing + hardening the WEB product (Phases A–G) and WRITING the mobile plan +
  the test script (Phase H).
- OUT OF SCOPE: actually building the mobile app (that is a separate run from the plan you write here);
  swapping to a real production secrets vault; swapping the in-repo graph runner for real LangGraph
  StateGraph (optional, only if it stays green and time allows — otherwise leave + note). Do NOT start
  the React Native app in this run.

---

## PHASE A — Close the known functional gaps (make the product whole)

### A1. Feedback subject discovery (the gap PHASE4D flagged) — `NEEDS_HARI_feedback_subject_discovery.md`
Today an employee subject cannot list their own feedback cycles (the cycles list is Manager+), so the UI
can't auto-discover the subject's own summary id. Fix it properly:
- Add a thin, subject-scoped read on the backend: a `GET /api/feedback/my-cycles` (or extend the existing
  feedback surface) that returns ONLY the cycles where the caller is the SUBJECT, with the released-summary
  id/status where available. Tenant-scoped, own-subject-only, no giver identities, 404/empty for none.
  Add it to the RBAC matrix + oracle if a new capability is cleaner; otherwise reuse an existing one and
  document the choice. Add backend tests (subject sees only their own; never another's; cross-tenant 404).
- Wire the frontend "My 360" so it auto-discovers and shows the subject's released summary without a
  manually-pasted id; keep the 403 SUMMARY_NOT_RELEASED + suppressed-group states.
- This same endpoint is needed by the mobile self-service surface — note that in the mobile plan.
**Verify live:** an employee opens "My 360" and sees their released summary with no id paste; a different
employee cannot see it; below-threshold groups marked suppressed. Then resolve/annotate the NEEDS_HARI file.
**Commit + push** `Finish-web A1 — feedback subject discovery (my-cycles)`.

### A2. Sweep for any other "works-but-can't-be-reached" gaps
Walk every screen group against the live API as each role and find anywhere the UI cannot reach data the
backend exposes (a missing list filter, a detail that needs an id the UI can't get, a tile that links
nowhere, a paginated list the UI treats as an array or vice-versa). For each REAL gap:
- If it is a thin backend read/filter that's genuinely missing, add it production-grade (scoped, tested).
- If it is a frontend wiring bug, fix it.
- If it is a product decision, write `NEEDS_HARI_<topic>.md` + a graceful placeholder.
Keep this tightly scoped — only real reachability gaps, no gold-plating.
**Verify live** per fix; **commit + push** `Finish-web A2 — reachability gaps closed`.

---

## PHASE B — Make the AI output GENUINELY GOOD (the highest-impact phase)

The agents currently produce real but GENERIC, PADDED output (e.g. a review that says "the employee"
with no name, praises "risk management" only because a field said on-track, and pads four sentences where
one would do). The cause is thin evidence in + loose prompts. Fix BOTH, per agent. Same Groq models — far
better output. Do NOT increase call volume to test (one/two records per agent).

### B0. Shared improvements (do first, all agents benefit)
- **Evidence builders:** for each agent, assemble the RICH real context the backend already has and pass
  it into the prompt — the subject's display_name, actual goal TITLES + KPI names + target vs actual +
  attainment %, the computed CycleScore (raw/T/cohort/risk/pace), and (where the agent is allowed)
  anonymised feedback THEMES. Today agents lean on a thin summary; give them the specifics. Keep PII
  scrubbing intact (names of the SUBJECT are fine in a review; giver identities never enter feedback
  summaries).
- **Prompt quality contract:** rewrite each agent's system prompt to demand: address the person by name;
  cite SPECIFIC goals/KPIs/numbers from the evidence (no generic claims); be concise and concrete (ban
  filler/padding/throat-clearing; no "it is important to note", no restating the score in every section);
  actionable, manager-grade language; output strictly in the required JSON schema. Add a short style spec
  ("specific over generic, evidence over adjectives, brief over padded").
- **Schema + validation:** tighten each agent's output schema so empty/padded/garbage sections fail
  validation and are regenerated or flagged low-confidence. Keep confidence calibrated to evidence
  sufficiency (thin evidence → lower confidence + the existing warning).
- Make all of the above per-agent CONFIG (prompt + model + evidence set in settings) so it's tunable
  without code edits later.

### B1. Agent 1 — Review Assistant (the one Hari saw)
Feed real goals/KPIs/score/feedback-themes + name; rewrite the prompt to produce a grounded, specific,
non-padded 5-section review that references the actual goals and numbers. Keep PENDING + confidence +
citations + HITL.
**Verify live (ONE seeded review):** capture the before/after — the new draft names the person, cites
specific goals/KPIs/numbers, and contains no generic padding. Record the transcript in the report.

### B2. Agent 3 — Feedback Summarization
Feed the anonymised THEMES richly (never giver identities); prompt for specific, balanced, evidence-based
themes (not platitudes), preserving the breach-check + threshold + HITL. **Verify live** on one cycle.

### B3. Agent 4 — Succession narrative
Feed the real bench/readiness/9-box/coverage context; prompt for a crisp, decision-useful narrative + red
flags, not generic prose. New source=AI plan PENDING, deterministic untouched. **Verify live** on one plan.

### B4. JD Generator
Feed the saved brief richly; prompt for a tight, role-specific JD (real responsibilities/must-haves from
the brief, no boilerplate). source=AI PENDING. **Verify live** on one JD.

### B5. Career Roadmap
Feed the real skill-gap + goals; prompt for specific, actionable, advisory tiers (never auto-promotion;
the advisory CHECK still holds). **Verify live** on one roadmap.

### B6. Agent 2 — KPI nudges & Chat
Nudges: phrase the real risk classification specifically (name the KPI + the trajectory), 8B model. Chat:
ensure answers are grounded in the real scoped data it retrieves (not vague), still read-only + RBAC-bound
+ write-blocked. **Verify live**: one nudge, one in-scope chat query (grounded answer), one out-of-scope
(empty), one write intent (blocked).

**Gate for Phase B:** backend suite green where touched (+ tests for any evidence-builder/schema code);
frontend clean; each agent proven on 1–2 records with captured transcripts; Groq calls kept low.
**Commit + push** per agent or in two coherent groups (B1–B3, B4–B6) `Finish-web B — AI output quality`.

---

## PHASE C — Deepen the remaining product surfaces to "a company would use this daily"

For each, build against the live API, all states real. Add backend support ONLY where a genuinely useful
capability is missing (scoped + tested); otherwise compose from existing endpoints.

### C1. The full review CYCLE as an HRBP/manager operation
- An HRBP can open/advance/close a performance cycle; managers see their reports' reviews for the active
  cycle; the calibration read (HRBP) shows the cohort. Make running a cycle feel like a guided operation,
  not isolated screens. Surface the cycle status everywhere reviews/goals/analytics depend on it.
**Verify live**; commit+push.

### C2. Goals & KPIs — complete the loop
- Goal create/edit with the live 100% KPI-weight sum (server-enforced), record actuals (own-only),
  manager approve, recompute → risk badges update, KPI templates instantiate. Make the weekly cadence
  legible (pace vs elapsed). **Verify live**; commit+push.

### C3. Approvals — designer + inbox + tracker, end to end
- Create a workflow (sequential/parallel, role/named steps), activate it, route a real review/JD through
  it, act in the inbox (approve / reject-with-reason), watch the tracker advance + escalation. Make the
  "re-create to edit steps" model clear (open-question #3). **Verify live** an end-to-end route; commit+push.

### C4. Org chart — actionable
- Readable reporting tree with headcount/vacancy rollups; person card; create/fill/close positions; link a
  PUBLISHED JD; reassign (cycle → 422). **Verify live**; commit+push.

### C5. Succession — HRBP tool
- Coverage dashboard (RED/AMBER/GREEN), interactive nine-box, bench + readiness overrides, mark critical
  role, generate → review → publish, Agent-4 enrich switches to the new AI plan (already fixed). Employees
  never see it. **Verify live**; commit+push.

### C6. Analytics — real charts + suppression visible
- Individual trend, department analytics with min-cohort (<5) suppression clearly shown (aggregate-only +
  privacy notice), calibration grid (HRBP/Admin). Use real charts, not raw numbers. **Verify live** the
  4-vs-5 suppression boundary; commit+push.

### C7. Admin + Billing + Integrations + Audit
- Users/roles/tenant-config; entitlements + the upgrade-to-FULL_AI modal flipping flags live; integrations
  config (Jira/Slack, secret_ref NAME only, never a token); the read-only audit console (filter +
  paginate, no mutation). Surface TokenLedger/budget usage on the billing screen (the AI cost story).
**Verify live** an upgrade flips flags app-wide; commit+push.

---

## PHASE D — Product-grade cross-cutting (4g) — make it feel finished

### D1. Navigation & wayfinding
Breadcrumbs, consistent page headers, active-state nav, a useful global search where it helps (people,
JDs, reviews — scoped), and a notifications/inbox affordance (approvals awaiting, feedback requests,
summaries to release) driven by real counts.

### D2. First-run & empty experiences
A genuine empty/first-run state per screen (not a blank table) that tells the user what to do. A clear
"AI not configured" calm state where the key is absent (must still hold).

### D3. Errors, resilience, feedback
Global error boundary; consistent toast conventions; the full error-code mapper applied everywhere
(400/401/403/404/409/422/429/503); 429 shows Retry-After + upgrade hint; optimistic-feel via React Query
with proper invalidation after mutations; skeletons not spinners.

### D4. Accessibility & responsive-tolerance
Keyboard navigation, focus management in dialogs/menus, labels + aria, color-contrast on the status
badges; ensure the desktop Admin Hub does not break on a narrow viewport (it is desktop-first, but must
degrade gracefully — true responsive self-service is the mobile surface).

**Gate:** frontend clean; verify the cross-cutting behaviours live on a few representative screens.
**Commit + push** `Finish-web D — cross-cutting polish`.

---

## PHASE E — Visual polish pass (make it look premium, within the locked stack)

You are NOT redesigning; you are RAISING the finish using the existing tokens + shadcn/Tailwind. Aim for a
restrained, modern, premium SaaS-admin feel (strong typography hierarchy, generous whitespace, calm
palette, subtle depth, consistent density). Concretely:
- Audit the design tokens (`src/styles/globals.css`, `tailwind.config.ts`): a single confident accent,
  refined neutrals, semantic colors for the status badges, a consistent type scale (tabular numbers for
  scores), an 8px spacing rhythm, hairline borders, rounded-2xl cards, subtle (not heavy) shadows.
- Apply consistently across every screen: page-header pattern, card/table/dialog/badge/empty/skeleton
  styling, button hierarchy (primary/secondary/ghost/destructive), spacing density. Kill any
  bootstrap-default or inconsistent look.
- Micro-interactions: hover/focus states, loading skeletons, smooth state transitions, disabled+reason
  tooltips on gated actions, a polished login + app shell (the first impression).
- Make the AI surfaces feel intentional: the PENDING/confidence banners, the draft-vs-final treatment, the
  chat panel.
Do NOT invent a new brand or import unlicensed assets; keep it clean and original.
**Gate:** frontend clean. **Commit + push** `Finish-web E — visual polish pass`.

> NOTE: This is the one area best refined with Hari's eye. Make it good, but in TEST-THIS-HARI.md call out
> the specific screens/areas where you want his visual judgement, since you cannot see the rendered pixels.

---

## PHASE F — Harden for QA handoff (Module 14 groundwork)

### F1. Frontend tests
Add Vitest + Testing Library tests over the load-bearing logic: the auth/refresh flow, the error-code
mapper, RBAC/feature-flag gating (locked → upgrade prompt; succession hidden from employees), the HITL
action gating on reviews, the KPI-weight 100% validation, the min-cohort suppression rendering. Aim for
meaningful coverage of the risky bits, not 100%.

### F2. Backend test integrity
Confirm the full backend suite is green (1050+); add tests for any backend you touched (A1, B evidence
builders/schemas, any C reads). The suite must never have regressed.

### F3. End-to-end smoke script
Add a repeatable smoke checklist/script (documented commands or a small script) that brings the stack up,
seeds, and exercises the core journeys via curl/HTTP, so QA can re-verify quickly. Capture expected
results.

### F4. Run hygiene
`.env` gitignored + unstaged (re-verify); no secrets in any committed file; runtime artifacts ignored;
`docker compose up -d --build` + `seed_demo` clean from scratch (verify seed runs twice with no dupes).
**Commit + push** `Finish-web F — QA hardening`.

---

## PHASE G — Documentation for handoff

- `docs/RUNBOOK.md`: how to run the whole stack, seed, log in (all demo accounts + roles), turn AI on/off
  (the Groq key), flip mocks, run tests, where things live.
- `docs/AI_GOLIVE.md`: consolidate the `NEEDS_HARI_llm_provider.md` steps — pick provider, set key, model
  map, budgets, optional real-LangGraph swap, LangSmith tracing — the single "make AI production" guide.
- Update `docs/BUILD_NOTES.md` with a short "web product complete" section pointing to the new surfaces.
**Commit + push** `Finish-web G — handoff docs`.

---

## PHASE H — Leave the two deliverables Hari asked for

### H1. TEST-THIS-HARI.md (the hands-on test script for when Hari returns)
Write a thorough, friendly, STEP-BY-STEP manual test script Hari can follow in the browser, organised so
he can do it in ~30–45 minutes. Requirements:
- Start with the exact run commands (`docker compose up -d --build`, `seed_demo`, the URL, the demo
  accounts + password + tenant for EACH role).
- Then a numbered walkthrough PER ROLE (Admin, HRBP, Manager, Employee), each step phrased as
  "do X → you should see Y", covering EVERY major surface and the things this run changed:
  - the role cockpit/dashboard;
  - run a review end-to-end incl. **request AI draft → confirm the new draft names the person + cites
    specific goals/KPIs/numbers + has no padding** (the Phase B improvement — call this out so Hari judges
    the AI quality directly);
  - goals/KPIs (100% weight, record actual, recompute, approve);
  - approvals (configure → route → approve/reject → tracker);
  - org chart (reassign, positions, link JD);
  - succession (nine-box, bench, generate → enrich → publish; confirm employees get nothing);
  - analytics (the 4-vs-5 min-cohort suppression);
  - 360 feedback FULL loop (request → give as enough givers to cross the threshold → close → AI summary
    PENDING → HRBP release → subject "My 360" sees it; confirm a below-threshold group is suppressed);
  - entitlements upgrade (STARTER globex vs FULL_AI acme; flip a flag, watch UI unlock);
  - audit console (read-only), integrations (no token shown), chat (grounded answer / out-of-scope empty /
    write blocked).
- A clearly-marked **"LOOK AT THIS — your visual judgement needed"** section listing the screens from
  Phase E where Hari's eye should decide (since the agent couldn't see rendered pixels).
- A **"KNOWN LIMITATIONS / NOT YET DONE"** section (honest): anything deferred, any NEEDS_HARI/BLOCKER,
  the AI-on-Groq free-tier limits, and the fact that mobile is a separate build (point to the plan).
- A short **"HOW TO REPORT BACK"** note: what feedback is most useful to bring to the next build (which
  screens feel off, which AI outputs are good/bad, which flows are confusing).
Make it genuinely usable as a checklist (checkbox bullets), not prose.

### H2. MOBILE_BUILD_PLAN.md (the full plan for the mobile app — PLAN ONLY, do not build)
Write a long, detailed, decision-complete plan for building the mobile app, so a future autonomous run can
execute it the way the web build_md files drove the web. Cover:
- **Decision framing:** responsive mobile-web (reuses the React web app in a phone browser) VS a true
  native iOS+Android app. RECOMMEND **React Native + Expo** for true cross-platform native from one
  TypeScript codebase, and explain WHY (one codebase both platforms; same React+TS+API client/types as the
  web; built in VS Code/Cursor with Claude Code, NOT Xcode — Xcode/Android Studio only at build/submit
  time). Note that responsive-web is the faster interim if app-store presence isn't yet needed. Leave the
  final call to Hari with a clear recommendation.
- **Scope:** mobile is the EMPLOYEE/MANAGER SELF-SERVICE surface, NOT the Admin Hub. Enumerate the
  screens: login + MFA, my dashboard, my goals + record actuals, my review (view + self-assessment), give
  360 feedback + my 360 summary (uses the new A1 my-cycles endpoint), my career roadmap + progress, the AI
  chat, notifications. Succession/admin/analytics-dept are explicitly OUT (management/desktop).
- **Architecture:** Expo + React Native + TypeScript; reuse the web's typed API client + types + auth
  logic (extract the shared layer so web and mobile don't drift — name the files to share); secure token
  storage (expo-secure-store, NOT localStorage); the same RBAC/feature-flag/error-code/HITL conventions;
  the same 404/403/429/503 handling; offline/loading states; push-notification consideration (later).
- **Reuse map:** exactly which existing backend endpoints each mobile screen calls (cite them), confirming
  the backend already supports the self-service surface (it does) and listing any thin reads still needed
  (e.g. A1 my-cycles, the my-features endpoint already exists, the nudges endpoint).
- **Phased build plan** (mirroring the web build_md gating): Phase 0 Expo scaffold + shared layer + design
  tokens + auth + shell/nav → then one screen-group per phase, each gated (typecheck/lint/build clean +
  runs in the Expo simulator), committed + pushed, blocker protocol, morning report. Include a
  per-phase acceptance list.
- **Design:** mobile-first patterns (bottom tab nav, large tap targets, native feel), reusing the web's
  palette/typography tokens for brand consistency.
- **Build/run/release notes:** Expo Go for dev on a real phone; EAS build for store binaries; what Hari
  needs (Apple Developer + Google Play accounts) and when (only at release, not for dev). Keep it honest
  about effort (this is a multi-session build, not one run).
- **Open questions for Hari** with safe defaults, the way the other build files do.
Target real depth — this file should be long enough that a future run can execute it without guessing.

**Commit + push** `Finish-web H — TEST-THIS-HARI + MOBILE_BUILD_PLAN`.

---

## CROSS-CUTTING ACCEPTANCE (re-check at every commit)
- Whole stack starts with one command, healthy; frontend on the REAL API; seed runs twice clean.
- Every action hits a real endpoint and reflects the real result; no dead buttons; no mock-only screens.
- RBAC/scope/tenant isolation intact; succession invisible to employees; HITL real on every AI/draft
  surface; AI output real, metered, PENDING.
- Backend suite green where touched (+ tests); frontend build + tsc + lint clean.
- `.env`/secrets never staged; Groq usage kept low; runtime artifacts gitignored.
- Committed AND pushed; pushes fast-forward (never force).

## END OF RUN
Write `FINISH_WEB_MORNING_REPORT.md` (per 0.6) AND ensure `TEST-THIS-HARI.md` + `MOBILE_BUILD_PLAN.md`
exist and are complete. Be honest about live-verified vs build-only. Include total Groq usage per model.
Leave everything committed + pushed, the stack running, the tree clean. A deep, working, polished,
verified web product + a clear test script + a real mobile plan is the goal — if you run low on capacity,
STOP after the current sub-phase (committed, pushed, running) and STILL write the report + TEST-THIS-HARI
covering what was done, so Hari can test exactly what exists.
