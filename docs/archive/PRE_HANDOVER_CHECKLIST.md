# Pre-Handover Verification — walk this before telling the testing team it's ready

The test suite being green is not proof the app works — your own clicking has caught real bugs it missed.
Walk this yourself on http://localhost:8090 (hard-refresh first). Tick each. Anything that fails =
a fix prompt before handover.

## The two headline fixes you asked for
- [ ] Employee login: clean read-only pages, NO "not authorized" walls on any button you can see.
- [ ] Chat: drag-resizes, stays open when you navigate, survives a reload, content sits beside it.

## AI agent (where the bug just showed up)
- [ ] "Make a review for Vera" → draft runs → "Open" ACTUALLY NAVIGATES to the review page (does not
      paste text into the chat). ** KNOWN BROKEN — fix before handover. **
- [ ] Agent answers the right thing (a review-draft click doesn't return a goals list).
- [ ] AI runs on the Gemini key (one real action responds).
- [ ] Agent memory: ask a follow-up with "her/that" — it resolves correctly.

## Core per role (log in as each: admin / priya HRBP / ada manager / an employee)
- [ ] Dashboard loads, no crash, numbers look real (not all-empty, not all-identical).
- [ ] Goals: open a person → shows real varied progress (% + bar), not "not recorded" for everyone.
- [ ] Create a goal as manager → it SAVES (no "outside your access scope").
- [ ] Record a KPI actual → the number/bar updates live (no reopen needed).
- [ ] Reviews: open, request AI draft, lands PENDING, you can finalize → UI updates.
- [ ] 360 / feedback: open a cycle, the state changes reflect without reopening.
- [ ] Check-ins, recognition: open, create one, it appears.
- [ ] Every dashboard list item click → goes to the right record (no dead links).

## Data cleanliness (matters for the demo)
- [ ] Reseed fresh, then confirm: no duplicate/junk goals ("BUG1 self goal" test data is gone),
      no doubled KPIs, people show a believable spread of progress.

## Handover package (what the testing/deployment team receives)
- [ ] .env.example is your PMS's real vars (Django, DB, the Redis URLs, Gemini, METRICS_TOKEN, EMAIL_*),
      placeholders only, no secrets.
- [ ] DEPLOYMENT_HANDOVER.md reads clearly + has the honest "not-wired" list.
- [ ] FINAL_REPORT.md + ROADMAP.md skimmed so you know what's built vs staged (payments, auth-cookie).

## Verdict
- If everything above ticks: tell the testing team it's ready for them to test.
- If any fail: those are the fix list first. The "Open draft" navigation bug is already on it.
