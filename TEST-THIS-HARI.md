# TEST-THIS-HARI.md — your hands-on walkthrough (~30–45 min)

Hi Hari. The web product is finished to a demo-ready standard. This is a
click-by-click script so you can judge it yourself. Each step is "do X → you
should see Y". Tick the boxes as you go. The things **this run changed** are
flagged **[NEW]** so you can focus your judgement there — especially the AI
output quality (Phase B).

> Honesty note: everything below was verified by me over real HTTP against the
> live stack (status codes, AI output, RBAC). What I could **not** judge is how
> it *looks* — see the "LOOK AT THIS" section for where I need your eye.

---

## 0. Start the stack (2 min)

```bash
docker compose up -d --build
docker compose run --rm web python manage.py seed_demo     # idempotent; safe to re-run
open http://localhost:8080
```

- [ ] `http://localhost:8080` loads the login screen.

**Demo accounts** — password is `Passw0rd!demo` for everyone; the **Workspace**
field is the tenant slug.

| Role | Workspace `acme` (FULL_AI) | Workspace `globex` (STARTER) |
|------|----------------------------|------------------------------|
| Admin | `admin@acme.test` | `admin@globex.test` |
| HRBP | `priya@acme.test` | `priya@globex.test` |
| Manager (4 reports) | `ada@acme.test` | `ada@globex.test` |
| Employee | `reza@acme.test` | `reza@globex.test` |

> The Admin Hub is a **Manager-and-up desktop tool** by design. Employees get a
> personal cockpit only; full employee self-service is the separate **mobile**
> build (see `MOBILE_BUILD_PLAN.md`). Test the rich surfaces as Admin / HRBP /
> Manager. `ada@acme.test` is both a manager **and** the subject of a released
> 360 + a roadmap, so use her for the "My 360" and "Career" checks.

---

## A. Admin — `admin@acme.test` / `acme` (~7 min)

