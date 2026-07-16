# DATA_CLEANUP — demo data hygiene + per-module verification

Goal: the ACME demo tenant that goes to the testing team must read like a real
company — no gibberish, placeholders, char-spam, or unrealistic duplicates — and
every module must render correctly. This is what was found, cleaned, and verified.

## What was junk (found by scanning the live `acme` tenant)

All junk was **runtime test rows** (QA runs + manual API poking), not the seed's
own content. Inventory before cleanup:

| Module | Junk found |
|---|---|
| Recognition | `lijil`, a 58-char `xxxxx…` spam string, + soft-deleted "QA kudos" dupes |
| Reviews | 1 draft body `QA probe body — solid quarter.` (on Vera's demo review) |
| Review comments | 5× `QA probe comment` |
| Feedback | 1× `kn` (2-char gibberish) |
| Check-ins | `d`, `kn`, `kjn`, `kj` (gibberish) |
| JD | `QA Lifecycle JD`, `QA Probe Engineer`, `RB Probe` (7 rows) |
| Goals | 0 gibberish, but **only 2 distinct titles across 1074 goals** (seed filler) |
| Employees | **~220 people had an empty `department`** (not presentable) |

## What was changed (`seed_demo_rich.py`, commit `c29326f`)

1. **`_purge_junk`** (runs first on every reseed) now **hard-deletes** every
   test/placeholder row across recognition / goals / reviews / comments / feedback
   / check-ins / JD, matched by junk heuristics: 7+ repeated chars, a 35+ char
   no-space token, placeholder prefixes (`qa `, `lijil`, `lorem`, `test`, `probe`,
   `bug1`, …), and ≤3-char alpha gibberish. It scans `all_objects` (incl.
   soft-deleted) so **nothing lingers** — a plain soft delete had left Vera's review
   tripping the `(tenant,emp,cycle)` unique constraint, leaving her review-less.
   Idempotent: repeated QA runs can never re-accumulate junk.
2. **Goals diversified** — a **department-keyed OKR pool** (Engineering / Sales /
   Product / Customer Success / Data / Design, + a generic fallback) → **14 distinct,
   realistic goal titles** grouped by function, instead of the same 2 on everyone.
   Weights (60/40) + KPI-sum-100 invariants preserved; KPI actuals still vary per
   person; Akhil stays the forced On-Track showcase.
3. **Departments backfilled** — `_user` now sets `department` on both create and
   reuse, so all ~210 seeded people have a real function (Engineering 40, and ~34
   each in CS/Data/Design/Product/Sales; leadership left blank). Fixes the org
   chart / people list / analytics-by-department / goal keying all at once.

## Per-module verification (live at http://localhost:8090, after reseed)

`./scripts/demo_ready.sh` → **57/57 checks pass**. Content probes as the relevant role:

| Module | Looks real? | Works? |
|---|---|---|
| **Goals / OKRs** | ✅ 14 distinct department OKRs, real KPIs (e.g. "New ARR closed", "CSAT", "Data quality %"), varied progress/attainment | ✅ list loads, progress bars render (demo_ready goals checks pass) |
| **Reviews** | ✅ real assessment prose ("Strong, consistent delivery…", markdown sections); Vera + emp009 DRAFT restored | ✅ open review OK; 15 for ada's team |
| **Recognition** | ✅ 17 cards, 7 distinct real messages, **0 junk** (no xxxxx/lijil/QA) | ✅ feed renders |
| **Feedback** | ✅ real sentences, gibberish removed | ✅ |
| **Check-ins** | ✅ real weekly notes, gibberish removed | ✅ |
| **Employees** | ✅ every person has a department + display name + seeded avatars | ✅ org chart / people list |
| **JD** | ✅ real titles ("Staff SRE", "Senior Platform Engineer", …), QA JDs removed | ✅ |
| **Analytics** | ✅ real distribution across varied attainment | ✅ (demo_ready analytics checks pass) |

## Text-overflow fix (still holds)

The earlier `break-words` fix (commit `1ad0465`) is intact on every free-text
renderer — recognition message + header, review body + comments, feedback summary,
check-in summary, chat turns — plus `min-w-0` on the recognition header. A long
no-space string wraps inside its card and never runs off screen. (`break-words`
verified present in the built bundle; vitest 132/132.)

## Guarantee going forward

Because `_purge_junk` runs at the start of **every** `seed_demo_rich`, and
`qa_handover.sh` reseeds after the QA verifier runs, the demo tenant is always
clean after a reseed — QA runs can add junk transiently, but the next reseed wipes
it. To refresh a pristine demo at any time:

```bash
docker compose exec web python manage.py seed_demo_rich
```
