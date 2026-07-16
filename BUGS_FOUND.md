# BUGS_FOUND — manual test pass (MYTEST.md) root-cause + severity ranking

Source of truth: `MYTEST.md` (Admin / HRBP / Manager / Employee pass). Investigated on branch
`hari/agent-ui-v2` against the live stack (PMS served at **http://localhost:8090**; `:8080` is held by an
unrelated `conduit-api-1` container). **Report first — fixes applied after, in severity order, one commit
each, no RBAC/HITL/tenant/audit gate weakened.**

## Ranked summary

| # | Sev | Area | Bug | Root cause (verified) | Status |
|---|-----|------|-----|-----------------------|--------|
| 1 | **P0** | Security | Agent could delete data | **Cannot happen** — no delete action in registry; verified live | Confirmed safe (+ add explicit refusal) |
| 2 | **P0** | Correctness | Ada (Manager) logs in as EMPLOYEE | Seed `_user` never reconciles **role** for an existing account | Root-caused |
| 3 | **P0** | Correctness | HRBP/Manager see "You don't have access" on landing | Role bug (#2) + `RoleGate` denies while `me` loads / gated `from` | Root-caused |
| 4 | **P1** | UX/data | Writes don't reflect until reopen (review finalize, 360 open, approval reject) | Mutations don't invalidate React Query cache | Agent mapping sites |
| 5 | **P1** | Crash | HRBP JD generation "crash" | Backend verified working end-to-end; frontend/env | Backend clean |
| 6 | **P1** | Crash | Admin screens "crash" | Backend clean; dead `/admin/integrations` nav route (no page) | Root-caused |
| 7 | **P2** | Agent | Agent "dumb": no memory, wrong answers | Plan-act V2 IS served (verified all roles); the **read/Q&A path** is thin + misroutes + no memory | Root-caused |
| 8 | **P2** | Dashboards | HRBP/Admin dashboards huge; KPI-nudges repeat same person ×N | Nudges not deduped per person | Agent mapping |
| 9 | **P2** | Dashboards | Dead links — list rows don't open the record | Cards render text, not links | Agent mapping |
| 10 | **P2** | Top bar | Star "Ask AI" and "?" help both open the same chat | Both wired to `chat.toggle` | Agent mapping |
| 11 | **P2** | Top bar | AI panel is blocking (modal) | shadcn `<Sheet>` (Radix Dialog) modal + overlay + focus trap | Confirmed |
| 12 | **P2** | Notifications | HRBP badge shows "1" but approvals inbox empty | Count source ≠ inbox list | Agent mapping |
| 13 | **P3** | Verify/cut | "Check with AI" flags — no re-check after edit | One-shot; no re-run affordance | Root-caused |
| 14 | **P3** | Verify/cut | Tenant config (raw JSON) looks pointless | Real per-tenant settings bag; needs labeling | Root-caused |
| 15 | **P3** | Product | Entitlements: only tenant-wide seats, no per-person tiers | **By design** (`Entitlement` = one row/tenant) | Flag for you (no invent) |
| 16 | **P3** | Verify/cut | Integrations (Jira/Slack) look broken | No admin Integrations page (dead route, see #6) | Root-caused |

---

## P0-1 — Destructive agent action: NOT reachable (verified) ✅
**Verdict: deletion is not a registered agent action and cannot be reached by anyone.**
- Registry `apps/ai/actions.py:934–1057` has 14 actions — none is delete/destroy/remove/purge.
- `execute_action` (`actions.py:1110–1117`): `spec = ACTIONS.get(action); if spec is None or "execute"
  not in spec: raise ValidationError`. Forged names (`delete_all`, `bulk_delete`, `purge`) → rejected.
- Planner drops unknown actions (`planner.py:112–133`). Live: "delete all the data"/"delete everyone" →
  **0-step plan**; single path refuses. "delete" appears only as a *write-intent keyword* (`chat.py:25`).
- **Proposed fix (hardening only):** add an explicit destructive-verb refusal in `chat_answer` so the
  agent *says* "I can't delete data" instead of returning an empty plan. No gate touched (nothing to
  remove — deletion is already absent).

## P0-2 — Ada (Manager) treated as EMPLOYEE 🔴
**Root cause:** `apps/core/management/commands/seed_demo_rich.py::_user` (lines 152–171) updates only
`manager` and `display_name` for an **existing** account — it **never reconciles `role`**. Both seeds
*intend* `ada` = MANAGER (`seed_demo.py:117`, `seed_demo_rich._people`), but once ada's role diverges
(an admin role-change, or an earlier state), a reseed **cannot** restore it. Live: `ada@acme.test` role
= EMPLOYEE with 14 reports; `/me` returns EMPLOYEE → employee nav + "You don't have access".
> Note: my own prior bug-3 probe flipped `ada`→EMPLOYEE via `POST /admin/users/<id>/role` and didn't
> restore it — which is exactly the fragility this bug describes (a role change sticks through reseeds).
* **File/line:** `apps/core/management/commands/seed_demo_rich.py:152–171`.
* **Proposed fix:** in `_user`, also reconcile `role` (append to `fields` + save) so the seed is
  idempotent on role and self-heals. Reseed to restore ada→MANAGER. (RBAC unchanged — this only makes
  the demo accounts match their intended roles.)

## P0-3 — "You don't have access" on landing (HRBP/Manager) 🔴
**Root cause (two compounding):** (a) the role bug above — a Manager stuck as EMPLOYEE lands with
employee nav and is denied manager areas; (b) `frontend/src/app/guards.tsx::RoleGate` returns
`NotPermitted` whenever `me` is falsy or rank < min — with no loading state of its own — so a stale/
still-resolving role, or a post-login redirect to a `from` route the role can't see, flashes the 403.
* **File/line:** `frontend/src/app/guards.tsx:42–45`; `frontend/src/features/auth/LoginPage.tsx:37,60`.
* **Proposed fix:** fix P0-2 (roles) first; then harden `RoleGate` to render a loader while `me` is
  loading, and clamp the post-login redirect so a role-forbidden `from` falls back to `/` (dashboard,
  visible to every role). Verify in-browser at :8090 per role. (No server gate changed — server RBAC
  still enforces; this is display correctness.)

## P1-4 — Writes don't reflect in UI until reopen 🟠  *(NOT the shared cause first assumed)*
**Correction after investigation:** it is **not** a blanket missing-invalidation. Two of the three
already invalidate correctly in the current tree; only one genuinely reproduces.
- **Review Finalize** (`reviews/useReviews.ts:83`, `refresh` at `:72-76`) invalidates
  `["reviews","detail",id]`+timeline+list; `ReviewDetailPage` reads the live `useReview` detail →
  already refetches in place. **No fix needed** (the user saw this on the *pre-rebuild* bundle).
- **Approval reject** (`approvals/useApprovals.ts:36-40`, `invalidate` at `:26-29`) invalidates
  `["approvals","route",routeId]`+inbox; `RouteSheet` reads the live `useRoute` → **already correct**.
- **360 "Open for collection" — the REAL bug.** `feedback/useFeedback.ts:73-76` DOES invalidate
  `["feedback"]`, but `CycleSheet`/`CycleBody` derive state from the **`cycle` PROP snapshot**
  (`CycleSheet.tsx:66-68` `isDraft = cycle.status === "DRAFT"`), and the parent passes a captured
  `useState` object (`FeedbackPage.tsx:183,210,218`). There is no single-cycle detail query, so the open
  sheet keeps the stale `DRAFT` snapshot until close/reopen. Adding invalidation is a no-op.
* **Root cause:** stale prop snapshot in the feedback Cycle sheet (the lone screen not following the
  app's "parent holds id, child reads a live query" convention used by `RouteSheet`/`ReviewDetailPage`).
* **File/line:** `frontend/src/features/feedback/FeedbackPage.tsx:183,210,218` + `CycleSheet.tsx:37,66-68`.
* **Proposed fix:** store only `selectedId` in the parent and derive `selected` from the live
  `useCycles` list (already invalidated by `openCycle`), so the sheet reflects Collecting immediately.
  (Also re-verify finalize/reject live in-browser on the rebuilt bundle.)

## P1-5 / P1-6 — JD generation & Admin "crashes" 🟠
- **JD (HRBP):** backend verified working end-to-end (login→create→save-inputs→generate `202`→job
  **SUCCEEDED**, JD `PENDING_HUMAN_REVIEW`); no 500/traceback. The "crash" is frontend/env — to confirm
  in-browser at :8090 (`frontend/src/features/jd/JdDetailPage.tsx` generate dialog). Backend not at fault.
- **Admin:** every admin endpoint + role mutation returns 200, no traceback. Likely cause: **dead nav
  route** — `nav.ts:95` links `/admin/integrations` but `router.tsx` defines no such route/page.
* **Proposed fix:** confirm the JD screen error in-browser; add/remove the `/admin/integrations` route.

## P2-7 — Agent dumb / no memory 🟡
**Root cause:** the served build **is** agent-V2 (plan→per-step approve) — verified live for **Admin**
("approve all goals"→confirm step; "start a 360…"→plan) and it's the V3 `ChatPanel` bundle. The
perceived dumbness is the **read/Q&A path** in `apps/ai/agents/chat.py`: it only knows goals + latest
score, **misroutes** "how many reviews" to a goals answer ("you have no goals on record"), and carries
**no session memory** on reads. So the user's hypothesis (old read-only build served) is not the cause.
* **Proposed fix (bounded, safe):** stop misrouting (answer review-count/read questions correctly within
  RBAC scope) and thread session memory into the read path; keep the delete refusal. A *full* reasoning
  agent is a larger feature — flagged for you (see PROGRESS_NIGHT). No scope/gate widened.

## P2-8/9/10/11/12 — Dashboards + top bar + badge 🟡
- **8 nudges dupes / 9 dead links / 10 duplicate Ask-AI+help / 12 phantom badge:** exact file:line +
  fixes being finalized by the frontend investigation; approach: dedupe nudges to one row/person (latest)
  + top-N + "view all"; make every dashboard row a link to its record's route; drop the redundant top-bar
  trigger; make the badge count the same query the inbox lists.
- **11 blocking panel — CONFIRMED:** `ChatPanel.tsx:116` mounts the panel in a modal shadcn `<Sheet>`;
  `components/ui/sheet.tsx:52–53` renders `<SheetPortal><SheetOverlay/>` (full-screen overlay + focus
  trap). Fix: non-modal Sheet (`modal={false}`, no overlay) or a docked side-panel in the layout.

## P3-13/14/15/16 — verify-or-cut
- **13 Check-with-AI recheck:** flags are one-shot; add a "re-check" after editing (or make the flow
  explicit). `frontend/src/features/reviews/ReviewDetailPage.tsx`.
- **14 Tenant config:** it's a real per-tenant settings JSON bag (`administration/views.py:182–206`);
  needs a friendlier label/hint, not removal.
- **15 Entitlements per-person: BY DESIGN** — `Entitlement` is one row per tenant (`billing/models.py:28–37`,
  `UniqueConstraint`). Per-person/per-group tiers would be a new feature + product decision. **Flagging
  for your call — not inventing it.**
- **16 Integrations:** no admin Integrations page exists (the dead `/admin/integrations` route, #6);
  label the surface honestly as "not connected" or hide until built.

---
*Fixes proceed P0→P1→P2→P3 below; each committed separately with tests kept green. Progress + retest
checklist in `PROGRESS_NIGHT.md`.*
