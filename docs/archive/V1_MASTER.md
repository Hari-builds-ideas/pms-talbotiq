# V1_MASTER.md — unattended: redesign goals → Gemini → simplify → polish → deploy → handoff docs

**Context:** final push before a July 16 demo. The author (Hari) is resigning, so this also produces
complete handoff documentation. A previous simplification attempt was REJECTED because it only added a
status tag to the same complex Goals/OKR screen. This run must do a REAL redesign, verified against how
real tools work, and must not overclaim.

**The one thing that matters most:** the Goals/OKR screen and the metrics must be simple enough that a
non-technical SME manager understands any screen in ten seconds without training. If a change doesn't
achieve that, it isn't done.

**Work fully autonomously.** Do not stop per feature. Make every change, keep tests green, commit per
change, only stop at the very end with a report + a testing checklist Hari runs later. If ambiguous, make
the SIMPLEST choice for a non-expert user, note it in QUESTIONS, keep going. Do NOT claim something is
done unless it truly matches the intent below — no "I did what you asked" when the screen is unchanged.

## Iron rules (do not weaken)
- Never break a working feature. Real data only; honest empty states.
- Deferred/removed features are HIDDEN from the UI, not deleted — document how to re-enable for v2.
- Keep backend + frontend tests green; commit per change; never leave the build red.
- Free-tier only for deploy; if a step costs money, use the free path and note it.
- Never commit secrets; never log into Hari's cloud accounts — prepare + document instead.

## Build files, IN ORDER
1. `V1_A_SIMPLIFY.md` — **RESEARCH real tools first, then REBUILD Goals/OKR** (% + colored bar per goal,
   details hidden); **REMOVE T-score from the v1 UI entirely** (code kept for v2); remove nine-box/
   calibration/succession/career from the v1 UI (code kept); simplify analytics + dashboards.
2. `V1_E_GEMINI.md` — write a Gemini provider, add the `GEMINI_API_KEY` placeholder to `.env.example`,
   use Gemini's best model, keep OpenAI/Groq switchable, verify end to end.
3. `V1_B_POLISH.md` — favicon, logo, premium login, consistent branding, calm empty states.
4. `V1_C_DEPLOY_DEMO.md` — free demo deploy: Vercel (frontend) + Render (backend) — prepare files +
   one-click instructions; do not deploy on Hari's behalf.
5. `V1_D_HANDOFF_DOCS.md` — complete docs/handoff/ so someone else can continue (v1-vs-v2 scope with
   re-enable steps, how it was built, dev setup, deployment + production path, mobile = deferred to v2).

Work 1 → 2 → 3 → 4 → 5. Do all of it. Only stop at the end.

## Final output
- Update `PROGRESS_V1.md` after each file.
- End with `V1_HANDOFF_REPORT.md`: what actually changed (be honest, show before/after of the Goals
  screen), what was removed vs kept, the Gemini wiring + how Hari pastes the key, the deploy click-through,
  the exact testing checklist for Hari, and any QUESTIONS. Do not overclaim — if something is partial,
  say so.
