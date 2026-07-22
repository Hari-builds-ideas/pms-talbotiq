# AGENT_INTEL — building a genuinely intelligent assistant

Branch: `hari/agent-intelligence-v2` (branched off `hari/agent-ui-v2`).
Goal: turn the read-only chat assistant from keyword→canned-reply into a reasoning,
memory-aware conversational assistant — WITHOUT ever weakening RBAC/HITL/tenant/audit.
The assistant stays **read-only**; all data flows through existing tenant+RBAC-scoped
queries; the LLM may only phrase/reason over data the caller may already see.

Verify live: http://localhost:8090 (demo login in `docs/TESTING_GUIDE.md`). Reset the
LLM quota counter between heavy probes: `docker compose exec web python -c "from apps.billing import atomic; atomic.reset_window('llm:global:calls')"`.

---

## Increment 1 — data-grounded DIAGNOSIS + TEAM-SCAN  ✅ (committed)

**Problem addressed:** "does he need help?" gave a flat goal list (or lost who "he"
was). No reasoning over the actual cycle/KPI data.

**Built:**
- `apps/ai/insight.py` — scoped, read-only insight layer:
  - `person_facts(caller, target)` — structured facts (cycle status/pace, per-goal
    KPI attainment vs target, review load), gated by `actor_can_access` FIRST.
  - `diagnose_person` — deterministic reasoned answer (headline → weakest-KPI
    reasoning → help verdict). No fabrication: missing signal is stated.
  - `team_risk(caller)` — scan of the caller's OWN reporting subtree only.
- `apps/ai/agents/chat.py` — routing:
  - team-scan intercept (`who's behind / at risk on my team?`) → `_answer_team_risk`,
    gated by `VIEW_TEAM_SCORES`; individual contributors get an honest "no team".
  - per-person diagnosis (`_DIAGNOSE_RE`) → `diagnose_person` (scope re-checked).
  - diagnosis vocabulary added to `_NAME_STOP_WORDS` (so "need/help/track" aren't
    parsed as names) and to the FakeLLM classifier's perf words.
- Tests: `apps/ai/tests/test_chat_diagnosis.py` (5) — reasoning over KPI %, coreference
  ("does she need help?" → the named person), **scope refusal** (report can't diagnose
  a peer), team-scan flags only at-risk reports, IC gets "no team".

**Before → after (live, manager ada):**
- `does he need help?` (after "how is Akhil doing")
  - before: *"Akhil has 2 goal(s): …"* (flat list, ignores the question)
  - after: *"Akhil Menon is on track this cycle and keeping pace… the weakest signal
    is 'Roadmap features delivered' at 90% of target… no extra help looks needed."*
- `who's behind on my team?`
  - before: routed to name search / generic redirect
  - after: *"9 of your 14 team member(s) need attention: Hana O'Brien (At risk, behind
    pace); …"*
- permission probe (employee `is Aarav Rossi at risk?`) → honest refusal, no leak. ✅

**Tests:** 270 passed (AI suite), 0 regressions.

---

## Increment 2 — self-test harness + comparison/aggregation + role-aware help  ✅ (committed)

Built the **self-test harness** first (the "core of the night") and let it drive the
fixes.

**Built:**
- `scripts/agent_intel_suite.py` — a live, multi-role adversarial conversation suite
  (employee/manager/HRBP/admin) with heuristic checks (no-leak, honest-refusal,
  not-canned, not-dead, no-dup-filler). Exit 1 on any failure so it can gate CI.
  First run flagged **2 real gaps**; now **32/32 checks pass**.
- `apps/ai/insight.py`: `team_scan(mode=at_risk|behind|all)`, `team_ranking(best=)`,
  `team_counts` — all scoped to the caller's OWN reporting subtree.
- `apps/ai/agents/chat.py`:
  - **Comparison** intent ("who's doing best/worst") → ranked top/bottom 5 (was a
    DEAD "couldn't find" reply — the harness caught this).
  - **Aggregation** intent ("how many of my reports are behind?") → a COUNT summary
    ("5 on track, 3 at risk, 9 behind pace"), not the full name list.
  - **Team-scan** now distinguishes "at risk" (rating) from "behind" (pace) and
    **caps** the list at 8 with "and N more" (HRBP scan went from 65 names → a
    focused 22-at-risk with a cap).
  - **Role-aware capability** answer — a manager hears about team insight, an
    employee hears "I can only see your own data" (fixes the "same scripted blurb").
