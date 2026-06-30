# HARI — dashboard redesign: data-source gaps + decisions (N1–N6)

You said: match the mockup, but **render real data — never hardcode placeholders; missing source →
empty state + flag, never fabricate.** I mapped every mockup tile + nav item to the real endpoint
surface (`shared/src/api/endpoints.ts`) and the current Manager cockpit. Most tiles are real or
composable. These are the gaps where the mockup shows something the product has **no real source** for,
plus one scale mismatch. I won't invent any of them — I need your call (recommended option first).

## The one that shapes every score tile — please confirm

### N6 — Performance scale: the product is a **T-score + risk status**, not a 1–5 rating
The mockup shows "4.2 / 5", "87%", and a donut with "4.5–5.0 / 3.5–4.4 / 2.5–3.4 / < 2.5" bands. The
backend has **no 1–5 performance rating** — `CycleScore` is a **T-score** (≈50 mean) + `risk_status`
(SAFE / AT_RISK / CRITICAL). The only 1–5 value anywhere is **check-in mood**.
- **(A) Recommended:** keep the mockup's card/donut/table **layout**, populate with the **real T-score
  + risk bands** (adapt the labels/legend to the real metric). On-brand, honest, zero backend change.
- **(B)** Define a fixed T-score→1–5 mapping purely for display (a presentation transform; still no new
  data). Riskier — a derived rating can mislead.
- **(C)** A literal 1–5 rating model = **backend change → out of scope** (would need a new field +
  scoring path). Flagged as not-this-pass.
**→ I'll build (A) unless you say otherwise. Confirm before I build the Dashboard.**

## No real backing source (won't fabricate)

### N3 — "Engagement Score 4.3 / 5"
No engagement feature/endpoint. Closest real signal: **average team check-in mood** (`checkinsApi.team`,
genuine 1–5).
- **(A) Recommended:** wire to avg team check-in mood, labeled honestly (e.g. "Team mood" or
  "Engagement (check-in mood)"). Real, same /5 shape.
- **(B)** Empty state ("No engagement data yet") until a real engagement source exists.

### N4 — "Announcements" rail (Q2 cycle live / AI Insights)
No announcements feature/endpoint.
- **(A) Recommended:** render a single **real "active cycle" status** line derived from `cyclesApi.list`
  / `feedbackApi.cycles` (e.g. "Q2 review cycle open · reviews due {date}"). Real, useful.
- **(B)** Empty state / omit the rail.
- (Static marketing copy = fabricated content → I won't do it without your OK.)

### N5 — Top-bar notifications badge (the "3")
No notifications endpoint.
- **(A) Recommended:** compose a **real pending-actions count** (approvals inbox + feedback requests +
  reviews to action) — the same sources as My Tasks.
- **(B)** Hide the badge until a notifications service exists.

### Team Competency radar (Leadership / Communication / Problem Solving / Technical Skills / Collaboration; Your Team vs Company Avg)
**No competency-rating feature on these axes, and no company-average.** (`careerApi.skillGap` is
per-roadmap skill *names*, not org-wide competency *scores*.)
- **Decision:** render a proper **empty state** in that card ("Competency data not available yet"),
  styled on-brand. I will **not** fabricate the radar. If you want it real, it needs a new competency
  model (backend → out of scope). Tell me if you'd rather omit the card entirely.

## Nav items in the mockup with no route

### N1 — 7 aspirational sidebar items have no backing route/feature
**1:1 Meetings · PIP & Improvement · Teams · Skills & Competencies · Reports · Engagement · Benchmarks.**
Creating links to them = dead links (violates the no-shown-then-denied rule). The plan maps the
mockup's 4 sections onto the **real** routes (Check-ins stands in for "1:1 Meetings"; Org for
"Employees"; etc. — see `docs/design/REDESIGN_PLAN.md` §(b)).
- **(A) Recommended:** **omit** the 7 routeless items — sidebar shows only real, working destinations.
- **(B)** Show them as visibly **disabled "Coming soon"** items to match the mockup's fullness (no
  navigation; clearly non-functional).

## Build-order decision

### N2 — Employee Profile (Constitution Ch.12 "masterpiece")
No dedicated profile screen exists today (only the Org **PersonSheet** slide-out).
- **(A) Recommended:** new additive read-only **`/people/:id`** composing existing endpoints only
  (scores, goals, reviews, recognition, feedback summary, career). No new backend/data.
- **(B)** Restyle the existing PersonSheet in place — smaller, less of a hero screen.

---

**My default if you just say "go":** N6→A (confirm anyway), N1→A, N2→A, N3→A, N4→A, N5→A, Competency
radar → empty state. Reply with any overrides and I'll start **Phase 0 (Foundation)**.
