# AGENT_ARCHITECTURE — plan → reason → per-step approve

How the chat is a real agent without ever letting the model act on its own. This is the doc to read
before touching `apps/ai/planner.py`, `apps/ai/actions.py`, or `apps/ai/sessions.py`.

## The loop

```
user message
   │
   ▼
POST /api/ai/chat/plan
   │  (records the user turn in the ChatSession — short-term memory)
   ▼
planner.build_plan(user, session, message)
   │  1. gateway.run(agent_code="planner", model="chat"/gpt-4o-mini, schema={steps,summary})
   │       └─ the LLM returns ORDERED action NAMES + a subject hint. Nothing else.
   │  2. for each step (cap 5):
   │       ├─ unknown action?              → drop
   │       ├─ caller lacks capability?     → drop (defense in depth)
   │       ├─ subject is a pronoun/empty?  → resolve from THIS plan / prior turn refs
   │       │                                  (access re-checked)
   │       └─ realize via the SAME _propose_* fn the single-action path uses
   │            → confirm | navigate | clarify   (params resolved in Python, scope-bound)
   │  3. compose a grounded `reason` per step from the real fetched facts
   │  4. persist ChatPlan + ChatPlanStep rows   ← INERT. nothing has executed.
   ▼
assistant turn recorded (with refs to the in-scope objects the plan touched)
   ▼
UI renders the plan as a checklist: [ reason ]  Approve · Skip · Explain
   │
   ▼  (human taps Approve on ONE step)
POST /api/ai/chat/plan/<plan>/step/<step>/approve
   │  planner.approve_step(user, plan, step)
   │    ├─ 403 if not the plan's owner; 404 if missing/cross-tenant
   │    ├─ row-lock the plan; transition PENDING→APPROVED under the lock (→ exactly-once)
   │    ├─ idempotent: an already-done step re-returns its result
   │    ├─ out_of_order flag if earlier steps are still pending (earlier steps NEVER auto-run)
   │    └─ execute_action(user, step.action, step.params)   ← the ONE write path
   │          └─ re-checks capability + object scope on REAL targets, audits, calls the
   │             SAME service the human UI calls
   ▼
step marked done|failed; result (job/audit ids) returned
```

## Where each invariant lives

| Invariant | Enforced in |
|---|---|
| LLM never produces params/permissions | `planner.build_plan` (uses only `action` + `subject` from the model) |
| Params resolved deterministically, scope-bound | the existing `_propose_*` in `apps/ai/actions.py` |
| Capability gate (twice) | `planner._realize_step` (build) + `execute_action` (execute) |
| Plan is inert | `planner._persist_plan` writes rows only; no service calls |
| Exactly-once execution | `approve_step` row-lock + PENDING→APPROVED transition |
| Idempotency | `approve_step` (DONE → re-return result) |
| Object scope on execute | `execute_action` → `actor_can_access` / `get_*_in_scope` (404) |
| Audit every write | the reused services (`audit_record`) |
| Memory is scope-safe | `sessions.resolve_reference` re-checks live access on every ref |
| Ambiguity asks, never guesses | `clarify` proposals bubble up as clarify steps |
| Out-of-scope never revealed | propose returns navigate/None; omission note is generic |

## Why the reason is composed in Python

A model-authored "reason" could hallucinate a fact ("Vera's review is in DRAFT") that isn't true. So
the reason is built in Python from what the propose function ALREADY verified against live rows (the
resolved person, the eligible-DRAFT filter, the pending-approval set). If a step can't be grounded
(propose returned nothing), it's dropped — so every emitted reason is grounded by construction.

## Session memory (short-term)

- `ChatSession` (owner-bound, tenant-scoped, `last_activity`, 24h TTL) + `ChatTurn` (role, text,
  `refs`). `refs` = `[{type,id,label}]` of the in-scope objects a turn grounded in.
- Resolution (`sessions.resolve_reference` / `resolve_person_reference`) walks recent refs newest-first
  and RE-CHECKS access (`actor_can_access` / scoped getters) before returning anything. A ref is a
  memory aid, never an access grant.

## Extending the agent

Add a new action the same way as the existing six: a `_propose_*` (scope-bound param resolution) + an
`_execute_*` (re-checks cap+scope, calls the audited service) + a registry entry + the 4 invariant
tests. The planner picks it up automatically (it only emits registry names). Never let a new action
resolve params from model output, and never skip the execute-time re-check.
