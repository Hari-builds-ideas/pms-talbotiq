# V1 Handoff Report (RUN 2 — real redesign)

**Task:** execute the updated `V1_MASTER.md` (A→E→B→C→D) — a **real** Goals/OKR redesign (the earlier
tag-only attempt was rejected), remove the T-score from the v1 UI, wire Gemini, polish, prepare the free
deploy, and update the handoff docs. **Status: DONE, verified green.** I've tried not to overclaim — the
"Honesty / partials" section below lists what is prepared-but-not-live and every judgement call.

Branch `hari/agent-ui-v2`. RUN 2 commits (oldest → newest):

| Commit | What |
|---|---|
| `87b341a` | **Goals screen rebuilt** — %+colored bar per goal, details hidden (+ `GOALS_RESEARCH.md`, `goalProgress.ts`, `V1_HIDE_TSCORE`) |
| `4a8762e` | T-score removed from person profile + employee cockpit; shared `ProgressBar`; `TrendChart` `seriesName` |
| `6dc6e78` | T-score removed from analytics, manager dashboard, review evidence |
| `3253d5f` | 7 unit tests for `goalProgress` |
| `57e17e1` | PROGRESS_V1 — Phase A log |
| `f5e9c88` | **Gemini** best/fast model split + `.env.example` key placeholder |
| `371e9a3` | Deploy files updated for Gemini (render.yaml + DEPLOY_DEMO) |
| `65b8693` | Handoff docs updated (V1_VS_V2 / SYSTEM_OVERVIEW / HOW_IT_WAS_BUILT) |
| `1d0d1ae` | PROGRESS_V1 — E/B/C/D + QUESTIONS |

**Verified:** `tsc` clean · **125** frontend vitest (118 + 7 new) · **239** backend AI tests · **57/57**
E2E smoke (`demo_ready.sh`) → **DEMO READY**. Reseeded (rich ACME). The running demo at
**http://localhost:8090** was rebuilt + confirmed serving the redesign.

---

## 1. The Goals/OKR screen — honest before / after

**BEFORE (rejected RUN 1):** the same dense screen — per person a T-score number + status badge + weight
badges; each goal card showed a "Goal weight N" badge and a raw KPI list (weight · target · direction ·
progress) always expanded. The only "simplification" was a status word added on top. A non-expert still
saw statistics and jargon first.

**AFTER (this run):** copied the pattern real tools use (Lattice / 15Five / Betterworks — see
`docs/GOALS_RESEARCH.md`). Per goal, the first thing you see is:
- the **goal title** in plain words,
- a big **% complete** (e.g. "72%"),
- a **colored progress bar** — green (on track) / amber (behind) / red (at risk),
- a one-word **status**.

Above each person's goals: **"3 of 4 goals on track — 68% overall."** Everything technical — weight
("How much this counts"), target ("Goal"), the KPI breakdown, direction ("Higher/Lower is better"),
the progress timeline, and the Approve button — is now **hidden behind "Show details."** A manager who
has never seen the product knows who's on track in ten seconds without opening anything.

The % is computed in `frontend/src/lib/goalProgress.ts` to mirror the backend scoring engine
(direction-aware KPI attainment, weight-blended), so the number is honest, not invented. **No backend or
data-model change** — KPIs, weights, targets, and the create / record-progress / approve flows are all
unchanged, just relocated.

---

## 2. What was REMOVED vs KEPT

**Removed from the v1 UI — the T-score number, everywhere** (person profile, employee cockpit, analytics
individual trend + table, analytics department mean/median, manager dashboard avg-score card + big number
+ team column, review evidence). v1 shows plain **goal progress % + status** in each spot instead. All of
it is guarded by one flag, **`V1_HIDE_TSCORE` in `frontend/src/app/v1.ts`** — set it to `false` and the
T-score numbers come back. **The backend is untouched**: `CycleScore.t_score` and the scoring engine still
compute and store it; only the UI stops printing it.

**Kept (still hidden from RUN 1, code intact):** nine-box / calibration, succession, career roadmaps,
raw-JSON tenant config — all one edit to `app/v1.ts` to restore (see `docs/handoff/V1_VS_V2.md`).

**Kept & working, untouched:** reviews (+ AI draft, HITL), 360 feedback, approvals, check-ins,
recognition, org chart, JD library, audit log, admin users/entitlements, and the whole AI agent
(plan→approve) flow.

**One re-enable caveat (not overclaiming):** flipping `V1_HIDE_TSCORE` restores every T-score number
**except** the profile + analytics **trend charts**, which plot progress % in v1 — reverting those two
charts to a T-score series is a one-line data-source swap, documented in the code and in `V1_VS_V2.md`.

---

## 3. Gemini — how you paste the key (your only action)

The Gemini provider is wired as the configured provider, with a **two-model split**: `gemini-2.5-pro` for
the human-read agents (review / JD / feedback / succession / career) and `gemini-2.5-flash` for chat —
both env-overridable. OpenAI and Groq remain switchable by config.

**Your whole action — paste the key, restart:**
1. In `.env` (gitignored — never commit), the block is already scaffolded (see `.env.example`):
   ```
   LLM_PROVIDER=apps.ai.gemini_provider.GeminiProvider
   GEMINI_API_KEY=your-gemini-key-here      ← paste the enterprise key here
   ```
