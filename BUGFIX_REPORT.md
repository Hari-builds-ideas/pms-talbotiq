# BUGFIX_REPORT — product-validation blocking bugs (web)

Four HIGH bugs from a hands-on product validation, fixed in priority order — root-cause
(not patch), each with a test and verified live, committed + pushed per fix. No mobile
work. RBAC / HITL / scope intact throughout; LLM verification used the FakeLLMProvider.

| # | Bug | Commit |
|---|---|---|
| 1 | Goals approve doesn't update state | `1a2849e` |
| 2 | "Request AI Draft" unreachable | `a0bb2b5` |
| 3 | Employee roadmap dead link | `df0d351` |
| 4 | AI assistant ignores intent | `e9f7b53` |

**Suite movement:** backend **1196 → 1201** passing (+5 chat) — and earlier +2 (seed)
from 1194 — net **1194 → 1201**, 2 deselected. Frontend **74 → 76** vitest (+2 goals
invalidation, +2 CareerPage; the goals test file replaced none). tsc / eslint / production
build clean. No regressions.

---

## BUG 1 (HIGH) — Goals approval state doesn't update

**Symptom.** Manager clicks Approve → success toast, but the row stays "Awaiting approval"; repeatable.

**Root cause (frontend, not backend).** The goals list is cached under
`["goals","list", cycle ?? "all"]`, but the post-mutation `refresh()` invalidated
`["goals","list", cycle]`. With **no cycle selected** (the default view) the cached key is
`…"all"` while the invalidation key is `…undefined` — React Query never matches them, so
the list **never refetched** after approve (same latent staleness for create / recordActual /
recompute). The backend was already correct: `GoalApproveView` stamps `approved_by` +
`approved_at` and returns the updated goal.

**Fix.** Invalidate by the stable **prefix** `["goals","list"]` + `["cycles","scores"]`,
which prefix-matches every cached variant — the row flips to "Approved" immediately, and
Recompute/record-actual now refetch too.

**Verified.** **[test]** `frontend/src/features/goals/useGoals.test.tsx` (2) — the default
no-cycle list AND a cycle-specific list are both invalidated after approve (fails pre-fix).
Backend persistence already covered by `test_manager_can_approve_report_goal_and_audit`.
**[live]** created a goal (`approved_by` null) → POST approve → 200 with `approved_by` +
`approved_at` set → GET list refetch shows it populated.

## BUG 2 (HIGH) — "Request AI Draft" not reachable

**Symptom.** A manager could not find any review where AI generation was available.

**Root cause (the seed, not RBAC/feature/UI).** The action only renders on a **DRAFT**
review. RBAC was fine (`RUN_AI_REVIEW_DRAFT` = Manager+), the feature was unlocked
(`acme` = FULL_AI → `agent1`, confirmed live), and the reviews list/detail UI surface
DRAFT rows. But (a) the seeded DRAFT review belonged to a non-demo manager (`employees[1]`
→ `lin`, not the primary demo manager `ada`), so it wasn't in her scope; and (b) `_ensure`
is get-or-create that **never resets state**, so once a tester clicked "Start editing"
(DRAFT → EDITING) the review was permanently non-DRAFT on re-seed. Live: the demo manager
saw **0** DRAFT reviews; the tenant-wide HRBP saw 8, none DRAFT.

**Fix.** `seed_demo._reviews` now seeds a dedicated DRAFT review for one of **ada's**
reports (not used by the spectrum specs) and **force-resets it to DRAFT on every seed**, so
the action is reliably reachable.

**Verified.** **[test]** `apps/core/tests/test_seed_demo.py` (2) — the demo manager reaches
a DRAFT review + `request_ai_draft` fires (→ AI_DRAFTING); a re-seed resets a drifted
(EDITING) review back to DRAFT. The HITL landing (DRAFT → AI_DRAFTING → **PENDING**, never
auto-finalized) and the no-provider loud no-op are already proven by `test_agent1_seam`
with the **FakeLLMProvider**. **[live]** re-seeded → ada sees a DRAFT review (Ella Nyberg,
her report) → `POST /api/reviews/<id>/request-ai-draft` → **202** (reachable + fires); with
no LLM key Agent-1 logs-and-skips (the documented behaviour); re-seeded to leave the demo
with a reachable DRAFT.

