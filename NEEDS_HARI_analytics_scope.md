# NEEDS_HARI — does Analytics & Reporting belong in MVP scope?

**Status:** non-blocking. A safe default was chosen and the build proceeded.

## The question
**Analytics & Reporting** is marked ✅ **MVP** in `docs/Document_2_..._Specification.md`
§Module 12, *but it is NOT one of the 14 steps in CLAUDE.md's locked build order.*
So there is a discrepancy between the two source documents about whether Analytics
is in the MVP cut.

## The safe default I chose (and built on tonight)
I **built it** (as "Module A", inserted per `docs/tonight_build.md`'s ordering:
after M11, before M12). Rationale:
1. Doc 2 §Module 12 marks it ✅ MVP — the feature specification (the build
   contract) includes it.
2. It is **fully deterministic** (no AI on the critical path) and builds **only on
   already-completed modules** — it reads `CycleScore` (M2), the 9-box
   `NineBoxPlacement` (M8), and the reporting tree (M7/M1). It adds **no new
   persisted model** (aggregates are computed + cached via `tenant_cache_key`).
3. `docs/tonight_build.md` explicitly schedules it tonight and instructed me to
   write this note.

## What Hari needs to confirm
- Does **Analytics & Reporting belong in the MVP / July-7 QA-handoff scope**, or
  should it be deferred to Phase 2? If deferred, the whole `apps/analytics` app +
  its routes (`/api/analytics/...`) + RBAC keys
  (`view_individual_analytics` / `view_department_analytics` /
  `view_calibration_grid`) can be reverted as a single unit — it is additive and
  touches no prior module's behaviour (the 919 prior tests stayed green).

## Design notes worth a sanity-check
- **Min-cohort suppression threshold = 5** (per the Doc-2 §Module 12 diagram). This
  is a **separate, larger** threshold from the Module-4 360-feedback per-group
  min-volume of **3** — both are kept and documented. A department/cohort view with
  **< 5 members suppresses individual values** (aggregate-only), so a small team can
  never be de-anonymised by its manager. Confirm 5 is the intended figure.
- A "department" is modelled as **a manager + their reporting subtree** (there is no
  `Department` model yet; the reporting tree from `User.manager` is the natural
  cohort). Confirm this is the right cohort definition, or whether a first-class
  `Department`/`BusinessUnit` is wanted later (it would also refine the HRBP scope
  approximation noted since Module 1).

Until you say otherwise, Analytics is built and green.
