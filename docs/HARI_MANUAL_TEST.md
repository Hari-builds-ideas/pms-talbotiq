# HARI_MANUAL_TEST — the human click-through before QA handover

The **automated** suite (`./scripts/qa_handover.sh`, 131 checks) already proves API-level RBAC,
negative/edge cases, cross-tenant isolation, and data hygiene. **Run that first and get a green
line.** This document is ONLY the things a script can't see: does it *look* right, *click* right,
does the screen reflect the backend, does it feel finished. ~30–45 minutes in a real browser.

**App:** http://localhost:8090 · **Tenant:** `acme` · **Password (all):** `Passw0rd!demo`

| Role | Account | Sees |
|------|---------|------|
| Admin | `admin@acme.test` | everything |
| HRBP | `priya@acme.test` | business-unit wide |
| Manager | `ada@acme.test` | her team (incl. **Vera Lindqvist**, Akhil) |
| Employee | `akhil@acme.test` | own data only |

**Set up before you start (2 min):**
1. `./scripts/qa_handover.sh` → wait for **✓ … CHECKS PASSED**. This leaves a **fresh reseed**, so
   **Vera Lindqvist and emp009 each have a DRAFT review** ready (needed for the review + AI steps).
   If you burn those during testing, get them back with:
   `docker compose run --rm web python manage.py seed_demo_rich`
2. Open a second browser (or a **private window**) — needed for the sessions test (§5.6).
3. Email links (reset / invite / email-change) print to the console — keep this open in a terminal:
   `docker compose logs web -f`

Legend: tick the box only on PASS; jot anything off in NOTES. "SEE" = the visible pass condition.

---

## 0 · MUST PASS BEFORE HANDOVER

Highest-risk visual/interaction items and the two bugs fixed this cycle. If any fails, stop and flag.

- [ ] **0.1 No "not authorized" wall for an employee.** Login **akhil@** → click **every** item in the
  sidebar and the top-bar bell. SEE: every visible link opens a real, populated page — you **never**
  hit an access-denied / 403 / "you don't have permission" screen from something the UI itself offered.
  `Result: PASS / FAIL / NOTES: ____`

- [ ] **0.2 Create a goal appears instantly.** Login **ada@** → **Goals & OKRs** → **New goal** → pick
  Vera, add a title + one KPI → Save. SEE: the dialog closes and the new goal shows under Vera
  **without a page refresh**. `Result: PASS / FAIL / NOTES: ____`

- [ ] **0.3 KPI actual updates live.** Same screen → open a goal → record a KPI actual (a new value).
  SEE: the big % and the colored bar **change on screen immediately** — no reload.
  `Result: PASS / FAIL / NOTES: ____`

- [ ] **0.4 AI "Open the draft" navigates (fixed bug).** **ada@** → top-bar **Ask AI** → type
  `make a review for Vera` → Send → **Approve** the `draft_review` step. When the plan finishes, a chip
  **"Open the draft to review it"** appears — click it. SEE: you **navigate to Vera's review page**
  (`/reviews/…`). The chip text is **NOT** pasted into the chat box, and the agent does **not** reply
  with a goals list. `Result: PASS / FAIL / NOTES: ____`

- [ ] **0.5 Chat panel behaves.** Open the chat → **drag its left edge** to resize (width changes) →
  click around to other pages (**panel stays open**, history intact) → **reload the browser**
  (panel/conversation **restores**). `Result: PASS / FAIL / NOTES: ____`

- [ ] **0.6 Profile photo uploads AND displays.** Any account → avatar menu → **My Settings** →
  **Upload photo** → pick a real **PNG** under 2 MB. SEE: "Photo updated" toast and the avatar image
  **renders** (top bar + settings). Repeat with a real **JPG**. `Result: PASS / FAIL / NOTES: ____`

- [ ] **0.7 AI drafting resolves — no dead spinner.** **ada@** → open Vera's DRAFT review →
  **Request AI draft**. SEE: "AI is working…" then, within ~30–60s, the draft body appears in
  **PENDING** state. It must reach a result (draft shown) or an honest **"AI step failed — try again"** —
  never a spinner that hangs forever. `Result: PASS / FAIL / NOTES: ____`

---

## 1 · Per-role nav walk (every page renders, nav is role-correct)

