# PROGRESS_NIGHT — autonomous bug-fix pass (from MYTEST.md / BUGS_FOUND.md)

Branch `hari/agent-ui-v2`. Fixed in severity order, one commit per fix, tests kept green, no
RBAC/HITL/tenant/audit gate weakened. **Retest at → http://localhost:8090** (`:8080` is still held by
your unrelated `conduit-api-1` container; the PMS runs on 8090). Accounts: `admin@ / priya@ / ada@ /
akhil@` · tenant `acme` · `Passw0rd!demo`.

> ⚠️ **Do a hard refresh (Cmd-Shift-R) at :8090** — the frontend image was rebuilt with all UI fixes.

---

## ✅ Fixed (commit + how to retest)

| Bug | What I changed | Retest |
|---|---|---|
| **P0-1 destructive agent** | Deletion is not (and was never) a registered action — verified live (empty plan, forged names rejected). Added an **explicit refusal** so a bulk-delete request says "I can't delete data" instead of a silent empty plan (`chat.py`; +test). | As any role, ask the agent "delete all the data" → clear refusal; no plan, nothing changes. |
| **P0-2 Ada = EMPLOYEE** | Root cause: `_user` in both seeds never reconciled **role** for an existing account, so a diverged role survived every reseed. Now reconciles role; +regression test. Reseeded → ada=MANAGER. | Log in as `ada@` → Manager nav (Reviews/Approvals/Analytics), her dashboard, no "You don't have access". |
| **P0-3 "You don't have access" on landing** | `RoleGate` now shows a loader while auth resolves (no 403 flash) and `landingPathFor()` clamps a role-forbidden post-login redirect back to `/`. | Log in as `priya@` (HRBP) and `ada@` → land on the dashboard, not a 403. Deep-link an admin URL as HRBP, log in → lands on `/`. |
| **P1-4 360 "Open for collection" stale** | The Cycle sheet read status from a captured object snapshot. Now holds only the id and derives the row from the live list (already invalidated by openCycle). Finalize-review & approval-reject **already** invalidate correctly (verified) — no change needed. | Manager: open a 360 cycle → "Open for collection" → status flips to **Collecting immediately** (no reopen). Also re-check Finalize + Approval-reject update live now (they should on the rebuilt bundle). |
| **P1-6 admin dead route** | Removed the `/admin/integrations` nav item (no page existed → it went nowhere). Backend admin endpoints were all verified working (no 500). | Admin → Settings section: no dead "Integrations" link; Users/Configure/Entitlements all load. |
| **P2-8 nudges wall + repeated names** | (a) `_gen_name` repeated full names every 40 people → widened to unique-per-index (now 204/210 unique). (b) `NudgesTile` dedupes per person, sorts worst-first, caps at 5 with "+N more". | HRBP/Admin dashboard: KPI-nudges is short (≤5 + "+N more"), no obvious repeats. |
| **P2-9 dead links (nudges + summaries)** | Nudge rows link to `/people/:id`. FeedbackPage now honours `?tab=` and `?cycle=` deep-links; the "Summaries to release" rows link straight to the release tab / that cycle (no more View-all→cycles→search). | HRBP dashboard: click a "360 for X" summary → lands on the Summaries-to-release tab. Click a nudge → the person. |
| **P2-10 duplicate top-bar chat** | Removed the redundant "?" help button (it opened the same chat as the ⭐ Ask AI). | Top bar: one AI entry (⭐ Ask AI); no duplicate "?". |
| **P2-11 blocking AI panel** | Added an opt-out `overlay` prop to `SheetContent` (default true — other sheets unchanged); the chat now renders `modal={false} overlay={false}` with outside-interaction prevented. | Open Ask AI → navigate/click the app **while it stays open**; it no longer dims/locks the app or closes on an outside click (close via X or the ⭐). |
| **P2-12 phantom badge** | The bell summed feedback-requests + approvals but always routed manager+ to `/approvals`. Now routes to whichever queue actually has items. | HRBP with a pending feedback request: the "1" bell opens `/feedback` (where the item is), not an empty inbox. |

Commits (newest first): dashboard deep-links + dead route · topbar help/badge · non-blocking panel ·
nudges dedupe + unique seed names · 360 cycle sheet · P0-3 landing · P0-1 destructive refusal ·
P0-2 seed role reconcile · BUGS_FOUND report.

**Test status:** backend `apps/ai apps/core` → 317 passed; frontend vitest → 117 passed; tsc clean.

---

## 🚩 Flagged — not fully fixed tonight, with why + proposal