- Tests: 4 new in `test_chat_diagnosis.py` (ranking order, count-not-list, at-risk
  excludes behind-only, capability is role-aware). **274 AI tests green.**

**Before → after (live, manager ada):**
- `who is doing best on my team?` — before: *"I couldn't find anyone by that name"*;
  after: *"Your top performers this cycle: 1. Akhil Menon (On track); 2. Mateo
  Santos…"*.
- `how many of my reports are behind?` — before: full 9-name list; after: *"Of your
  14 report(s): 5 on track, 3 at risk, 9 behind pace."*
- `who is at risk?` — before: 65 names (over-broad); after: *"3 of your 14… are at
  risk: Hana O'Brien; Liam Costa; Noah Cohen."*
- `what can you do?` — before: one blurb for everyone; after: role-specific.

---

## Increment 3 — Gemini natural-language phrasing over grounded facts  ✅ (committed)

**Built:** `insight.llm_phrase(tenant_id, query, facts, draft)` — rephrases the
already-correct, in-scope deterministic diagnosis draft in natural language, grounded
ONLY in the facts we hand it (strict "never invent / never mention anyone else"
prompt, separate agent code `chat_phrase`). Falls back to the draft on ANY
error/no-key/disabled, so it can only improve wording, never correctness or safety.
Flag: `AGENT_INTEL_LLM_PHRASING` (default on). Wired into the diagnosis route in
chat.py. Tests: phrasing-used-when-model-answers, disabled→grounded-draft. First
`docs/AGENT_INTEL/REPORT.md` written.

**Before → after (live Gemini):** "does he need help?" → *"Akhil Menon is currently
on track and keeping pace… his 'Roadmap features delivered' KPI is at 90% of target,
the only area slightly below expectations. Overall, Akhil does not appear to need
additional help."* — natural + reasoned + grounded (90% matches the real KPI). Harness
32/32; **276 AI tests** green.

---

## Increment 4 — name-typo tolerance (scope-safe) + harness growth  ✅ (committed)

**Built:** `insight.fuzzy_name_suggestions(caller, name_text)` — difflib close-match
(cutoff 0.8) over the caller's IN-SCOPE people only (EMPLOYEE→none, MANAGER→subtree,
HRBP/ADMIN→tenant capped), access re-checked. Wired into chat.py's "couldn't find"
branch: a typo now yields *"I couldn't find that exact name — did you mean Akhil
Menon?"* instead of a dead end — but NEVER suggests a name the caller couldn't see
(an employee mistyping a peer gets the plain not-found, no leak). Harness grew to 34
checks (added a manager typo + a very-long rambling input); all pass.

**Before → after:** "how is Anastaesia doing?" (manager, report "Anastasia") →
*"…did you mean Anastasia?"* (was: "couldn't find anyone by that name"). Employee
mistyping a peer → still "couldn't find", no name revealed. **278 AI tests** green
(2 new in `test_chat_typo.py`).

---

## RESUME HERE → Increment 5

Next cycle, in priority order:
1. **Migrate "how is X" status** to the reasoned+phrased answer (STILL the flat
   "has N goal(s): …" template — confirmed in live smoke). Route status queries
   through `diagnose_person` + `llm_phrase`; keep an explicit "show/list my goals" →
   flat list. This WILL change several summary tests in `test_chat.py` /
   `test_chat_memory.py` that assert "has N goal(s):" — update them intentionally to
   the reasoned shape while keeping the name + scope assertions. Do this as its own
   focused increment (it's the biggest test-churn item).
2. **"what about the other one"** after a disambiguation — remember the offered set
   on the session, resolve "the other/first/second one".
3. **Two-named-people comparison** ("how are Akhil and Mei doing?") — resolve both
   in scope, diagnose each briefly.
4. Grow harness: topic-switch-then-refer-back, multi-person, "the other one".

Known weaknesses: status "how is X" still templated (diagnosis + team intents ARE
reasoned/phrased); no "the other one"; no two-person compare.

To re-run the harness: `python scripts/agent_intel_suite.py` (server on :8090, seeded).
