# The prompt to paste into Claude Code

Drop all six BUILD_*.md files into the repo root (or a `builds/` folder), then paste this:

---

You are running unattended in AUTO MODE on Claude Opus (do NOT switch models), extra effort, for a long
continuous session. I have placed a production-hardening build series in the repo: BUILD_0_READ_FIRST.md
(the operating contract) and BUILD_1 … BUILD_5. Execute the WHOLE series, strictly in order.

Start now:
1. Read BUILD_0_READ_FIRST.md IN FULL — it is the rulebook for every build (sources of truth, the
   PROGRESS.md / DECISIONS.md / QUESTIONS.md living docs, "done = real + verified", the guardrails that
   never relax, the Groq-free-tier discipline, commit/push per phase).
2. Create PROGRESS.md, DECISIONS.md, QUESTIONS.md if absent; update them continuously.
3. Execute BUILD_1, every phase in order, to completion. Then BUILD_2, then BUILD_3, BUILD_4, BUILD_5 —
   each fully, in order. Do not start a build until the previous one is committed, pushed, and green.

Hard rules (full detail in BUILD_0): this is CODE-ONLY, repository-level work against the EXISTING stack
(existing MySQL, Redis, Celery, React) — do NOT attempt to provision cloud infra, a managed DB, a real
read replica, k8s, TLS, or a vault; write the code that is READY for them and verify against the existing
single instance. Never weaken RBAC/scope/tenant isolation, HITL, anonymisation, or the graceful AI
degradation. Keep AI output real through the one LLMGateway. This series should need almost no real LLM
calls — use the FakeLLMProvider in tests and reuse seeded artifacts; never burn the Groq free tier. The
backend suite (was 1059) must never regress and grows with every change; frontend build/tsc/lint stay
clean. After each phase: green + verified → commit AND push (never force; rejected push → write a BLOCKER
and continue local commits). `.env`/secrets NEVER staged — scan the staged diff before every commit.

Do NOT stop to ask. A genuine decision → log it in QUESTIONS.md, take the safe default, record it in
DECISIONS.md, and CONTINUE. A hard blocker on one task → write BLOCKER_<build>_<phase>.md, note it in
PROGRESS.md, leave prior work green/committed/pushed, and continue with the next independent task. Do NOT
stop after a single feature — continue until the entire series is complete and verified.

At the end of each build write its <BUILD>_REPORT.md, then proceed to the next automatically. At the very
end write SERIES_COMPLETE_REPORT.md: everything done, verified [test]/[live]/[build], the commit list,
all QUESTIONS/DECISIONS/BLOCKER, final test counts, the visual/subjective calls that need my eye, and an
explicit statement that the only remaining work is infra provisioning + plugging in the Gemini key (both
my actions, outside this series).

Begin with BUILD_0, then BUILD_1 Phase 1.1. Go.

---

## A note on running it
- The series is designed to run continuously. If your Claude Code session has a per-run cap, just paste
  the same prompt again — it reads PROGRESS.md and continues where it left off (the living docs are the
  resume point). Tell it: "Read PROGRESS.md and continue the build series where it left off."
- Check in at the BUILD boundaries (when a BUILD_N_REPORT.md appears). Especially after BUILD_5's UX
  work — that's where YOUR eyes on the running app matter most.