- [ ] **Sign in.** Top-left shows **Acme Corporation** (the real tenant — **[NEW]**, it used to be hardcoded). Left nav shows Workspace + Talent Intelligence + Governance + Administration groups.
- [ ] **Users & Roles** (`/admin/users`) → you see the seeded roster. Try **change a role** / **set reporting line** / **set display name** → the row updates (real writes).
- [ ] **Tenant Config** (`/admin/tenant`) → settings load and save.
- [ ] **Entitlements** (`/admin/billing`) → acme shows **FULL_AI**; the TokenLedger / AI-usage story is on this screen. Note the **upgrade** control.
- [ ] **The upgrade contrast:** open a second browser/incognito, sign in as `admin@globex.test` / `globex`. Globex is **STARTER** — AI-heavy features show a **premium "upgrade to unlock"** card (never an error, never hidden). On a FULL_AI tenant those same surfaces are live. *(Optional: click Upgrade on globex and watch the flags unlock app-wide — this mutates globex's demo state.)*
- [ ] **Integrations** (`/admin/integrations`) → Jira/Slack config. Confirm it shows a **secret_ref name only — never a token value**.
- [ ] **Audit Console** (`/audit`) → read-only log; filter + paginate. There is **no** edit/delete affordance (the log is insert-only).

---

## B. HRBP — `priya@acme.test` / `acme` (~8 min)

- [ ] **Sign in** → HRBP cockpit (team/BU tiles).
- [ ] **Analytics** (`/analytics`) → individual trend + department analytics with **real charts**.
  - [ ] **[suppression — judge this]** Find the min-cohort rule: a department with **< 5** people shows an **aggregate-only + privacy notice** (no individual rows); a department with **≥ 5** shows the breakdown. This 4-vs-5 boundary is a privacy guarantee — confirm it reads clearly.
  - [ ] **Calibration grid** (HRBP/Admin) renders the cohort.
- [ ] **Succession** (`/succession`) — employees can never see this; you can.
  - [ ] Coverage dashboard shows RED/AMBER/GREEN.
  - [ ] **Nine-box** grid is interactive; **bench** + **readiness overrides** work.
  - [ ] Pick a critical role → **Generate** a plan → it lands **PENDING** with the deterministic analysis → **[NEW AI]** click **Enrich** → a real Agent-4 narrative is added (crisp, names the coverage gap + the single key action, **no individual names**) → **Publish**.
- [ ] **360 Feedback → Summaries to release** (`/feedback`, HRBP tab) → you see AI summaries awaiting release with confidence, anonymity-passed, suppressed-groups. **Release** one → the subject can then see it.

---

## C. Manager — `ada@acme.test` / `acme` (~15 min) — the core loop + AI quality

- [ ] **Sign in** → manager cockpit: team nudges (**[NEW]** each names the trajectory — *"T-score 40 and behind pace. Weakest goal: '…'"*), reviews, approvals, feedback requests.

### C1. Run a review end-to-end — **judge the AI here [NEW, Phase B]**
- [ ] **Reviews** (`/reviews`) → open or create a review for a report → **Request AI draft**.
- [ ] **[THE KEY AI CHECK]** Read the generated draft. It should:
  - **name the person** (e.g. "Reza"), not "the employee";
  - **cite specific goals + KPIs + numbers** (e.g. *"Throughput 97% vs 100% target, a 3% gap"*);
  - reference the **cycle score / risk band**;
  - give **concrete recommendations** tied to the gaps — **no filler/padding**.
  - It is **PENDING_HUMAN_REVIEW** with a confidence chip + HITL banner — never auto-final.
- [ ] Edit if you like → **Submit** → **Approve** → **Finalize**. (If the review routes through an approval workflow, it enters the route — see C3.)

### C2. Goals & KPIs
- [ ] **Goals & KPIs** (`/goals`) → **New goal**: the form enforces **KPI weights sum to exactly 100** and the employee's active goal weights too (badge flips green/amber). **[NEW]** this rule is now a tested helper.
- [ ] **Record an actual** on a KPI → **Recompute** → the risk badge updates (real scoring).
- [ ] **Approve** a report's goal.

### C3. Approvals
- [ ] **Approvals** (`/approvals`) → as HRBP/Admin **configure a workflow** (sequential/parallel, role/named steps) → **activate** it.
- [ ] Route a real review or JD through it → act in the **inbox** (approve / reject-with-reason) → watch the **tracker** advance (+ escalation). The "re-create to edit steps" model is intentional.

### C4. Org chart
- [ ] **Org Chart** (`/org`) → readable reporting tree with headcount/vacancy rollups; open a **person card**.
- [ ] **Create / fill / close** a position; **link a PUBLISHED JD**.
- [ ] **Reassign** a reporting line → if it would break a mid-cycle rule you get a clean **422** (not a crash).

### C5. 360 feedback — full loop
- [ ] **360 Feedback → Cycles** → **New cycle** for a report → **open** → **invite** reviewers.
- [ ] As the invited givers (the "For me" tab / cockpit), **give feedback** until a group crosses the **min-volume (3)** threshold. Note the anonymity + threshold copy.
- [ ] **Close & summarize** → a real Agent-3 summary is generated, **PENDING** (or HRBP-held if it tripped the breach/sensitive guard).
- [ ] Switch to **priya** (HRBP) → **Summaries to release** → **Release**.
- [ ] Back as **ada** → **My 360** tab → her **released summary** shows (**[NEW]** auto-discovered via `/my-cycles`, no id paste). Confirm a **below-threshold group is marked suppressed** and **no giver identities** appear anywhere.

### C6. Career — **[NEW surface this run]**
- [ ] **Career** (`/career`) → **My development**: ada's roadmap with the **skill gap** (current→required band, weak goals), **tiers** with per-tier **progress** controls, **Refresh (deterministic)**, and **Enrich with AI** (Full-AI gated).
- [ ] Click **Enrich with AI** → a real Agent-5 roadmap draft (specific, advisory, never "promote") appears with a confidence chip. *(On globex/STARTER the button shows an upgrade tooltip instead.)*
- [ ] **My team** tab → ada sees her reports' roadmaps and can refresh/enrich them.

### C7. AI chat
- [ ] Top bar **Ask AI** → ask *"how are my reports doing?"* → a **grounded** answer (names goals + cycle score/risk for people in scope).
- [ ] Ask about someone **out of your scope** → it returns **nothing** (RBAC-bound, no leak).
- [ ] Ask it to *"approve all reviews"* → **blocked** ("I'm a read-only assistant").

---

## D. Employee — `reza@acme.test` / `acme` (~3 min)

- [ ] **Sign in** → a personal **cockpit**: my goals, feedback requests (give feedback from here), my roadmap tile. The management nav is correctly absent.
- [ ] Try to hit `/succession` in the URL → a clean **403/Not-found** (succession is invisible to employees). 
- [ ] *Note:* the employee's own "My 360 summary" and full self-service are the **mobile** surface; the backend endpoint (`/feedback/my-cycles`) is built and was verified live for the employee role. See `NEEDS_HARI_feedback_subject_discovery.md`.

---

## 👀 LOOK AT THIS — your visual judgement needed

I tuned within the existing design system (it's already premium: slate + blue,
purple=AI, gold=premium, dark sidebar, Inter, tabular numbers). I **can't see
pixels**, so please eyeball these and tell me what feels off:

- [ ] **Login + app shell** — the first impression (spacing, the dark sidebar, the topbar).
- [ ] **Dashboard density** per role — too sparse? too busy? right tiles?
- [ ] **The AI surfaces** — the PENDING/HITL banner, the confidence chip, the draft-vs-final treatment on reviews / feedback summaries / succession / career. Do they feel intentional and trustworthy?
- [ ] **The new Career page** (`/career`) — it's brand new; does it match the rest?
- [ ] **Tables & empty states** — consistent? The "nothing here yet" states helpful?
- [ ] **Status badges** — colour semantics (success/warning/danger/AI/premium) legible at a glance?
- [ ] **Narrow window** — the hub is desktop-first but should degrade gracefully; does anything break badly?

---

## ⚠️ KNOWN LIMITATIONS / NOT YET DONE (honest)

- **Employee self-service in the *web* hub is intentionally minimal** (cockpit only). Real employee/manager self-service is the **mobile app** — planned, not built (see `MOBILE_BUILD_PLAN.md`). The `/feedback/my-cycles` endpoint that mobile needs is already built.
- **AI runs on the Groq free tier.** There's a global call ceiling (60/run) + per-tenant budgets + 429 back-off. A burst of AI actions can hit a rate limit (you'll see a calm "try again shortly"). For heavy use, raise the budgets / move off the free tier — see `docs/AI_GOLIVE.md`.
- **Secrets** live in the gitignored backend `.env` (never committed). Production should use a real secret store — see `docs/AI_GOLIVE.md`.
- **Visual polish** is good but is the one area I couldn't judge — hence the section above.
- Open product decisions are in the repo-root `NEEDS_HARI_*.md` files (each has a safe default already taken).
- A duplicate `/api/reviews/calibration` endpoint exists (the UI uses `/api/analytics/calibration`); harmless, noted for cleanup.

---

## 📣 HOW TO REPORT BACK (what's most useful)

When you've clicked through, the most valuable feedback for the next build:
1. **AI quality** — paste 1–2 AI outputs (a review draft, a feedback summary, a succession narrative) and tell me: grounded enough? too long/short? wrong tone? This directly tunes the prompts in `apps/ai/agent_config.py`.
2. **Which screens feel off visually** (from the LOOK-AT-THIS list) — and how.
3. **Any flow that confused you** — where you didn't know what to click next.
4. **Anything that 500'd or felt broken** — with the screen + what you did.

Re-run `python3 scripts/smoke.py` anytime to confirm all 47 core journeys + RBAC
boundaries still pass.
