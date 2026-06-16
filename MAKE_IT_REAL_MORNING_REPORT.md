# MAKE_IT_REAL_MORNING_REPORT.md

**Run:** Autonomous overnight — turn the PMS into a real, running, AI-powered product.
**Model:** Claude Opus (did not switch).
**Headline:** The product is now **one running stack serving a real React frontend off
the real API with seeded data, and the AI agents are ALIVE on Groq** — proven live, end
to end, through the existing safety pipeline (budget → PII-scrub → schema-validate →
meter → confidence → HITL lock). Priorities **(1) wire it real** and **(2) make the AI
alive** are DONE and verified live. Everything is committed **and pushed** to
`origin/main`.

> Honesty about verification: every claim below marked **[live]** was performed over real
> HTTP against the running Docker stack and the result captured. Items marked **[build]**
> were verified by the backend test suite / typecheck only.

---

## Secrets hygiene (done first)
- `.env` (holding `GROQ_API_KEY`) is **gitignored**, **untracked**, and was **never
  staged** — verified before every commit (scanned the staged diff for `gsk_`/key values).
- `docker-compose.yml` passes the key via `${GROQ_API_KEY}` **interpolation only** — the
  literal key is never written to any tracked file. The compose project loads it from the
  gitignored `.env`. **[live]**
- `config/settings/test.py` clears the key + pins the provider off, so the **test suite
  never makes a real Groq call**. **[build]**

## Groq usage this run (free-tier headroom)
- **5 real LLM calls total**, metered in the `TokenLedger`:
  - `llama-3.3-70b-versatile` ×2 — Agent 1 (review draft, 562 tok), Agent 4 (succession, 448 tok)
  - `llama-3.1-8b-instant` ×3 — Chat (read / write-blocked / out-of-scope)
- Global run ceiling counter at **5 / 60**. Well under 30 RPM, 1,000 RPD, 12,000 TPM.

---

## Phase 1 — One running stack + demo seed + live wiring ✅ (commit `570aec7`, pushed)

**1a. One-command stack.** Dockerized the frontend (multi-stage Vite build → nginx) as the
public edge: it serves the SPA and reverse-proxies `/api,/admin,/accounts,/static,/healthz,
/readyz` → the Django `web` tier. `web` auto-migrates on start. Stack = MySQL + Redis +
Django(web) + Celery(worker, beat) + frontend(nginx) + flower.
- **One command:** `docker compose up -d --build`
- **[live]** `GET /` → 200 (SPA), `GET /readyz` → 200 (all checks up) through the edge.

**1b. Idempotent `seed_demo`.** `apps/core/management/commands/seed_demo.py` builds two
tenants so the commercial story is demoable:
- **acme** (FULL_AI): 28 users in a real reporting tree (Admin→2 HRBP→5 Mgr→20 Emp, display
  names set), an ACTIVE cycle, 25 goals+KPIs+measurements → **computed CycleScores**
  (spread of ON_TRACK/AT_RISK), reviews in 4 states, a 360 cycle with submitted feedback,
  2 active approval workflows, a JD library (some PUBLISHED), positions incl. an OPEN
  vacancy, 2 critical roles + bench + 8 nine-box placements + a deterministic plan, career
  roadmaps, audit rows.
- **globex** (STARTER): a smaller tenant whose premium features are locked.
- **[live]** Re-runnable with no duplicates: `docker compose run --rm web python manage.py seed_demo`.
- Demo login: any seeded email (e.g. `admin@acme.test`, `priya@acme.test`, `ada@acme.test`,
  `reza@acme.test`) + password `Passw0rd!demo`, tenant slug `acme` (or `globex`).

**1c. Frontend flipped to the LIVE API** (`VITE_USE_MOCKS=false` baked into the image; MSW
kept behind the flag). Walking the screens against real serializers surfaced and **fixed**
real mismatches:
- login `tenant_slug` (was `tenant`); org reassign `{user,new_manager}` (was `{employee,
  manager}`); review timeline field `note` (was `action`, would have crashed the timeline);
  Positions tab gated to HRBP+ (its list endpoint is scoped to them).

**Acceptance [live]:** logged in over HTTP as **Admin / HRBP / Manager / Employee**;
loaded real data on dashboard, users, reviews, org, succession, analytics, JD, billing,
nudges (shapes match the typed client). **3 real mutations** verified end-to-end + audit
rows written:
- create user → appears in list + `admin.user_created` audit row;
- approve a PENDING review (HITL gate, as the manager) → `state=APPROVED`, `human_reviewer`
  set + `review.approved` audit row;
- reassign reporting line (as HRBP) → manager changed + `reporting_line.reassigned` audit row.
- RBAC held: succession `→ 404` for an employee.
Backend suite **1050 passed**; frontend `tsc`+`lint`+`build` clean.

## Phase 2 — Real-data gaps
The live wiring exposed only **frontend-side** mismatches (login, reassign, timeline,
positions gating) — all fixed inline in Phase 1c (exactly what the contract anticipated).
**No backend gap required a change**: every Admin-Hub screen renders real data without an
unhandled state; reads match the serializers; RBAC/scope/tenant isolation intact. One minor
note for later (not a blocker): the review **list** serializer omits `approval_route` (the
detail/route-tracker UI already guards for it). No separate Phase 2 commit was needed.

