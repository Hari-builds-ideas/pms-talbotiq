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

## RESUME HERE → Increment 3

Next cycle, in priority order:
1. **Gemini phrasing layer.** `insight.person_facts` → strong system prompt + ONLY
   the permitted facts → Gemini writes the natural-language answer (reason, don't
   template). Deterministic `diagnose_person` string is the fallback on any model
   error/no-key. LLM must NEVER add data beyond `person_facts`. Guard with a
   settings flag (`AGENT_INTEL_LLM_PHRASING`, default on when a key is present) +
   a FakeLLM test that the fallback path stays grounded + a live smoke.
2. **Migrate "how is X" status** to the reasoned diagnosis (still the flat goal
   summary today). Update the affected summary tests intentionally.
3. **Expand the harness**: name typos ("Akil Menon"), "what about the other one"
   after a disambiguation, topic-switch-then-refer-back, very-long input, multi-
   person ("how are Akhil and Mei doing"), comparison across two named people.
4. First **docs/AGENT_INTEL/REPORT.md** milestone write-up.

Known weaknesses to attack: status "how is X" not yet reasoned; no LLM phrasing yet
(answers grounded but templated); no typo tolerance on names; no two-named-people
comparison.

To re-run the harness: `python scripts/agent_intel_suite.py` (server on :8090, seeded).
