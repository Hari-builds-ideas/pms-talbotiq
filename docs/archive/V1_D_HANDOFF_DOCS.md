# V1_D_HANDOFF_DOCS.md — complete handoff documentation

**Why this matters:** the author (Hari) is leaving the company. These documents are the handoff — someone
who has never seen this codebase must be able to understand what was built, what's in v1 vs v2, how it
works, and how to continue. Write them to that standard: complete, honest, and clear to a newcomer. No
insider shorthand.

Write all of the following into a `docs/handoff/` folder (Markdown). Ground everything in the ACTUAL code
— cite real modules, real commands, real file paths. Do not invent.

## 1. `docs/handoff/README.md` — start here
- One page: what the product is, who it's for (SMEs), the tech stack, and a map of the other handoff
  docs. The single entry point for a new engineer.

## 2. `docs/handoff/SYSTEM_OVERVIEW.md` — what was built
- The full picture of v1: every feature that exists, what it does, and where it lives in the code.
- The architecture: Django + DRF backend, React SPA, MySQL, Redis, Celery, the provider-agnostic LLM
  gateway. A clear diagram (ASCII or Mermaid) of how requests flow.
- The core invariants a newcomer must NOT break: tenant isolation (fail-closed), RBAC server-side, the
  HITL gate on every AI action, the append-only audit log, LLM calls only through the one gateway,
  no-fabrication. Explain WHY each exists.

## 3. `docs/handoff/V1_VS_V2.md` — the scope split (critical for handoff)
- A clear table: every feature → **In v1 (live)** / **Simplified in v1** / **Deferred to v2 (hidden,
  code present)**.
- For each DEFERRED feature (nine-box, calibration, succession, career roadmaps, advanced admin): where
  the code is, how it was hidden (flag/route/nav), and EXACTLY how to re-enable it for v2. This is the
  most important section for whoever continues.
- For each SIMPLIFIED feature (T-score, goals, analytics): what the simplification was, and where the
  original detail still lives.

## 4. `docs/handoff/HOW_IT_WAS_BUILT.md` — the build story & decisions
- How the system was built and the key decisions + why (multi-tenant model, the agent's
  name-only/params-server-side design, the budget/metering approach, the safety matrix). A newcomer
  needs the "why", not just the "what".
- The testing approach: the backend suite, the frontend tests, the safety/injection matrix, the
  query-budget guards — what they protect and how to run them.

## 5. `docs/handoff/DEVELOPER_SETUP.md` — run it locally
- Exact steps to clone, build, run (docker compose), seed demo data, and log in. The demo accounts +
  tenant + password. How to run the tests. How to recreate containers after changes. Written so a new
  dev is running the app in under an hour.

## 6. `docs/handoff/DEPLOYMENT.md` — how the demo is deployed + the path to production
- How the free demo deploy works (Vercel + Render, per DEPLOY_DEMO.md).
- The honest path to a REAL production deployment later: the requirements already assessed (managed DB,
  Redis, hosting, TLS, secrets, monitoring, the OpenAI/Gemini data sign-off, email/SMTP). Point to the
  existing PRODUCTION_REQUIREMENTS.md. Be clear this is NOT done — it's the v2/production roadmap.

## 7. `docs/handoff/MOBILE.md` — the mobile app status (explicit, for v2)
- State it plainly: **mobile is deferred to v2 and still in development.** The BACKEND and API endpoints
  are ready and working; the mobile FRONTEND (React Native/Expo) needs work — it has bugs and isn't
  visually finished.
- Where the mobile code is, what works, what's broken, and what a v2 engineer should tackle first.
- This is so whoever picks up phase 2 can start from a clear baseline, not guess.

## 8. `docs/handoff/OPEN_QUESTIONS.md` — honest unknowns & product decisions
- The decisions that are product calls, not code (e.g. per-person vs tenant-wide entitlements, the AI
  data-egress sign-off, per-tenant LLM keys). List them so they aren't lost when the author leaves.
- Any known rough edges, tech debt, or "here be dragons" a newcomer should know.

## Rules
- Everything grounded in the real code — cite files/commands. A newcomer should be able to trust every
  statement.
- Honest over optimistic — if something is rough or unfinished, say so. This is a handoff, not a sales
  doc.
- Keep it readable — plain English, short sections, real examples.

## Done when
- `docs/handoff/` contains all eight documents, each complete and code-grounded, such that a new
  engineer could take over the project cold. Logged in PROGRESS_V1.md.