1. **P2-7 "agent is dumb / no memory."** The served build **is** agent-V2 — verified live: plan→per-step
   approve works for **Admin/HRBP/Manager** (e.g. "approve all goals" → a confirm step; "start a 360…"
   → a plan). So the "old read-only build" hypothesis is **not** the cause. The real limitation is the
   **read/Q&A path** in `apps/ai/agents/chat.py`: it only knows goals + latest score, **misroutes**
   "how many reviews" to a goals answer, and carries **no memory** on reads. Turning it into a general
   reasoning agent (memory on reads, answer reviews/approvals counts, multi-turn context) is a
   **feature-sized** change with real scope-safety risk, so I did not blind-ship it overnight.
   *Proposal:* thread the session transcript into the read path and add read handlers for
   reviews/approvals counts, all still RBAC-scoped. **Question for you below.**
2. **P2-9 remaining dashboard cards** (succession risk, approvals inbox, stale goals). Nudges + summaries
   are done. The others need deep-link plumbing on their target pages (SuccessionPage `?role=`,
   ApprovalsPage `?route=`), and **stale-goals is blocked**: the backend (`apps/ai/agents/stale_goals.py`)
   returns only display strings (no `goal_id`/`employee_id`) — it needs to return ids before the row can
   link. Exact steps are in BUGS_FOUND #9.
3. **P1-5 HRBP JD generation "crash."** The **backend is verified working** end-to-end (create → generate
   → job SUCCEEDED → PENDING_HUMAN_REVIEW; no 500/traceback). I could not reproduce a crash server-side.
   If it still errors in the browser, it's a client-side issue in `JdDetailPage` — please note the exact
   browser-console error on retest and I'll fix that specific failure.
4. **P3-13 "Check with AI" re-check loop** — the quality flags are one-shot with no re-run after editing.
   A "re-check" affordance is a small frontend add (`ReviewDetailPage`); deferred, flagged.
5. **P3-14 Tenant config (raw JSON)** — it's a real per-tenant settings bag; it needs a friendlier
   label/explainer, not removal. Cosmetic; deferred.
6. **P3-15 Entitlements per-person tiers** — **by design** today: `Entitlement` is one row per tenant
   (`billing/models.py`, `UniqueConstraint`). Per-person/per-group tiers is a **product decision + a real
   feature**, so per your "don't invent" rule I did **not** build it. **Question below.**
7. **P3-16 Integrations honest state** — removed the dead nav link (above); a proper "Integrations —
   not connected" page can be added when Jira/Slack are wired.
8. Minor: 6 of 210 seeded display names still collide (base-seed fixed names vs generated) — cosmetic,
   down from ~dozens; can be deduped further if it bothers you.

---

## ❓ Questions for you (answer in the morning; I'll act on them)
1. **Agent read-path (P2-7):** do you want me to invest in a richer read/Q&A agent (session memory +
   answer reviews/approvals/team questions, still strictly RBAC-scoped)? It's a feature, not a bug fix —
   worth a focused task.
2. **Entitlements (P3-15):** should entitlements stay **tenant-wide** (documented as by-design), or do
   you want **per-person/per-group tiers** (a new model + UI + gating change)? Your call, not mine.
3. **Remaining dead links (P2-9):** OK to add `?role=`/`?route=` deep-links to Succession/Approvals, and
   to extend the stale-goals API to return ids so those rows can link? (Backend + frontend touch.)

---

## Full retest checklist (per bug, at http://localhost:8090 — hard-refresh first)
- [ ] **Roles:** `ada@`→Manager nav+dashboard; `priya@`→HRBP; `admin@`→Admin; `akhil@`→Employee. None shows "You don't have access" on landing.
- [ ] **Agent delete:** ask "delete all the data" / "delete everyone" → explicit refusal, nothing changes.
- [ ] **Agent works (all roles):** as admin/HRBP/manager, "start a 360 for <a report> and draft their review" → a plan with per-step Approve; approve → runs, lands PENDING.
- [ ] **360 open:** Manager → a 360 cycle → "Open for collection" → flips to Collecting **without reopening**.
- [ ] **Review finalize / approval reject:** state updates live (no reopen).
- [ ] **Dashboards (HRBP/Admin):** short KPI-nudges (≤5 + "+N more"), no repeated names; clicking a summary/nudge navigates to the record/person.
- [ ] **Top bar:** single ⭐ Ask AI (no "?"); the bell count opens the queue that has the items.
- [ ] **AI panel:** open it, then navigate/use the app with it still open (non-blocking); close via X.
- [ ] **JD (priya@):** JD Library → New JD → Generate with AI → lands PENDING_HUMAN_REVIEW. If it errors, capture the console error.
- [ ] **Admin:** Settings shows Users/Configure/Entitlements (no dead Integrations link); each loads.