## Phase 3 — AI alive on Groq ✅ (commit `8aca626`, pushed)

**3a/3b.** Added `langgraph` + `langsmith` to `requirements.txt` (image rebuilt clean;
node sequences keep running through the in-repo `run_graph` faithful runner — the
LangGraph `StateGraph` swap was left as-is per `NEEDS_HARI_llm_provider.md`, noted below).
Implemented **`apps/ai/groq.py::GroqProvider`** behind the existing `LLMProvider` ABC
(OpenAI-compatible Chat Completions via `requests`, JSON mode, per-agent system prompts
pinning each agent's exact output shape). Wired:
- a **two-model strategy** as a setting (`settings.LLM_MODEL_MAP`): `llama-3.3-70b-versatile`
  for human-read agents (review/feedback/succession/jd/career), `llama-3.1-8b-instant` for
  chat — trivially re-tunable per agent;
- a **global run ceiling** (`LLM_MAX_CALLS=60`, cache-counted across web+celery) + bounded
  `max_tokens` + **429 backoff** (honours `Retry-After`) to protect the free tier;
- the agent **seams** (`REVIEW/FEEDBACK/JD/SUCCESSION/CAREER` providers) point at the real
  LangGraph agents in `base.py`; each delegates `configured` to the gateway, so an unset key
  still yields a clean **503** (and tests pin them off — hermetic).
- `llm_configured()` is **True** in the running stack. **[live]**

**3c. Proven on REAL Groq output, one agent at a time [live]:**
- **Agent 1 (Review Assistant):** `POST /api/reviews/<id>/request-ai-draft` → real 5-section
  draft from llama-3.3-70b, `state=PENDING_HUMAN_REVIEW`, `source=AI`, confidence 0.88, real
  citations (goal + cycle_score t_score=49.2070), TokenLedger row (562 tok). HITL-locked.
- **Chat (8B):** in-scope read → real answer + data; "approve & finalize…" → **blocked**
  (read-only); cross-tenant person → "No matching person in your scope" (RBAC/tenant
  isolation held).
- **Agent 4 (Succession enrich):** `POST /api/succession/plans/<id>/enrich` → a **new**
  `source=AI` plan PENDING (deterministic plan untouched), real Groq narrative, confidence
  0.88, agent4 TokenLedger row (448 tok).
- **Key-unset → 503** fallback verified (GroqProvider.configured=False when keyless). **[build]**

**3d. AI visible in the UI:** the live frontend (mocks off) now renders these real flows —
the review AI-draft produces a real draft inline with its confidence + PENDING banner; the
chat panel returns real answers; the KPI-nudges tile shows real Agent-2 nudges. With the key
present the 503 states are replaced by the working flow; with it unset they degrade gracefully.

Backend suite **1050 passed** after the AI wiring (the 5 "default-provider-not-configured"
seam tests were kept green by pinning the seams to NotConfigured in `test.py`).

---

## Phase 4 — Deepen the PMS
**Not started** — stopped here to keep a deep, working, verified subset (priorities 1 & 2)
committed, pushed, and running, rather than start broad changes I might not finish cleanly.
The dashboards, review-cycle workflow, goals/KPIs, 360, succession, and analytics screens
all already render real data and the AI is alive behind them; Phase 4 is depth/polish on top.

## NEEDS_HARI / BLOCKER files
- No new BLOCKER files. The four pre-existing `NEEDS_HARI_*.md` remain (llm_provider is now
  largely actioned — Groq is wired and live; the optional LangGraph `StateGraph` swap and a
  LangSmith key are the only remaining items there).

## How to run the whole thing
```bash
# from the repo root, with the gitignored .env present (holds GROQ_API_KEY)
docker compose up -d --build              # MySQL+Redis+Django+Celery+frontend(nginx)
docker compose run --rm web python manage.py seed_demo   # idempotent demo data
# open http://localhost:8080  → log in: tenant "acme", admin@acme.test / Passw0rd!demo
docker compose run --rm web pytest -q     # 1050 backend tests
```
- AI on/off: with `GROQ_API_KEY` in `.env` the agents run on Groq; remove it and they
  degrade to the graceful 503 path (no crash, no fabrication).
- Flip the frontend back to standalone mocks: rebuild with `--build-arg VITE_USE_MOCKS=true`.

## What remains / recommended next steps
1. **Phase 4 depth** (the cockpit dashboards, the guided review-cycle workflow, living
   goals/KPIs, 360 end-to-end, succession-as-HRBP-tool, analytics charts).
2. **AI UI polish:** JD "Generate with AI" needs an inputs form first (the seam 422s without
   saved inputs — proven, not a payload bug); succession "Enrich" should switch the panel to
   the new AI plan it creates; surface the TokenLedger/budget usage in the billing screen.
3. **Provider hardening:** optional real LangGraph `StateGraph` swap + a LangSmith key for
   tracing; tune the confidence heuristic; per-tenant budget tuning for production tiers.
4. **The mobile-web self-service surface** (separate build) + a QA sweep.

## Commit + push list (this run, on `origin/main`)
- `570aec7` Make-it-real Phase 1 — one running stack + demo seed + live wiring  *(also carried
  the 10 prior local-only frontend-build commits to origin)*
- `8aca626` Make-it-real Phase 3 — AI alive on Groq
- (this commit) Make-it-real — morning report

Tree clean; stack running.
