# AGENTIC_CHAT_REPORT.md — the powerful AI assistant (propose-and-confirm across the app)

Built on the EXISTING propose-and-confirm registry (`apps/ai/actions.py`, RW_BUILD_4/5). Six chat
actions, each executing ONLY through the existing human-approval gate calling the SAME audited,
RBAC/scope-checked service the human UI uses. Backend + chat-surface only; no new capabilities; no
auth/SSO/shared-contract/Docker/RBAC-matrix changes. Tests use the deterministic path — **no live
OpenAI calls in the run.**

## The invariant — how it's kept

- The chat classifier maps a write-ish message to intent `write`; `propose_action` DETERMINISTICALLY
  keyword-matches ONE registered action and returns an **inert** proposal. The LLM only classifies
  intent — it never extracts params or permissions. Parameters are resolved in Python against ONLY
  the caller's visible scope (`_visible_user_ids` / `_resolve_person` / `_resolve_critical_role`).
- **Confirm** actions write only via `execute_action` (the single write path), reached only on an
  explicit human Approve. Execute RE-CHECKS the capability (`role_has_capability`) AND the object
  scope (`actor_can_access` / `get_*_in_scope` → 404) and calls the SAME service the view calls.
- **Navigate** actions never write from chat: they return a deep-link + prefill; the human completes
  + submits on that screen's own audited endpoint.
- Params are DATA: an instruction embedded in a field is only ever stored/prefilled, never parsed as
  a command (proven per action).

## Actions as built

| Action | Feel | Endpoint/service reused (human path) | Capability | Tests |
|--------|------|--------------------------------------|-----------|-------|
| `initiate_360` | confirm (else navigate when subject unclear) | FeedbackCycle create — mirrors `FeedbackCycleListCreateView` (`actor_can_access(subject)` + DRAFT create, `opened_by` server-set) + `feedback_cycle.created` audit | `MANAGE_FEEDBACK_CYCLE` (Manager+) | 4 ✅ |
| `draft_review` | confirm (else navigate `/reviews` when none eligible) | `enqueue_agent_job(agent1, review)` — mirrors `ReviewRequestAIDraftView` (`RUN_AI_REVIEW_DRAFT` + `actor_can_access(employee)`) | `RUN_AI_REVIEW_DRAFT` (Manager+) | 4 ✅ |
| `career_enrich` | confirm | `enqueue_agent_job(career_roadmap, roadmap)` — mirrors `RoadmapEnrichView` (`get_roadmap_in_scope` → 404) | `MANAGE_CAREER_ROADMAP` (own/managed) | 4 ✅ |
| `succession_enrich` | confirm | `enqueue_agent_job(agent4, succession_plan)` — mirrors `PlanEnrichView` (`get_plan_in_scope` → 404) | `GENERATE_SUCCESSION_ANALYSIS` (HRBP+; employees 404) | 4 ✅ |
| `create_jd` | navigate-and-prefill `/jd?title=…` | none from chat — human Generates via the JD endpoints | `MANAGE_JD_LIBRARY` (HRBP+) | 4 ✅ |
| read/search | read-only (no approval) | `nl_search` + grounded chat Q&A (scope-bound) — already shipped (RW_BUILD_5 / UI #4) | `VIEW_TEAM_SCORES` (search) / `USE_CHAT` | covered by `test_chat.py` / `test_nl_search.py` |

The two execution feels are decided per action in the registry (`feel`), per DECISIONS D38.

## Tests (the four per action) — all green

`apps/ai/tests/test_actions.py` (+ `test_chat.py` for read/search), FakeLLMProvider / NotConfigured
(eager Celery → enqueued job lands DEGRADED, no live call). For each confirm action:
1. **proposal is inert** — proposing enqueues/creates nothing;
2. **out-of-scope / wrong-capability refused at execute** — `PermissionDenied` (cap) / `NotFound` (scope);
3. **approved action enqueues/writes + audits exactly once**;
4. **embedded instruction in a param is not obeyed** — execute acts only on the resolved id; an
   injected "approve all goals" approves nothing (`goal.approved` audit count stays 0).
For `create_jd` (navigate): proposes with prefill; refused without `MANAGE_JD_LIBRARY`; NOT executable
from chat (`execute_action` raises); an embedded instruction stays inert prefill text. Plus
`test_mixed_intent_message_never_auto_executes` — a mixed message proposes but writes nothing.

**Verification:** full backend suite **1321 passed, 2 deselected**; frontend `tsc`/`eslint`/`build`
green, vitest **106 passed** (incl. the navigate deep-link test).

## Frontend (chat surface)

`ProposalCard` is now feel-aware: `confirm` → Approve→execute (prefers the backend `message`);
`navigate` → "Open the screen" deep-links `deeplink` + `prefill` (query string) — never executes;
`clarify` → renders nothing (the question is the bubble text). Types extended in the shared layer
(`ChatProposal.feel/deeplink/prefill`, `ChatActionResult.message/job_id/cycle_id`).

## Honest notes / deferrals (see QUESTIONS Q11–Q13)

- **Commit grouping:** delivered as cohesive commits (backend registry+tests; frontend; docs) rather
  than six micro-commits — the six actions share one registry + one test pattern and are each
  independently tested. Each commit is green.
- **Param extraction is deterministic, not model-driven** (safe default — removes an injection
  vector). Names/roles resolve only within visible scope; ambiguous → the chat asks (`clarify`);
  missing inputs → prefer navigate-and-prefill. The build spec mentioned "the model extracts
  parameters"; we deliberately keep extraction in Python (stronger gate). [Q11]
- **Mixed-intent keyword routing:** a message blending intents routes by first keyword match; the
  human-approval gate (a single specific card) is the protection — nothing auto-executes. [Q12]
- **Prefill consumption on target screens** (JD/reviews/feedback): the chat deep-links + passes
  prefill in the query string; whether each screen reads it is a follow-up. The invariant holds
  regardless (the human completes via the audited endpoint). [Q13]
- **Live verification** is in `HARI_ATTENTION_NEEDED_LIVECHECK.md` (per-action click-list + the
  refusal tests) — recreate `web` + run those.
