# Paste this into Claude Code to run the re-weighting (start with RW_BUILD_1)

Put PRODUCT_REWEIGHTING_PLAN.md and the RW_BUILD_*.md files in the repo root (next to BUILD_0_READ_FIRST.md).
Then paste:

---

Read BUILD_0_READ_FIRST.md and PRODUCT_REWEIGHTING_PLAN.md IN FULL — the plan is the product direction
(re-weight, don't rebuild; the foundation stays). Then execute RW_BUILD_1_NAV_AND_RBAC.md, every phase in
order, committed/pushed/green.

All BUILD_0 rules apply: real wiring, never weaken RBAC/scope/tenant isolation/HITL/anonymisation/the
succession employee-404; backend suite never regresses and grows; frontend build/tsc/lint clean; commit
AND push per phase (never force; rejected → BLOCKER + continue local); .env never staged; keep PROGRESS/
DECISIONS/QUESTIONS updated; almost zero LLM calls (FakeLLMProvider; reuse seeded artifacts).

RW_BUILD_1 is UI/permissions only (no new backend): make each role's sidebar + dashboard show ONLY what
that role can use (employees see a clean minimal surface; no shown-then-denied links), demote the
enterprise screens (succession, nine-box, calibration, JD, org, audit, integrations, tenant config) into
an HR/Admin-only "Advanced" area, and confirm server-side route protection still holds (defense in depth).
Do NOT create dead links to Check-ins/Recognition if those routes don't exist yet — RW_BUILD_2/3 add them.

Do NOT stop to ask: log decisions in DECISIONS.md, open questions in QUESTIONS.md (with the safe default
taken), blockers in BLOCKER_*.md, and continue. At the end write RW_BUILD_1_REPORT.md, then STOP so I can
log in as each role and confirm the surfaces before RW_BUILD_2.

Begin with RW_BUILD_1 Phase 1.1 (the nav/RBAC audit map). Go.

---

## After RW_BUILD_1 (your device check, then continue)
- Log in as employee / manager / HRBP / admin and confirm each sidebar shows only its set, no dead links,
  employees see the clean minimal surface. THAT confirmation is yours — the agent can't see the rendered UI.
- Then run RW_BUILD_2 (Recognition): "Execute RW_BUILD_2_RECOGNITION.md per the same rules; stop after for
  my device check." Then RW_BUILD_3 (Check-ins), RW_BUILD_4 (assistant upgrade), RW_BUILD_5 (AI quick
  wins) — each its own run, each with your live check.
