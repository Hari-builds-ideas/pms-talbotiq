# Goals/OKR display — how the real tools do it, and the pattern we're copying

**Purpose:** before rebuilding our Goals/OKR screen, confirm the simplest pattern that leading
performance tools actually use to show goals to everyday (non-technical) managers — then copy it rather
than invent something novel.

**Method (honest):** the vendor help centers (Lattice, 15Five, Betterworks) block automated fetching, so
this is grounded in their public help-center article titles (found via search, linked below) plus
well-documented, stable product patterns for these tools. The conclusion is not controversial — all three
converge on the same shape.

## What the leading tools show

**Lattice** — a goal shows a **progress bar** with a **percent complete**, plus a plain **status**. Lattice's
own help articles are literally titled *"Understand Goal Progress and Statuses Definitions"*, *"Understand
Progress Calculation"*, and *"Update Goal Progress"*. Progress is a single % (either entered directly or
computed from a current-value ÷ target); the goal's status is a small plain label (e.g. **On Track /
Progressing / Behind / At Risk**) shown next to the bar. The Goal Explore side-panel and the Goal Details
page both lead with the bar; the numeric detail lives inside the goal.

**15Five (Objectives & Key Results)** — each objective rolls its key-results up into **one overall %**,
each key result has its own **progress bar**, and a **color/confidence status** (on track = green, behind =
yellow, at risk/off track = red) sits alongside. The list view is scannable: name + % + colored bar.

**Betterworks** — goals show a **percent-complete**, a **colored progress bar**, and a **status**
(On Track green / At Risk amber / Off Track red). Same shape again.

## The simplest common pattern (what we copy)

Per goal, top-level, no jargon:
1. **Goal title** in plain words.
2. **% complete** — big and clear (e.g. "72%").
3. A **colored horizontal progress bar** filling to that % — **green** = on track, **amber** = behind,
   **red** = at risk. Reads exactly like a to-do / project progress bar.
4. A one-word **status** ("On track" / "Behind" / "At risk").

Above the list, one plain **summary line** for the person: *"3 of 4 goals on track — 68% overall."*

**Everything technical is hidden until "Show details":** weight ("how much this counts"), target vs
actual numbers, the KPI breakdown, direction (higher/lower is better), and cycle dates. A manager who has
never used the product understands who's on track in ten seconds without opening details or reading a
tooltip.

## How we adapt it to our data (and one judgement call)

- Our backend already stores per-KPI **actual** and **target** and computes goal **attainment** (a 0–1
  fraction). We surface that as the **% complete** and fill the bar to it. No backend data-model change.
- **Status from %** (simplest, non-expert-friendly): **On track ≥ 70%**, **Behind 40–69%**, **At risk
  < 40%**. Real tools often factor in *time elapsed in the cycle* (pacing) too; we deliberately use the
  simpler pure-% thresholds for v1 clarity and note this in `PROGRESS_V1.md` QUESTIONS as a v2 refinement.
- The **T-score** (our cohort-relative statistic) is **removed from the v1 UI entirely** — it's the exact
  kind of statistic these consumer-grade tools never show a line manager. The computation stays in the
  backend for v2 (see re-enable notes in `PROGRESS_V1.md`).

## Sources
- [Understand Goal Progress and Statuses Definitions — Lattice Help Center](https://help.lattice.com/hc/en-us/articles/1500001282601-Understand-Goal-Progress-and-Statuses-Definitions)
- [Understand Progress Calculation in Lattice — Lattice Help Center](https://help.lattice.com/hc/en-us/articles/360059451414-Understand-Progress-Calculation-in-Lattice)
- [Update Goal Progress — Lattice Help Center](https://help.lattice.com/hc/en-us/articles/1500001241521-Update-Goal-Progress)
- [Customizing Goal Status: Recommended Examples — Lattice Help Center](https://help.lattice.com/hc/en-us/articles/4429889110423-Customizing-Goal-Status-Recommended-Examples)
- [The Tale of Performance Management Tools: 15Five, Lattice, Betterworks… — Josh Bersin](https://joshbersin.com/2021/04/the-tale-of-performance-management-tools-15five-lattice-and-many-more/)
