# QA_NIGHT — progress log

Overnight machine-checkable QA pass (no rendered UI — visual half is Hari's tomorrow).
Method: live HTTP probes at :8090 as all four roles + a second tenant (globex) for
isolation; safe fixes committed per fix; risky findings written up in BUGS_FOUND.md.

## Status

| Step | State | Notes |
|---|---|---|
| Endpoint inventory | DONE | all apps/*/urls.py mapped (~120 routes, 17 modules) |
| Second tenant (globex) | DONE | gadmin/gmgr/gemp@globex.test |
| Sweep A: goals/reviews/feedback/checkins/recognition | DONE | **63/63** after 3 fixes (see below) |
| Sweep B: org/jd/analytics/audit/approvals/bell/admin | DONE | **63/63** — no code bugs (2 alarming-looking results were by-design scope) |
| Sweep C: auth + Phase-2 + AI agent | DONE | **18/18** + Phase-2 re-run **49/49** |
| Cross-tenant isolation (all modules) | DONE | **29/29** — uniform 404, no oracles, no foreign rows, AI blind cross-tenant |
| New pytest integration tests | DONE | audit: priority flows already covered; +4 regression tests for tonight's bugs |
| BUGS_FOUND.md + QA_NIGHT_REPORT.md | DONE | 3 bugs fixed (1 HIGH), 2 observations written up |

## Log

- 2026-07-14 00:0x — inventory built; starting globex tenant + sweep harness.
- Sweep A ran 63 role/negative/integrity checks live. Three REAL bugs found + fixed:
  - `478e3d2` fix(goals): non-numeric KPI actual was a **500** (Decimal coercion) and
    left a ghost "actual.recorded" audit row — now validated → 400, no audit, no write.
  - `15c5dad` fix(recognition): message cap (model says 1000, TextField isn't
    DB-enforced) — a 50k-char kudos landed in the feed; now 400.
  - `9881297` fix(reviews): **repeat finalize bypassed an in-flight approval route**
    (review FINALIZED while its route was IN_PROGRESS — approval matrix defeated).
    Now 409 ACTIVE_ROUTE. Regression tests added for all three.
- Everything else clean: role scoping (own/team/BU), weight/title validation,
  malformed JSON, state-machine legality (start-edit→submit→approve→finalize),
  360 open/give/close ordering, self-recognition + self-rating blocks, check-in
  duplicate-week handling, reaction palette.
- Note: probe corrupted one demo review pre-fix (FINALIZED + IN_PROGRESS route) —
  repaired (stale route CANCELLED); reseed also ran mid-night.
- Sweep B 63/63 (org/JD/analytics/audit/approvals/cycles/billing/admin): all denials
  and negatives clean; employee org-export verified scoped (own line, 5 nodes);
  audit console is GET-only (405 on POST/DELETE).
- Sweep C 18/18 (auth edges + AI): fail-closed without tokens; globex↔acme logins
  don't cross; AI schema role-filtered, session/plan isolation holds, destructive ask
  refused, **Open-the-draft navigation fix holds live**, colleague ask leaks nothing.
- Cross-tenant 29/29; Phase-2 re-run 49/49.
- Final gates (pass 1): backend **1480 passed / 0 failed** (clean isolated run; one earlier
  run failed en masse purely from demo_ready recreating containers mid-suite) ·
  demo_ready **57/57 DEMO READY** · stale-route repair applied · reseeded.

## Pass 2 (deeper sweep — modules pass 1 skipped)

| Sweep | State | Notes |
|---|---|---|
| D: succession/career/one-on-ones/notifications | DONE | **28/28** — succession fully shut to employees (no access anywhere); career/1:1 own-scope holds; no bug |
| E: JD/review/feedback/approvals **lifecycle** sub-endpoints | DONE | **34/34** — found + fixed **BUG-N5** (JD non-object body → 500 on submit/export, `f5cc539`) |
| Cross-tenant on new modules (succession/career/1:1/JD-lifecycle) | DONE | **11/11** — every ACME id as globex admin → 404, no foreign rows |

- Pass-2 total: 73 new live checks; 1 MEDIUM bug fixed (BUG-N5) + regression test.
- Reseeded after pass-2 probes; grand total **5 bugs found & fixed** across both passes.
- Final gates (pass 2): backend **1482 passed / 0 failed** (clean isolated run; +2 new
  regression tests since pass 1) · demo_ready **57/57 DEMO READY**.