2. Restart: `docker compose restart web celery-worker`.
3. **Verify (one command):**
   ```
   docker compose run --rm web python manage.py shell -c "from apps.ai.providers import get_llm_provider; p=get_llm_provider(); print(type(p).__name__, 'configured=', p.configured)"
   # → GeminiProvider configured= True
   ```
   Then in the app: **Ask AI → "draft a review for <a report>"** → approve the step → the draft returns
   (lands PENDING for human review). No key → a clean 503, never a fake.

To force the cheap model everywhere on a tight free tier: set `GEMINI_MODEL=gemini-2.5-flash`.

---

## 4. Deploy click-through (free demo — nothing deployed on your behalf)

Full detail: **`DEPLOY_DEMO.md`**. In brief:
1. **Render** → New → Blueprint → this repo (`render.yaml` builds web + free Redis + MySQL). Set
   `DJANGO_ALLOWED_HOSTS` + `DJANGO_CSRF_TRUSTED_ORIGINS`, and **paste `GEMINI_API_KEY`** (the only
   hand-entered secret; `sync:false`, never in git).
2. **Vercel** → New Project → this repo. Edit the `/api` rewrite host in `vercel.json` to your Render
   `*.onrender.com`. Deploy.
3. Open the Vercel URL (first hit cold-starts ~30–60s — the free web service sleeps).

Free-tier tradeoffs documented honestly in `DEPLOY_DEMO.md` (ephemeral MySQL that reseeds on boot, eager
Celery, single Redis, model override for rate limits). The path to real production is
`docs/handoff/DEPLOYMENT.md` Part 2.

---

## 5. Your testing checklist (run when you have time)

**Automated (green as of this run):**
- [ ] `cd frontend && npx tsc --noEmit && npm test` → tsc clean + **125** passing. *(Run from `frontend/`
      — a stray repo-root vitest config falsely shows 2 failures.)*
- [ ] `docker compose run --rm web pytest apps/ai -q` → **239 passed, 5 deselected**.
- [ ] `BASE=http://localhost:8090 ./scripts/demo_ready.sh` → **57/57 · DEMO READY**.

**Manual — the Goals redesign (open http://localhost:8090, ~10 min):**
- [ ] **Goals** — each goal leads with a big **%** + a **colored bar** + a one-word status; person line
      reads "N of M goals on track — X% overall". **No T-score anywhere.**
- [ ] Click **Show details** on a goal → weight ("How much this counts"), Goal (target), KPIs, direction,
      timeline, and Approve appear; collapse hides them again.
- [ ] Record a KPI progress value (as the owner) → the bar/% update.
- [ ] **Profile** (People → someone), **Employee dashboard**, **Analytics**, **Manager dashboard**,
      **a Review's Evidence panel** → confirm none show a T-score number; each shows progress %/status.
- [ ] **Analytics** → individual trend is "Progress %", department shows On track/Behind/At risk (no
      mean/median T-score), no calibration tab.
- [ ] Nav has no Career / Succession / Configure; the 4 roles all still work (reviews, feedback,
      approvals, JD, audit).
- [ ] **Re-enable spot-check (optional):** set `V1_HIDE_TSCORE = false` in `frontend/src/app/v1.ts`,
      rebuild → T-score numbers return; revert.

**Gemini:** the § 3 verify command + Ask-AI draft (needs your key).

---

## 6. Honesty / partials / QUESTIONS

- **Gemini is now LIVE-VERIFIED** (2026-07-11, real key). The agent did hard PMS tasks end-to-end: a
  2-step plan (initiate_360 + draft_review) → approved → a **review drafted by the best model
  `gemini-3.1-pro-preview`** (~20s, grounded prose, landed PENDING/HITL); an injection request planned
  only registered actions and **executed nothing**; reads answered on the fast model. Three fixes the
  live run forced (committed `2370ab2`): (a) `gemini-2.5-pro` is **blocked for new API projects** → best
  default is now `gemini-pro-latest` (`gemini-3.1-pro-preview` also works); (b) Gemini pro models "think",
  so `LLM_MAX_TOKENS` default raised 900→4096; (c) the T-score **leaked in agent TEXT** (chat answer, KPI
  nudges, AI-drafted review prose) — now removed behind the backend `V1_HIDE_TSCORE` flag and re-verified
  (a fresh draft has zero T-score/cohort leaks). **Not exercised live:** JD generation — the only DRAFT
  JD lacks required `inputs` (422), published JDs can't regenerate; not a Gemini fault (same best model
  already proven via the review draft) — flagged for a seed follow-up.
- **Goal status thresholds** (On track ≥70 / Behind 40–69 / At risk <40) are pure-%; real tools also factor
  cycle time elapsed — a v2 refinement (`lib/goalProgress.ts`). A goal with no recorded KPI shows "Not
  started"; an unrecorded KPI on a partly-recorded goal counts as 0 (engine-consistent).
- **Goals "Refresh analytics" button** — the old "Recompute scores" button is kept (manager-only) but
  relabelled; the live bars don't need it. Could move to Analytics later.
- **Raw tenant-config** stays hidden (not rebuilt as friendly toggles) — a v2 build.
- **T-score re-enable caveat** — see § 2 (trend charts don't auto-revert with the flag).
- **The two `V1_HANDOFF_REPORT.md` / handoff docs** were updated in place; the RUN 1 report was replaced
  by this one.

**Bottom line:** the Goals screen is a genuinely different, simpler screen (% + bar, detail hidden) — not
a re-tag — and the T-score is gone from the v1 UI while fully preserved in the backend. Everything is
green, committed per change, and one flag/one key away from where v2 or a live demo needs it.
