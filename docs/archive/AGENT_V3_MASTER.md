# AGENT_V3_MASTER.md — open-ended intelligence via scoped function-calling

Branch: **hari/agent-intelligence-v2** (checkout; never touch hari/agent-ui-v2 or main). Keep backend +
frontend tests green, commit per working unit, log every unit to `docs/AGENT_V3/PROGRESS.md` with a
"resume here" note. Resume from that file if present.

## Where we are, and what this run adds
Already built and working: company-wide DB person resolution (scales to thousands, exact+fuzzy), a working
multi-step task flow with slot-filling + human approval, conversation memory + reference resolution, and
per-turn permission scoping. Those are DONE — do not regress them.

**What's missing:** the assistant only answers the question shapes we pre-coded. It can't handle
open-ended, compositional questions the developer didn't anticipate — "who improved most since last
cycle?", "summarise my team's biggest risks", "who's ready for promotion?". This run adds that, using the
researched architecture: **a Gemini function-calling agent with a small set of permission-scoped read
tools that the model COMPOSES to answer novel questions**, with all math done in the backend, honest "no
data" behaviour, and the existing human-approval gate preserved for write actions.

## The architecture (implement THIS — from the research, don't invent an alternative)
- **Function-calling, NOT text-to-SQL.** The model never writes SQL and never touches the DB. It calls a
  fixed set of typed tools; our backend runs the scoped ORM query and returns rows.
- **~8–12 mid-grained tools**, one per resource + a few aggregate helpers. Not one giant tool, not 50 tiny
  ones. The model composes them (resolve person → get their cycle scores → get history) to answer
  questions we never explicitly coded.
- **Backend does all math.** Ranking, "who improved most", counts, averages, deltas — computed in Python
  from scoped rows via dedicated aggregate tools. The LLM NEVER does arithmetic on raw rows; it phrases
  the computed result. This is how we prevent invented numbers and bad math.
- **Scope lives in the tools.** Every tool takes the caller's identity from a TRUSTED server-side context
  (not a model-supplied argument), and re-runs the existing permission check on every call. The model
  cannot see or change whose data it may read.
- **Read tools compose freely; write tools stay approval-gated.** The existing recognition/check-in/
  review-draft action flow (plan → human approves → commit) is preserved unchanged. Read/query tools need
  no approval; write/action tools always do.
- **Grounded or honest.** If a tool returns empty or a scope check denies, the model must say "no data" /
  "outside your access" — never fabricate. Structural guard + prompt discipline.

## Execute these build files IN ORDER
1. `A_TOOLS.md` — define the scoped read-tool set (typed schemas, ORM-backed, scope-checked).
2. `B_AGENT_LOOP.md` — the Gemini function-calling loop: compose tools, backend math, grounding guards,
   integrate with existing memory + the approval-gated write actions.
3. `C_OPEN_ENDED.md` — make it answer compositional questions (improvement, ranking, risk, promotion,
   summaries) by composing tools; backend aggregation helpers.
4. `D_EVAL_HARNESS.md` — a question-bank + LLM-as-judge eval that scores grounded-ness and scope-safety,
   runnable in CI, at scale.
5. `E_REPORT.md` — honest report, before/after, eval results, how to test.

## Iron rules
- No hardcoded names or seed-specific cases anywhere. No text-to-SQL. No raw DB access from the model.
- Directory lookup company-wide; DATA access permission-scoped and re-checked in every tool call.
- All aggregation/ranking/math in the backend, never in the LLM.
- Write actions keep the human-approval gate. Read-only stays read-only.
- Never fabricate: empty tool result or denied scope → honest statement.
- Never weaken RBAC/tenant-isolation/HITL/audit. Every unit backed by a test. Commit per unit.
  Resume-safe.

## Definition of done
On a 5,000-person tenant, as different roles, the assistant answers open-ended questions it was never
explicitly coded for — "who improved most", "who's at risk and why", "who's ready for promotion", "compare
my two weakest performers" — by composing scoped tools, with correct backend-computed numbers, honest "no
data"/refusal when appropriate, and the write-action approval gate intact. The eval harness passes for
grounded-ness and scope-safety. All tests green. End with `docs/AGENT_V3/REPORT.md`.
