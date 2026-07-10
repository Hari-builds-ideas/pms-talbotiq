# V1 Handoff Report

**Task:** execute `V1_MASTER.md` end-to-end (Phases A→B→C→D) autonomously.
**Status: DONE.** All four phases complete, committed per change, tests green. Nothing is left running or
half-done. This is the one doc to read first; everything it references is real and in the repo.

Branch `hari/agent-ui-v2`. New commits this run (oldest → newest):

| # | Commit | Phase |
|---|---|---|
| 1 | `8c8b2d2` feat(v1): hide career, succession, calibration, raw tenant-config | A |
| 2 | `b5f8ecb` feat(v1): remove succession + career tiles from dashboards | A |
| 3 | `bf547e3` feat(v1): demote T-score behind plain status + 0-100 bar | A |
| 4 | `b3fc97f` feat(v1): plain per-person lead line on Goals | A |
| 5 | `9c75f8f` docs(v1): log Phase A | A |
| 6 | `cd028db` feat(v1): brand-green favicon, meta, consistent login mark | B |
| 7 | `1fd6a9a` feat(deploy): wire Gemini provider + free Vercel/Render demo scaffolding | C |
| 8 | `002eaa5` docs(v1): log Phase B + C | C |
| 9 | `9121039` docs(handoff): complete docs/handoff/ (8 code-grounded docs) | D |

**Iron rules honoured:** no working feature was broken (deferred features are HIDDEN, not deleted — all
code/routes/endpoints/tests retained); real data only (no fabrication); no backend data-model change;
committed per change; free-tier only; no secrets committed; no login to your Vercel/Render accounts.
Every hidden feature has documented one-line re-enable steps.

---

## 1. What changed, by phase

### A — Simplify (make every screen readable in 10 seconds)
- **One central v1 switch:** `frontend/src/app/v1.ts` — product scope, consulted in exactly 4 places
  (nav, ⌘K palette, router, Analytics). Distinct from the billing `hasFeature()` lever.
- **Hidden (code kept):** nine-box/calibration, succession, career roadmaps, raw-JSON tenant config —
  removed from nav, ⌘K, routes (guarded, imports/components retained), dashboards (tiles + queries), and
  the Analytics calibration tab.
- **T-score demoted:** new `frontend/src/components/ScoreBar.tsx` — a plain **On track / At risk / Needs
  attention** badge + a 0–100 bar; the raw T-score is now a small "Score N/100 · 50 = team average"
  caption with a tooltip. Applied to the Employee dashboard card + the profile page.
- **Goals plain-language:** a one-line human lead per person ("On track this cycle · N goals") above the
  OKR detail; the existing Progress/Goal/"Higher is better" relabels remain.
- **Reseeded** ACME (211 people) so every kept screen looks full.

### B — Polish (visual only)
- Favicon replaced (off-brand blue "R" → brand-green **#0d5c3a** sprout mark matching the app icon).
- `index.html`: page title, description meta, `theme-color`, OpenGraph/Twitter tags.
- Login: consistent Sprout brand mark + a v1-accurate tagline (no longer names hidden succession).
- *Placeholder note:* the sprout mark is a clean brand-color placeholder — swap for a final designer asset
  when you have one; it does not block the demo.

### C — Free demo deploy (prepared + documented; nothing deployed on your behalf)
- **Gemini wired:** `apps/ai/gemini_provider.py` (mirrors the OpenAI provider via Gemini's
  OpenAI-compatible endpoint, so the gateway pipeline is unchanged) + 5 unit tests.
- **Deploy files:** `render.yaml` (web + free Redis + MySQL), `vercel.json` (SPA + `/api` proxy → no
  CORS), and **`DEPLOY_DEMO.md`** (the click-by-click).
- **Free-tier realities documented honestly:** eager Celery (no free worker), ephemeral MySQL that
  reseeds on boot, web sleeps (~30–60s cold start), single Redis, Gemini rate limits.
- The Gemini key is the **only** hand-entered secret (pasted in the Render dashboard, `sync:false`).

### D — Handoff docs
- **`docs/handoff/`** — 8 code-grounded docs: `README` (start here) → `SYSTEM_OVERVIEW` → `V1_VS_V2`
  (scope split + re-enable) → `HOW_IT_WAS_BUILT` → `DEVELOPER_SETUP` → `DEPLOYMENT` → `MOBILE` →
  `OPEN_QUESTIONS`. Written for a new engineer inheriting the codebase; every path/command is real.

---

## 2. What was CUT vs KEPT

**Kept & live in v1:** Dashboards (per role), Goals & OKRs (simplified), Reviews (+AI draft, HITL), 360°
Feedback (+AI summary), Check-ins, Recognition, Approvals, Employees/Org chart, JD Library + AI generator,
Analytics (trends + status distribution), Audit log, Admin (Users & Roles, Entitlements).

**Hidden in v1 (NOT deleted — code, routes, endpoints, components, tests all retained):**

| Hidden feature | Re-enable (all in `frontend/src/app/v1.ts`) |
|---|---|
| Career roadmaps | remove `"/career"` from `V1_HIDDEN_PATHS` |
| Succession + nine-box + critical roles | remove `"/succession"` |
| Analytics calibration / nine-box tab | set `V1_HIDE_CALIBRATION = false` |
| Raw-JSON tenant config | remove `"/admin/tenant"` |

After a re-enable: `cd frontend && npm run build`, and restore the old expectations in
`frontend/src/app/nav.test.ts`. Full detail: `docs/handoff/V1_VS_V2.md`.

**Simplified (original detail still present):** T-score → status-first (raw number kept as a caption and
in Analytics tables); Goals → plain lead line (raw weight/target kept on the card).

---

## 3. Deploy instructions (free demo)

Full click-by-click: **`DEPLOY_DEMO.md`**. In brief — nothing here has been run for you; it's one-click:
1. **Render:** New → Blueprint → point at this repo (`render.yaml`). It creates the web service + free
   Redis + MySQL. In the web service env, set `LLM_PROVIDER=apps.ai.gemini_provider.GeminiProvider` and
   **paste your `GEMINI_API_KEY`** (the only hand-entered secret — never in git).
2. **Vercel:** New Project → this repo. In `vercel.json`, replace the placeholder Render hostname in the
   `/api` rewrite with your real `*.onrender.com` host. Deploy.
3. Open the Vercel URL. First hit may cold-start (~30–60s) because the free web service sleeps.

Demo accounts (tenant `acme`, password `Passw0rd!demo`): `admin@acme.test` / `priya@acme.test` (HRBP) /
`ada@acme.test` (Manager) / `akhil@acme.test` (Employee).

Path to real production (durable DB, real Celery worker, secrets manager, always-on + replicas,
observability): `docs/handoff/DEPLOYMENT.md` Part 2 — it's provisioning + config, not a rewrite.

**The running local demo is refreshed:** the `pms-frontend-8090` helper was recreated from the rebuilt
frontend image, so **http://localhost:8090** now shows all A+B changes (verified: 200, brand-green
favicon, updated title/meta).

