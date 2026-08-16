# V1_A_SIMPLIFY.md — REDESIGN Goals/OKR + remove T-score (not a re-tag)

**Branch:** main. **Merge:** auto on green. Work autonomously.
**This is a REAL redesign, not adding a status tag to the existing screen.** A previous attempt only
added an "On Track" tag on top of the same complex screen — that is explicitly rejected. The Goals/OKR
screen must be rebuilt so a non-technical SME manager understands it in ten seconds.

## STEP 0 — RESEARCH FIRST (do this before writing any UI)
Research how the leading performance tools actually display goals to everyday managers — **Lattice,
15Five, Betterworks** (and similar). Identify the SIMPLEST common pattern they use: almost universally a
**goal with a % complete and a progress bar**, a plain status, and details hidden until expanded. Write a
short `docs/GOALS_RESEARCH.md` noting what you found and the pattern you're copying. Then build to that
pattern. Do NOT invent a novel UI — copy what already works for normal users.

## STEP 1 — REMOVE T-score from the v1 UI entirely
- T-score is too complex for SMEs. Remove it as a displayed number **everywhere** in the v1 UI
  (person view, goals, dashboards, analytics, reviews, nudges).
- Replace every place it was the headline with a plain **% complete** (goal attainment) and/or a plain
  status word (On Track / Behind / At Risk derived from that %).
- KEEP the T-score computation in the backend/code (feature-flagged off in the UI) so v2 can restore it.
  Do NOT delete the code or the data. Document how to re-enable it for v2 in PROGRESS_V1.md.

## STEP 2 — REBUILD the Goals/OKR screen (the headline: % + bar per goal)
When a manager opens a person, the FIRST thing they see, per goal:
- The **goal title** in plain words.
- A **% complete** number (e.g. "72%") — big and clear.
- A **colored progress bar** filling to that % — green (ahead/on track), amber (behind), red (at risk).
  Exactly like a to-do / project progress bar. No statistics, no jargon.
- A one-line plain status ("On track" / "Behind" / "At risk").
Above the goals, one plain summary line for the person: e.g. "3 of 4 goals on track — 68% overall."

**Everything technical is hidden until "Show details":**
- weight ("how much this counts"), target vs actual numbers, KPI breakdown, direction, cycle dates.
- A newcomer manager never needs to open details to understand how someone is doing.

**Relabel all remaining jargon in plain English** (only visible in details):
- actual → "Progress", target → "Goal", weight → "How much this counts",
  increasing/decreasing → "Higher is better ↑ / Lower is better ↓".

**The bar for done:** a manager who has never used the product opens a person's Goals and, in ten
seconds, knows which goals are on track and which aren't — without reading a tooltip or learning OKRs.

## STEP 3 — Remove the complex enterprise features from the v1 UI (keep code for v2)
Hide from nav + routes + dashboard cards (do NOT delete code; document re-enable path):
- **Nine-box / calibration grid** — remove from v1 UI entirely.
- **Succession** (dashboard, nine-box, critical roles, plans) — remove from v1 UI.
- **Career roadmaps / Career Paths** — remove from v1 UI.
- **Raw-JSON tenant config + any advanced admin** a normal admin wouldn't understand — hide or replace
  with a couple of plain labeled toggles.
Remove every resulting dead link cleanly — no "coming soon" clutter.

## STEP 4 — Analytics + dashboards, plain and clickable
- Analytics leads with the simple trend + a plain status distribution (how many On Track / Behind / At
  Risk). No calibration grid. No T-score. Scannable.
- Every dashboard card: plain-language headline + a number, and every list row deep-links to its record.
  Dedupe and cap long lists (top N + "view all").

## Rules
- Hide via nav config + route guards + feature flags; keep underlying code + endpoints intact for v2.
- No backend data-model changes — this is presentation + navigation + the Goals screen rebuild.
- Keep all tests green; where a test asserts a now-removed screen or the old T-score display, update it
  to the v1 state (mark the old coverage v2, don't silently delete).
- After: reseed clean demo data so every kept screen looks full and the new goal bars show real %.

## Done when
- `docs/GOALS_RESEARCH.md` exists and the new Goals screen matches the simplest real-tool pattern
  (% + colored bar per goal, details hidden). T-score is gone from the v1 UI (code kept). Nine-box /
  calibration / succession / career are gone from the v1 UI (code kept). Every kept screen is
  understandable in ten seconds. Tests green. All logged in PROGRESS_V1.md with re-enable instructions.