## BUG 3 (HIGH) — Employee roadmap access inconsistent (dead link)

**Symptom.** The employee dashboard advertises a Career Roadmap tile; clicking it returned
"You do not have access."

**Root cause (frontend over-gate).** The dashboard's `MyRoadmapTile` (a Panel `to="/career"`)
is shown to employees, but `router.tsx` wrapped `career/*` in `RoleGate min="MANAGER"` (and
the sidebar entry was MANAGER+). The **backend already authorizes it** — `VIEW_CAREER_ROADMAP`
is granted to all roles (OWN scope); live, an employee `GET /api/career/roadmap` → **200**.

**Fix (decision D28: show employees their OWN roadmap, read-only).** Removed the career
`RoleGate`; lowered the sidebar Career entry to `EMPLOYEE`; `CareerPage` gates the "My team"
tab and all manage controls (choose/change target, refresh, AI-enrich, adopt, per-tier
progress edit) behind `atLeast("MANAGER")`. Employees see only "My development" with their
roadmap read-only; the empty state points them to their manager. (Hiding the tile was the
alternative; showing the advertised, server-authorized own-roadmap is the coherent choice.)

**Verified.** **[test]** `frontend/src/features/career/CareerPage.test.tsx` (2) — employee:
no team tab, no target picker, read-only empty copy; manager: full tabs + picker. **[live]**
employee `reza@acme.test` `GET /api/career/roadmap` → 200 (own roadmap, no dead link).

## BUG 4 (HIGH) — AI assistant ignores intent

**Symptom.** Every query ("I feel lonely", "what day is today?", "what can you do?")
returned the same performance-metrics summary.

**Root cause.** `chat_answer` classified intent **binary** (`write` vs `read`); every
non-write query fell through to the grounded goals+score answer → a metrics dump for
everything.

**Fix (decision D29).** Expanded the intent to **`write` | `performance` | `capability` |
`general`** and routed each: `write` → the read-only refusal (**unchanged**);
`performance` → the existing grounded, RBAC-scoped goals + cycle-score answer (`read` kept
as a legacy alias); `capability` → a description of what the assistant does; `general` → a
polite decline + redirect, **never** a metrics dump. Updated the `_CHAT` LLM system prompt;
the `FakeLLMProvider` classifier mirrors it deterministically; the frontend mock chat
handler mirrors the same routing. RBAC-scoping + the write-block are untouched — every
performance fetch still goes through `actor_can_access`.

**Verified.** **[test]** `apps/ai/tests/test_chat.py` +5 (capability + 3 general variants
return no metrics; a grounded performance question still answers with data) — 14 pass.
**[live]** the real `chat_answer` + gateway + **FakeLLMProvider** on the demo DB: "how am I
doing this cycle?" → `performance` + data; "I feel lonely" / "what day is today?" →
`general`, no data; "what can you do?" → `capability`; "approve review 123" → `write`,
blocked.

## Feedback / state-update polish

The "did anything happen?" symptom after **Recompute** and **approval** is resolved by the
BUG 1 prefix-invalidation: both actions already showed a toast ("Scores recomputed" /
"Goal approved"), and now the goals list **and** cycle scores refetch, so the data updates
on screen. No other stale-invalidation sites remained (audited
`invalidateQueries` across the app).

## Verification honesty key
**[test]** asserted by an automated test in the suite · **[live]** exercised over real HTTP
/ the real service on the running stack (LLM paths via FakeLLMProvider, per the no-LLM
constraint) · **[build]** typecheck/lint/production-build only.