For each role: log in, click through **every** sidebar item top to bottom + the bell + avatar menu.
Pass = each page renders real content, **no crash / blank / error boundary**, and the sidebar shows
**only** the rows listed. (v1 hides Career Paths, Succession, Configure, and Integrations for everyone —
they must be **absent**, not shown-then-broken.)

- [ ] **1.1 Employee (akhil@)** — sidebar: Dashboard, Goals & OKRs, Reviews, Feedback, Check-ins,
  Recognition. NO Approvals/Employees/Analytics/Audit/admin. Every page loads. `Result: ____`
- [ ] **1.2 Manager (ada@)** — adds Approvals, Employees, Analytics. Every page loads; team data shows. `Result: ____`
- [ ] **1.3 HRBP (priya@)** — adds JD Library, Audit. Wider data than ada. Every page loads. `Result: ____`
- [ ] **1.4 Admin (admin@)** — adds Users & Roles, Entitlements. **No Integrations item.** Every page loads. `Result: ____`
- [ ] **1.5 Active nav highlight** — on any role, the sidebar highlights the page you're on, and the
  top-bar breadcrumb/title matches. `Result: ____`

---

## 2 · Visual / UX per screen (does it look finished)

Walk these as **ada@** (most populated) unless noted. Judge against a modern SaaS bar.

- [ ] **2.1 Dashboard** — cards align in a tidy grid; numbers render (no `NaN`/`undefined`); the
  **Approval inbox / KPI nudges / Stale goals** cards are a **fixed height and scroll inside** when long —
  the page does **not** stretch to thousands of rows. `Result: ____`
- [ ] **2.2 Goals** — each person's goals as cards; big % + colored bar + status word; KPIs and the
  Updates timeline expand cleanly; no text overflow/truncation clipping. `Result: ____`
- [ ] **2.3 Reviews** — list reads cleanly; open a review → sections/body render as formatted text
  (not raw markdown); state chip is clear. `Result: ____`
- [ ] **2.4 Feedback / Check-ins / Recognition** — feeds/lists look intentional; avatars + names;
  empty areas show a **clean empty state**, not a blank gap or a spinner stuck on. `Result: ____`
- [ ] **2.5 Employees / org chart** (ada@) — directory + org chart render; expanding a big team doesn't
  freeze; a person card opens without layout break. `Result: ____`
- [ ] **2.6 Analytics** (ada@) — charts render with axis labels + legends; the individual trend shows
  multiple points; nothing overlaps or clips. `Result: ____`
- [ ] **2.7 Admin — Users & Roles + Entitlements** (admin@) — tables paginate cleanly at 200+ users;
  the plan/entitlements card is readable. `Result: ____`
- [ ] **2.8 Loading + empty states** — throttle or just watch on first load: skeletons/spinners show
  briefly, then real data; no permanent spinner, no flash of error. `Result: ____`
- [ ] **2.9 Consistency** — cards, buttons, badges, spacing look like **one** product across the pages
  above (same corner radius, same header style). Note any screen that looks off. `Result: ____`
- [ ] **2.10 Dark mode** (if a theme toggle is present) — flip it; text stays readable, no white-on-white
  or invisible borders. `Result: ____`

---

## 3 · Interaction (does it click right)

- [ ] **3.1 Buttons do something visible** — on the screens above, primary buttons open a modal, navigate,
  or show a toast — none are dead. `Result: ____`
- [ ] **3.2 Success toasts** — saving profile, giving recognition, creating a goal each pop a success
  toast. `Result: ____`
- [ ] **3.3 Error toasts + in-UI validation** — submit a form with a bad value (e.g. New goal with blank
  title, or a weight over 100) → the UI shows a clear inline error / error toast, **not** a silent
  no-op or a raw error. `Result: ____`
- [ ] **3.4 Modals/sheets** — open and close (X, Esc, click-outside) cleanly; focus returns; background
  doesn't scroll under them. `Result: ____`
- [ ] **3.5 Bell / notifications** — the top-bar bell shows a real count and opens the relevant queue;
  acting on an item lowers the count. `Result: ____`

---

## 4 · State-reflects-backend (the bug class I keep hitting)

After each write, the **screen must update on its own** — no manual close/reopen or hard refresh.

- [ ] **4.1 Review finalize** — **ada@** → a PENDING review → Approve, then Finalize. SEE: the state chip
  flips to APPROVED then FINALIZED on screen. `Result: ____`
- [ ] **4.2 360 open-for-collection** — **ada@** → Feedback → start/open a 360 for Vera. SEE: the cycle's
  status changes to open/collecting in place. `Result: ____`
