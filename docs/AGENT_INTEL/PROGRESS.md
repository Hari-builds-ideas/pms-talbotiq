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

## Increment 5 — "how is X" status is now reasoned + phrased (FLAGSHIP)  ✅ (committed)

The original complaint is fixed. Any status question about a person now routes
through `diagnose_person` + `llm_phrase` (reasoned over real cycle status + KPI
attainment, natural language) instead of the flat "has N goal(s): …" template. Only
an explicit "show/list my goals" (`_LIST_GOALS_RE`) still returns the raw title list.

**Zero test churn** — existing tests assert on the `data` array (goal titles, which
diagnosis preserves) and negative "goal(s):" checks, so all stayed green. 280 AI
tests (2 new: status-is-reasoned, show-goals-still-flat).

**Before → after (live):** "how is Mei Patel?" — before: *"Mei has 2 goal(s): …;
Latest cycle: On track — behind pace."* → after: *"Mei Patel is currently on track
and keeping pace this cycle… her 'Roadmap features delivered' is at 86% of target,
the primary area to keep an eye on… no additional support appears necessary."*
"show me my goals" → still the flat list.

---

## Increment 6 — two-named-people comparison  ✅ (committed)

**Built:** `_resolve_multiple` (splits on and/vs/comma, resolves each segment in
scope independently) + `_answer_two_people` (diagnoses each, combined reply, optional
phrasing over BOTH people's facts). Fires only when ≥2 DISTINCT in-scope people
resolve, so "goals and KPIs" is untouched and an out-of-scope name is simply excluded
(never a leak). 282 AI tests (2 new); harness 36/36.

**Before → after (live):** "how are Akhil Menon and Mei Patel doing?" → *"Both Akhil
Menon and Mei Patel are on track and keeping pace this cycle. Akhil has delivered 90%
of roadmap features, and Mei is at 86% for the same goal… no immediate additional
support appears needed for either."* Comparing an out-of-scope person → safe
non-answer, no leak.

---

## Increment 7 — "the first/second/other one" after a disambiguation  ✅ (committed)

**Built:** the disambiguation reply now GROUNDS the offered candidates as `user`
refs in a canonical order (`_dedup_sorted_users`), and `sessions.last_offered_people`
returns them (access re-checked). A pre-branch `_ORDINAL_ONE_RE` intercept resolves
"the first/second/third/other/last one" from that set and diagnoses the pick — works
however the short follow-up classifies, fires only when an offered set exists.
283 AI tests (1 new); harness 39/39.

**Before → after (live):** "how is yuki doing?" → "Several people match: … Tell me
which one — you can say 'the first one' …" → "the first one" → *"Yuki Chen is
currently on track, though pace is behind…"* (was: a dead "couldn't find").

---

## RESUME HERE → Increment 8

Next cycle, in priority order:
1. **Comparison polish**: when one of two named people is out of scope, answer the
   in-scope one AND note the other is out of your access (today a mixed pair falls to
   a generic "couldn't find" — safe, not helpful).
2. **Topic-switch-then-refer-back**: after switching people, "go back to the first
   person" / re-referring an earlier-grounded person by role ("my report").
3. Refresh `docs/AGENT_INTEL/REPORT.md` with the comparison + "the other one" rows
   and updated weaknesses.
4. Consider a harness quota note: with phrasing ON each reasoned turn = 2 LLM calls,
   so a full run ≈ 40+ calls; RESET the ceiling before each run
   (`atomic.reset_window('llm:global:calls')`) or raise `LLM_MAX_CALLS` in the
   running container (env-for-testing sets 400 but the live container is on 60).

Known weaknesses: mixed in/out-of-scope comparison → "couldn't find"; no explicit
"go back to X"; harness is LLM-quota-heavy with phrasing on.

To re-run the harness: reset the quota, then `python scripts/agent_intel_suite.py`.
