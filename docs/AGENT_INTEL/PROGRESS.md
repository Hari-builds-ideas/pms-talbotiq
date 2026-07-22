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

## RESUME HERE → Increment 2

Next cycle, in priority order:
1. **Gemini phrasing layer.** Add `insight.person_facts` → a strong system prompt +
   the permitted facts → Gemini writes the natural-language answer (reason, don't
   template). Deterministic fallback = the current `diagnose_person` string on any
   model error/no-key. LLM must NEVER add data beyond `person_facts`. Add a live
   smoke + a FakeLLM test that the fallback path stays grounded.
2. **Migrate "how is X" status** to the reasoned answer (currently still the flat
   goal summary). Update the affected summary tests.
3. **Distinguish "at risk" vs "behind pace"** in team-scan (right now both are
   listed together); cap long lists with an "and N more".
4. **Comparison + aggregation intents:** "who's doing best/worst on my team",
   "how many of my reports are behind" (a count, not the full list).
5. **Grow the self-test harness** (`scripts/agent_intel_suite.py` — to be created):
   multi-turn conversations per role, pronoun chains, ambiguous names, typos, empty
   /gibberish/very-long input, permission-boundary probes. Run it, triage failures,
   fix+test+log each, expand, repeat.

Known weaknesses to attack: team-scan answer can be very long; "at risk" currently
over-broad; status "how is X" not yet reasoned; no LLM phrasing yet (answers are
templated, if grounded).
