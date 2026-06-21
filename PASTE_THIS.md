# Paste this into Claude Code to run the final push (BUILD_6 → 9)

Drop BUILD_6, BUILD_7, BUILD_8, BUILD_9 into the repo (alongside the existing BUILD_0_READ_FIRST.md),
then paste:

---

You are running unattended in AUTO MODE on Claude Opus (do NOT switch models), extra effort, for a long
continuous session. The BUILD_1–5 series is complete and green. Now execute the FINAL PUSH: BUILD_6 →
BUILD_7 → BUILD_8 → BUILD_9, strictly in order.

Start now:
1. Read BUILD_0_READ_FIRST.md IN FULL — its contract still governs every build (sources of truth; the
   PROGRESS.md/DECISIONS.md/QUESTIONS.md living docs; "done = real + verified"; never weaken RBAC/scope/
   tenant isolation, HITL, anonymisation, the succession employee-404, or graceful AI degradation;
   backend suite never regresses and grows; frontend build/tsc/lint clean; commit AND push per phase
   (never force; rejected push → BLOCKER + continue local); .env never staged — scan the staged diff
   first; almost zero LLM calls — use FakeLLMProvider in tests, reuse seeded artifacts, never burn the
   Groq free tier).
2. Execute BUILD_6 (stabilize: fix the org-chart ".for is not iterable" crash + sweep that bug class +
   close the three Q1 large-tenant items), every phase to completion, committed/pushed/green.
3. Then BUILD_7 (the two Tier-3 features — review section comments + nine-box drag-reposition,
   BACKEND-FIRST with tests), then BUILD_8 (mobile foundation: extract the shared layer WITHOUT
   regressing the web app, Expo scaffold, secure auth, shell, My dashboard), then BUILD_9 (the rest of
   the mobile self-service screens + hardening). Each fully, in order; don't start a build until the
   previous is committed, pushed, and green.

This is CODE-ONLY against the existing stack — do NOT provision cloud infra, a managed DB, a real
replica, k8s, TLS, a vault, an EAS build, or store accounts; write the code that is READY for them
(e.g. the device-register endpoint, the expo-notifications registration) and verify against the existing
stack / Expo. For mobile, the real bar is "runs in Expo against the live backend", not "compiles".

Do NOT stop to ask. A genuine decision → log it in QUESTIONS.md, take the safe default, record it in
DECISIONS.md, continue. A hard blocker on one task → BLOCKER_<build>_<phase>.md + note in PROGRESS.md,
leave prior work green/committed/pushed, continue with the next independent task. Do NOT stop after a
single feature — continue until the whole push is done.

At the end of each build write its <BUILD>_REPORT.md, then proceed to the next automatically. At the very
end write FINAL_PUSH_COMPLETE_REPORT.md: everything done, verified [test]/[live]/[build], the commit
list, all QUESTIONS/DECISIONS/BLOCKER, final backend+frontend+mobile test counts, the screens that need
my eye, and an honest statement of what remains (infra, the Gemini key, EAS/store accounts for a real
mobile release, and any mobile screen not finished in the window).

Begin with BUILD_6 Phase 6.1 (the org-chart crash — reproduce it live first). Go.

---

## How to run it continuously
- If a session caps out, paste: "Read PROGRESS.md and continue the final-push build series where it left
  off." The living docs are the resume point.
- Check in at each BUILD_N_REPORT.md. The two places YOUR manual testing matters most: after BUILD_6
  (confirm the org chart + every screen no longer crash) and during BUILD_8/9 (run the mobile app in
  Expo on a real phone and click through — that's the bar, and it's yours to judge).
