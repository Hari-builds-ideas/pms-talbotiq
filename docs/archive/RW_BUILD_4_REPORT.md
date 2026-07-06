# RW_BUILD_4_REPORT — AI assistant: read-only → propose-and-confirm (HITL)

The headline AI upgrade, kept small and safe. The chat assistant still answers grounded + RBAC-scoped as
before, but a WRITE intent that maps to a SUPPORTED, permitted action now returns an inert **proposal** —
an Approve/Cancel card. **Nothing executes until the human taps Approve**, which runs the action through
the **same audited, permission-checked path a human uses**, re-checked at execution.

Committed, pushed, green, deployed, live-verified.

## The safety contract (all tested + verified live)

- **A proposal is inert.** Proposing approves nothing — only `execute_action` writes, only on the
  explicit Approve tap. (Test: propose leaves every goal unapproved + zero audit rows.)
- **Execute re-checks capability + object scope on the REAL targets.** `approve_goals` mirrors
  `GoalApproveView` exactly: `APPROVE_GOALS` + `actor_can_access(goal.employee)` + the `goal.approved`
  audit + the same stamp. It can never do what the user couldn't do via the normal endpoint;
  out-of-scope / already-approved / missing targets are **skipped**, not approved.
- **Writes + audits exactly once; idempotent.** Re-running an approved action is a no-op.
- **No capability → no proposal AND no execute.** An employee is offered nothing and is refused (403) at
  the endpoint.
- **The LLM never picks or runs the action.** It only classifies the message as a write *intent* (the
  existing gateway classification); the action mapping, target resolution, and execution are
  deterministic and permission-checked.

## What shipped

- **Backend**: `apps/ai/actions.py` — an extensible action registry + `approve_goals` (propose +
  execute). `apps/ai/agents/chat.py` — write intent now tries `propose_action` and returns a proposal
  (else the read-only refusal still holds). `ChatActionExecuteView` → `POST /api/ai/actions/execute`
  (USE_CHAT + chat entitlement, AI-throttled). No new capabilities (reuses USE_CHAT + APPROVE_GOALS).
- **Frontend**: the chat panel renders a proposal as an Approve/Cancel confirm card with a preview of the
  targets; Approve calls `aiApi.executeAction` and invalidates `["goals"]` so an open goals screen
  reflects the approvals; the result ("Approved N goal(s)") shows inline. Types + `executeAction` added
  to the shared layer.

## Verification

- **[test]** `apps/ai/tests/test_actions.py` (6): inert proposal; execute approves + audits exactly once
  + idempotent re-run; out-of-scope target refused at execution; employee gets no proposal + 403 on
  execute; the HTTP endpoint writes once. Existing chat tests still green (a non-actionable write still
  refuses). Backend suite full re-run green; frontend **93** passing, tsc/lint/build clean.
- **[live]** over HTTP: ada chats "approve my team's goals" → `status: proposal` with 1 goal (1 real
  OpenAI call for intent); Approve → execute `200`, `approved: 1`; the goal is stamped by ada with
  exactly 1 `goal.approved` audit row; an employee's execute → `403`.

## Decisions / follow-ups

- **D34**: propose-and-confirm; execution = the human path, re-checked; LLM classifies intent only.
- **Q9**: started with one action behind a registry; more proposable actions (e.g. nudge no-progress
  reports) are a follow-up, each mapping to an existing audited endpoint.

## Your device check (before RW_BUILD_5)

Hard-refresh http://localhost:8080, log in as **`ada@acme.test`** (Manager), open **Ask AI**, and type
*"approve my team's goals"*. You should get a confirm card listing the pending goals with **Approve** /
**Cancel** — tap Approve and the goals approve (the Goals screen reflects it). As **`reza@acme.test`**
(Employee) the assistant stays read-only (no such card). Password `Passw0rd!demo`.

## Next

RW_BUILD_5 — AI quick wins (drafting/proposing helpers via the LLMGateway, all HITL).