- [ ] **4.3 Approval reject** — **ada@** (or priya@) → Approvals → reject a pending step (give a reason).
  SEE: it leaves the inbox and its status updates without reload. `Result: ____`
- [ ] **4.4 Record actual** — (same as 0.3) the goal % updates live. `Result: ____`
- [ ] **4.5 Invite + resend** — **priya@** → Users → Invite a fresh email → the pending list updates;
  click **Resend** → a fresh link appears + "re-sent" toast, still no reload. `Result: ____`
- [ ] **4.6 Plan switch** — **admin@** → Entitlements → switch plan to **Starter**. SEE: locked features
  flip to 🔒 immediately; switch back to **Enterprise** → they unlock. **Leave it on Enterprise.**
  `Result: ____`
- [ ] **4.7 Branding save** — **admin@** (Enterprise) → Org settings → change primary color → Save. SEE:
  a success toast and the value persists on the screen (and after a reload). `Result: ____`

---

## 5 · Account features by hand

Use a **throwaway** account for the destructive ones so you don't lock a demo login — create one via
§5.7 invite, or use akhil@ and reset afterward. Email links print in `docker compose logs web -f`.

- [ ] **5.1 Edit profile + preferences** — My Settings → change phone, timezone, language, notification
  prefs → Save. SEE: success toast; reload → values persisted. Notification prefs show **Email + In-app
  only** (no Slack). `Result: ____`
- [ ] **5.2 Change password** — My Settings → change password. SEE: success; you're signed out of other
  sessions; the new password logs in, the old one doesn't. `Result: ____`
- [ ] **5.3 Change email** — request an email change → grab the confirm link from the logs → confirm.
  SEE: the account email updates only **after** confirming. `Result: ____`
- [ ] **5.4 2FA enroll + confirm** — Security → Enable 2FA → scan/enter the secret in an authenticator →
  enter the 6-digit code. SEE: 2FA shows enabled; next login prompts for a code; **Disable** asks for
  your password. `Result: ____`
- [ ] **5.5 Active sessions list** — My Settings → Sessions shows your current session(s) with device/time.
  `Result: ____`
- [ ] **5.6 Revoke / sign out others (two browsers)** — log in as the same user in a second browser →
  in the first, **Sign out other devices** → the second browser gets kicked to login on its next action.
  `Result: ____`
- [ ] **5.7 Invitation accept flow** — **priya@** invites a new email → copy the link → open it in a
  private window → set a password → you land logged in as that new user. `Result: ____`

---

## 6 · AI agent by hand (live Gemini)

- [ ] **6.1 Memory / follow-up** — **ada@** → Ask AI → `how is Vera doing on her goals?` → then
  `how many reviews does she have?`. SEE: "she" resolves to Vera; a real count, not a goals dump.
  `Result: ____`
- [ ] **6.2 "open the draft" (typed)** — after 0.4's session, type `open the draft`. SEE: "Here it is —
  opening review." with an **Open** button that navigates. `Result: ____`
- [ ] **6.3 Out-of-scope refusal** — **akhil@** → Ask AI → `how is Vera Lindqvist performing?`. SEE: a
  no-data-in-your-scope style answer — no performance data leaks. `Result: ____`
- [ ] **6.4 Result-card Open buttons** — any write plan (e.g. give recognition / start a 360) → after
  approving a step, the result card's **Open** button navigates to the created record. `Result: ____`
- [ ] **6.5 Runs on Gemini** — answers are substantive/natural (not canned), confirming the live model
  is wired. `Result: ____`

---

## Sign-off

| Section | Items | Passed | Blockers |
|---|---|---|---|
| 0 MUST PASS | 7 | ___ | |
| 1 Nav walk | 5 | ___ | |
| 2 Visual/UX | 10 | ___ | |
| 3 Interaction | 5 | ___ | |
| 4 State-reflects-backend | 7 | ___ | |
| 5 Account | 7 | ___ | |
| 6 Agent | 5 | ___ | |

**Handover-ready when:** §0 is 7/7 and no unexplained FAIL elsewhere. Log anything that looks
unfinished (even if "working") in NOTES — that's the whole point of this pass. Expected v1 absences
(not bugs): Career Paths, Succession/nine-box, raw Configure editor, Jira/Slack integrations, payments.
When done, reseed once so QA starts clean: `docker compose run --rm web python manage.py seed_demo_rich`.