---

## 4. Testing checklist — run this when you have time

Tests were kept green throughout (I verified after each phase). This is for **you** to confirm.

**Automated (fast):**
- [ ] Frontend: `cd frontend && npx tsc --noEmit && npm test` → expect tsc clean + **118 passing**.
      *(⚠ run from `frontend/`, not the repo root — a stray root vitest config falsely shows 2 failures;
      see OPEN_QUESTIONS.)*
- [ ] Backend AI: `docker compose run --rm web pytest apps/ai -q` → expect **239 passed, 5 deselected**.
- [ ] Full backend: `docker compose run --rm web pytest -q` → expect green.
- [ ] E2E smoke: `./scripts/demo_ready.sh` → expect "✓ DEMO READY".

**Manual (open http://localhost:8090, ~10 min):**
- [ ] **Nav is clean** — no "Career Paths", "Succession", or "Configure" in the sidebar or ⌘K, for any role.
- [ ] **Dashboards** — no succession/coverage/roadmap tiles; the Employee "My performance" card leads with
      a plain status word (not a bare number).
- [ ] **A profile** (People → someone) — leads with the status badge + 0–100 bar; the T-score is a small
      caption with a "50 = team average" tooltip.
- [ ] **Goals** — each person opens with a plain one-line lead ("On track this cycle · N goals"); KPIs read
      Progress / Goal / "Higher is better".
- [ ] **Analytics** — trend + status distribution; **no** calibration/nine-box tab.
- [ ] **Brand** — the browser tab shows the green sprout favicon + "Talbotiq PMS · Admin Hub"; the login
      page shows the sprout mark.
- [ ] **Nothing broke** — log in as each of the 4 roles; Reviews, Feedback, Approvals, JD Library, Audit
      all still work.
- [ ] **Re-enable spot-check (optional)** — in `frontend/src/app/v1.ts` remove `"/succession"`, rebuild,
      confirm Succession returns intact; then revert.

---

## 5. Open questions & mobile state

Full list: `docs/handoff/OPEN_QUESTIONS.md` + the QUESTIONS section of `PROGRESS_V1.md`. The decisions I
made autonomously (and would flag for your call):
- **Goals lead wording** — used the honest "status + goal count" instead of the exact "3 of 4 goals on
  track" (the precise phrasing needs per-goal attainment threaded to the header — small follow-up).
- **T-score demotion scope** — demoted on per-person headline surfaces; kept as a secondary column in the
  Analytics/team tables (expert "insights" screens). Say if you want it demoted there too.
- **Raw tenant config** — hidden rather than rebuilt as friendly toggles (a v2 build).
- **Stray root-level vitest** — running vitest from the repo root shows 2 false failures (wrong config);
  the real suite is green from `frontend/`. Worth removing that root config so no one is misled.

**Mobile (`docs/handoff/MOBILE.md`): deferred to v2 — backend-ready, frontend needs work.** A real Expo
app exists and talks to the live backend using the **same** `@shared` client + types as web (so no
mobile-specific backend work). It has NOT had the v1 simplification or brand pass, has no tests, and isn't
in the demo deploy. v2 = a focused frontend effort (mirror `v1.ts` scope, brand, test), not new backend.

---

**Bottom line:** v1 is a simpler, on-brand, demo-deployable product with a complete handoff — and every
enterprise feature is one line away from returning. Nothing was deleted; nothing was faked; the guards
(tenant isolation, RBAC, HITL, append-only audit, one LLM gateway, no fabrication) are all intact.
