# HARI_FULL_TEST — complete manual walkthrough before QA handover

**App:** http://localhost:8090 · **Tenant:** `acme` · **Password (all):** `Passw0rd!demo`

| Role | Account | Who |
|------|---------|-----|
| Admin | `admin@acme.test` | Full tenant control |
| HRBP | `priya@acme.test` | Business-unit wide |
| Manager | `ada@acme.test` | Her team (incl. Vera Lindqvist, Akhil) |
| Employee | `akhil@acme.test` | Own data only |

**Before you start** (5 min): `docker compose ps` shows web/celery-worker/mysql/redis up, then
`BASE=http://localhost:8090 ./scripts/demo_ready.sh` → expect **57/57 checks · DEMO READY**.
If lockout tests were run recently, wait 15 min or reseed. Reset-password links print in
`docker compose logs web -f` (dev console email). Test in a normal window; use a **private
window** for second-session/invite steps so cookies don't collide.

Legend: every item ends with `Result: PASS / FAIL / NOTES: ____` — tick the box only on PASS.

---

## 0 · MUST PASS before handover

These are the recently fixed bugs and the paths QA will hit first. If any fails, stop and flag.

- [ ] **0.1 AI "Open the draft" navigates (fixed bug #1).**
  Login **ada@** → sparkle **Ask AI** (top bar) → type `make a review for Vera` → Send.
  SEE: a plan card with a `draft_review` step (not an immediate write). Click **Approve** on the step.
  SEE: result card "review" with an **Open →** link. When the plan completes, a suggestion chip
  **"Open the draft to review it"** appears. Click the chip.
  SEE: you **navigate to `/reviews/<id>`** — Vera's review page. The chip text is **NOT pasted
  into the chat input**, and the agent never replies with a goals list.
  `Result: PASS / FAIL / NOTES: ____`

- [ ] **0.2 Typed "open the draft" also navigates (backend half of bug #1).**
  Same chat session: type `open the draft` → Send.
  SEE: "Here it is — opening review." with an **Open** button that goes to the same review.
  Then open a **fresh** chat session (reload the page, new conversation) and type `open the draft`.
  SEE: an honest "I don't see a recent record like that in this conversation…" — **never** a goals dump.
  `Result: PASS / FAIL / NOTES: ____`

- [ ] **0.3 Goals screen shows no junk / no duplicates (fixed bug #2).**
  Login **ada@** → **Goals & OKRs** (`/goals`).
  SEE: each person appears once with their current-cycle goals only (typically 2 per person:
  "Deliver cycle objectives" + "Grow craft & collaboration"). **No** goal titled "BUG1…", **no**
  repeated identical goals from archived cycles. Progress bars vary (some red, some amber, some green).
  `Result: PASS / FAIL / NOTES: ____`

- [ ] **0.4 No "not authorized" walls anywhere.**
  For EACH of the four accounts: log in, click **every item in the sidebar** and the bell icon.
  SEE: every visible link opens a working page. You must **never** see "You don't have access" /
  403 / a permission error from something the UI itself offered. (Missing features are simply
  absent from the nav, not shown-then-blocked.)
  `Result (admin): ____ (priya): ____ (ada): ____ (akhil): ____`

- [ ] **0.5 Create/save paths actually persist.**
  As **ada@**: Goals → **New goal** for Vera (any title, weight, one KPI) → Save → the goal appears
  without a reload. Record a KPI actual on any goal → the progress % updates **live**.
  As **akhil@**: Check-ins → submit this week's check-in → it shows as submitted.
  `Result: PASS / FAIL / NOTES: ____`

- [ ] **0.6 Review AI draft lands PENDING and finalize updates the UI (HITL gate).**
  As **ada@** → Reviews → open a report's review in DRAFT → **Request AI draft**.
  SEE: a job spinner, then the draft body appears with state **PENDING_HUMAN_REVIEW** — it is
  never auto-approved. Edit/complete → **Finalize/Approve** → the state chip updates on screen
  without a manual reload.
  `Result: PASS / FAIL / NOTES: ____`

---

## 1 · Login & authentication

- [ ] **1.1 Login each role.** `/login`: tenant `acme` + each account.
  SEE: lands on the role's dashboard; the sidebar differs per role (see §2); your name/avatar
  in the top bar.
  `Result: ____`

- [ ] **1.2 Logout really logs out.** Avatar menu → **Sign out**.
  SEE: back at `/login`. Press Back — you do NOT re-enter the app with data; protected pages
  redirect to login. (Server-side: the refresh token is revoked, not just cleared locally.)
  `Result: ____`

- [ ] **1.3 Bad login is generic.** Wrong password once.
  SEE: one generic "invalid credentials" style message — nothing that reveals whether the
  email exists.
  `Result: ____`

- [ ] **1.4 Forgot / reset password.** From `/login` → **Forgot password?** → tenant `acme` +
  `akhil@acme.test` → submit. SEE: a neutral confirmation (same message even for a made-up email —
  try one). Grab the link from `docker compose logs web` (`/reset-password?tenant=…&uid=…&token=…`),
  open it, set a new password.
  SEE: reset succeeds; login works with the NEW password only; re-using the same link fails.
  **Reset akhil's password back to `Passw0rd!demo` via the same flow before continuing.**
  `Result: ____`

- [ ] **1.5 Session list + revoke.** Login **ada@** in your main window AND in a private window.
  Main window → avatar → **My Settings** (`/settings`) → Sessions.
  SEE: 2+ sessions listed (current one marked). Click **Sign out other devices**.
  SEE: the private window's session dies on its next action (kicked to login when its token
  refreshes — within ~15 min, or immediately on reload after the access token expires).
  `Result: ____`

- [ ] **1.6 Account lockout.** ⚠️ Use a throwaway account (create one via §8.2 invite), NOT a
  demo account. Enter the wrong password **8×**.
  SEE: a "too many attempts" style message — and the **correct** password is also refused
  (HTTP 429) until ~15 minutes pass. Login history (My Settings) records the lockout.
  `Result: ____`

- [ ] **1.7 2FA surface.** My Settings → Security.
  SEE: **Enable 2FA** produces a TOTP secret/QR to scan; after enrolling+confirming with a code
  from your authenticator, next login asks for the 6-digit code; **Disable 2FA** requires your
  password. (If you skip full enrollment, at minimum: enroll shows a secret, disable asks for
  the password.)
  `Result: ____`

- [ ] **1.8 Login history.** My Settings → Login history.
  SEE: your recent SUCCESS entries (and FAILED/LOCKOUT ones from 1.3/1.6) with time + device.
  `Result: ____`

---

## 2 · RBAC — what each role sees (and doesn't)

Log in as each role and compare the sidebar to this table. ✅ = must be visible, ✗ = must be
ABSENT (not visible-but-blocked). Career Paths, Succession and Configure are hidden for
**everyone** in v1 (deferred to v2) — they must not appear at all.

| Sidebar item | akhil (Emp) | ada (Mgr) | priya (HRBP) | admin |
|---|---|---|---|---|
| Dashboard | ✅ | ✅ | ✅ | ✅ |
| Goals & OKRs | ✅ (own only) | ✅ (team) | ✅ (BU-wide) | ✅ |
| Reviews | ✅ (own) | ✅ (team) | ✅ | ✅ |
| Feedback | ✅ | ✅ | ✅ | ✅ |
| Check-ins | ✅ (My week) | ✅ (+ My team tab) | ✅ | ✅ |
| Recognition | ✅ | ✅ | ✅ | ✅ |
| Approvals | ✗ | ✅ | ✅ | ✅ |
| Employees (`/org`) | ✗ | ✅ | ✅ | ✅ |
| JD Library | ✗ | ✗ | ✅ | ✅ |
| Analytics | ✗ | ✅ | ✅ | ✅ |
| Audit | ✗ | ✗ | ✅ | ✅ |
| Users & Roles | ✗ | ✗ | ✗ | ✅ |
| Entitlements | ✗ | ✗ | ✗ | ✅ |

- [ ] **2.1 Sidebar matches the table for all four roles.** `Result: ____`
- [ ] **2.2 Deep-link denial is graceful.** As **akhil@**, manually browse to `/admin/users`
  and `/audit`. SEE: you are bounced to the dashboard (or a clean redirect) — no broken page,
  no data. `Result: ____`
- [ ] **2.3 Scope inside shared pages.** Goals as akhil = only his own goals; as ada = her team;
  as priya = the business unit. People search/profile (`/people/:id`): akhil cannot open a
  random colleague's profile with private data. `Result: ____`
- [ ] **2.4 Post-login landing is safe.** While logged out, visit `/admin/users` → login as
  **akhil@**. SEE: you land on the dashboard, not an unauthorized admin page. `Result: ____`

---

## 3 · Dashboards (per role)

- [ ] **3.1 Employee (akhil@).** SEE: own KPIs/goal progress, own check-in state, recognition
  feed — no team/BU widgets, no at-risk tiles. All numbers are real (match Goals page). `Result: ____`
- [ ] **3.2 Manager (ada@).** SEE: team stats (goal progress, pending reviews count, at-risk
  people tile from AI nudges), stale-goal nudge panel. Clicking a stat leads somewhere sensible. `Result: ____`
- [ ] **3.3 HRBP (priya@).** SEE: BU-wide cockpit (calibration/coverage style stats) — wider
  numbers than ada's. `Result: ____`
- [ ] **3.4 Admin (admin@).** SEE: tenant-level dashboard; nothing errors. `Result: ____`

---

## 4 · Goals & OKRs (`/goals`)

- [ ] **4.1 Read + open a person.** As **ada@**: each team member shows their goals with a big
  % + colored bar + plain-English status; expanding a goal shows KPIs ("Progress" label,
  "Higher = better" wording) and the **Updates** timeline (2–4 realistic notes on active goals). `Result: ____`
- [ ] **4.2 Create a goal (manager) = saves.** **New goal** → pick Vera, title, objective,
  weight, add a KPI → Save. SEE: appears immediately under Vera; survives a reload. `Result: ____`
- [ ] **4.3 Record a KPI actual = updates live.** On any active goal record a new actual.
  SEE: the % and bar update **without a reload**; an entry lands in the goal's Updates timeline. `Result: ____`
- [ ] **4.4 Approve flow.** The goal you created (DRAFT) → approve as ada.
  SEE: status chip flips to ACTIVE on screen. `Result: ____`
- [ ] **4.5 Employee's own view.** As **akhil@**: sees only his 2 goals, can record actuals on
  his own KPIs, canNOT create goals for others or see Vera's. `Result: ____`
- [ ] **4.6 Weights sane.** Any person's active goals sum to 100 (no 200/100 weight bug). `Result: ____`

---

## 5 · Reviews (`/reviews`, detail `/reviews/:id`) — HITL

- [ ] **5.1 List per role.** akhil = own reviews; ada = her team incl. Vera's DRAFT review. `Result: ____`
- [ ] **5.2 Request AI draft → PENDING (= MUST-PASS 0.6).** `Result: ____`
- [ ] **5.3 Edit + finalize.** Edit the draft body/sections, finalize/approve.
  SEE: state updates in the UI instantly; the final body is what you edited (human words win). `Result: ____`
- [ ] **5.4 Review quality flag.** In the editor, SEE the review-quality indicator/flag surface. `Result: ____`
- [ ] **5.5 Comments.** Add a comment on a review → appears without reload. `Result: ____`
- [ ] **5.6 Employee sees the outcome.** As **akhil@** (or Vera's own login `vera@acme.test`):
  the finalized review is readable; PENDING internals/other people's reviews are not. `Result: ____`

---

## 6 · 360° / Feedback (`/feedback`)

- [ ] **6.1 Open a cycle.** As **ada@**: an existing 360 cycle for a report opens with
  participants and progress. `Result: ____`
- [ ] **6.2 Start a 360.** Via the page (or AI: "start a 360 for Vera" → approve).
  SEE: a new cycle appears; participants listed. `Result: ____`
- [ ] **6.3 Give feedback.** As **akhil@**: pending feedback requests are visible; submit one.
  SEE: it flips to done **without reopening the page** (state reflects immediately). `Result: ____`
- [ ] **6.4 Anonymity.** Viewing collected 360 feedback as the subject's manager: giver
  identities are anonymized where the cycle says so. `Result: ____`

---

## 7 · Check-ins, Recognition, Employees, JD, Analytics, Notifications, Approvals, Audit

- [ ] **7.1 Check-ins (`/checkins`).** akhil: submit **My week** (wins/blockers) → shows
  submitted. ada: **My team** tab shows the team's week + AI meeting-summary block; respond to
  a report's check-in → the response appears for the report. `Result: ____`
- [ ] **7.2 Recognition (`/recognition`).** Feed shows seeded kudos with real names. Give
  recognition (as anyone) to a colleague → appears at the top of the feed instantly. `Result: ____`
- [ ] **7.3 Employees (`/org`, ada/priya/admin).** Directory loads with search; org chart
  expands on demand (no crash on big teams); open a person → `/people/:id` profile with role,
  manager, goals summary. `Result: ____`
- [ ] **7.4 JD Library (`/jd`, priya/admin only).** List opens; generate/create a JD → the
  AI-generated JD lands for review (HITL — not auto-published); open detail `/jd/:id`. `Result: ____`
- [ ] **7.5 Analytics (`/analytics`, manager+).** Charts render with real seeded data;
  individual trend shows ~4 points (3 prior cycles + current); department/calibration views
  load. As ada the scope is her team; as priya it's wider. `Result: ____`
- [ ] **7.6 Notifications (bell, top bar).** SEE a real pending-actions count (not a dummy);
  clicking it opens the relevant queue (e.g. approvals/reviews awaiting you); acting on the
  item drops the count. `Result: ____`
- [ ] **7.7 Approvals (`/approvals`, manager+).** Pending items (e.g. the DRAFT goal from 4.2
  before you approved it) are listed; approve one → it disappears from the queue and the
  underlying record updates. `Result: ____`
- [ ] **7.8 Audit (`/audit`, HRBP/admin).** Recent actions appear (your goal.approved,
  review finalize, plan changes, invitation events) with actor + timestamp. There is **no**
  edit/delete affordance — the log is read-only. `Result: ____`

---

## 8 · Admin & Phase-2 account features

- [ ] **8.1 My Settings (`/settings`, any role).** Edit display name/phone/timezone → Save →
  persists after reload. Change password (needs current password) → you're signed out
  everywhere else; new password works. Email change sends a confirm link (see web logs) and
  only applies after confirming. `Result: ____`
- [ ] **8.2 Invite + RESEND (priya@ or admin@).** Admin → **Users & Roles** → **Invite user** →
  fresh email (e.g. `qa.test1@acme.test`) + role.
  SEE: invite link shown for copy-paste; the invite appears under Pending with **Resend** and
  **Revoke**. Click **Resend** → "Invitation re-sent" + a fresh link in the box. Open the link
  in a private window → set a password → you're logged in as the new EMPLOYEE. The used link
  is dead afterwards; an accepted invite can't be resent. As **akhil@** there is no invite UI. `Result: ____`
- [ ] **8.3 Users admin (admin@).** Search users (pagination works at 200+ people), change a
  user's role, deactivate → that user can't log in; reactivate restores. `Result: ____`
- [ ] **8.4 Subscription plan gating (admin@).** Admin → **Entitlements**: current plan =
  **Enterprise**. Switch to **Starter**.
  SEE: locked features flip to 🔒 immediately (no reload of the server needed); Org branding
  save is refused with an "Enterprise-plan feature" message (server 403, not just hidden UI).
  Switch back to **Enterprise** → branding saves. **Leave it on Enterprise** (the 211-person
  tenant + invite demo depend on it). `Result: ____`

---

## 9 · AI agent & chat panel

- [ ] **9.1 Draft-review story on Gemini (= MUST-PASS 0.1/0.2).** `Result: ____`
- [ ] **9.2 Memory & pronouns.** As **ada@**: ask `how is Vera doing on her goals?` → a real
  answer about Vera. Follow up `how many reviews does she have?` → "she" = Vera, a real count —
  not a goals dump. `Result: ____`
- [ ] **9.3 Scope refusal.** As **akhil@**: ask about another employee's performance
  (`how is Vera doing?`). SEE: a no-data-in-your-scope answer — no leak. `Result: ____`
- [ ] **9.4 Write = plan + approval, refusal beat.** Any write ask ("give Vera kudos") returns
  an inert plan; nothing executes without your per-step Approve. An out-of-scope/destructive
  ask ("delete all goals") is refused, plans nothing destructive, executes nothing. `Result: ____`
- [ ] **9.5 Panel behavior.** Open the chat → drag its edge to resize (persists after reload) →
  navigate between pages: the panel **stays open** with history intact → reload the browser:
  the conversation **resumes** (same session). `Result: ____`

---

## 10 · Data cleanliness (demo credibility)

- [ ] **10.1 Goals are current-cycle only** — no archived duplicates, no "BUG1" junk (= 0.3). `Result: ____`
- [ ] **10.2 Progress varies** — bars range roughly 26–100%, several statuses represented;
  nothing looks copy-pasted. `Result: ____`
- [ ] **10.3 History is real** — Analytics shows prior-cycle trend points (the archived cycles
  exist for trends, invisible on Goals). `Result: ____`
- [ ] **10.4 People look real** — 211 seeded people with names/departments; recognition/check-in
  content reads naturally; Vera Lindqvist is Ada's report with a DRAFT review ready for the demo. `Result: ____`
- [ ] **10.5 Reseed is safe** — after all testing, run
  `BASE=http://localhost:8090 ./scripts/demo_ready.sh` once more: 57/57 green, junk from your
  testing (draft goals you abandoned, etc.) is cleaned, demo accounts still log in. `Result: ____`

---

## Sign-off

| Section | Items | Passed | Notes |
|---|---|---|---|
| 0 MUST PASS | 6 | ____ | |
| 1 Auth | 8 | ____ | |
| 2 RBAC | 4 | ____ | |
| 3 Dashboards | 4 | ____ | |
| 4 Goals | 6 | ____ | |
| 5 Reviews | 6 | ____ | |
| 6 Feedback/360 | 4 | ____ | |
| 7 Modules | 8 | ____ | |
| 8 Admin/Phase-2 | 4 | ____ | |
| 9 AI agent | 5 | ____ | |
| 10 Data | 5 | ____ | |

**Handover ready when:** section 0 is 6/6 and no FAIL anywhere is unexplained.
Known v1 scope cuts (expected absences, not bugs): Career Paths, Succession/nine-box,
raw tenant Configure, Jira/Slack integrations pages, payments (design-only).
