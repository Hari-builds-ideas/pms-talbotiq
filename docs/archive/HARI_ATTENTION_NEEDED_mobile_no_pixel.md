# HARI_ATTENTION_NEEDED — mobile (no-pixel branches, File G)

Two mobile improvements landed as **review branches** (DO NOT merge — mobile pixels
need your device). Both are structurally testable and shipped green (bundle + lint +
tsc + tests), because they're **routing** and **API wiring**, not visual composition.

## Recommended review order
1. **`hari/mobile-tab-ia`** (G1) — the bigger UX shift. Tab IA recut to mirror the web
   sidebar: **Home · Goals · Reviews · Recognition · You** (Reviews + Recognition
   promoted from "More"; Feedback + Career moved into the "You" overflow; route paths
   unchanged so no deep-link breaks). Routing/config only.
2. **`hari/mobile-chat-agent-v2`** (G2) — the larger surface change. The mobile chat
   now consumes the agent V2 plan/step endpoints (Ask vs Plan modes; an inert
   checklist with Approve · Skip · Explain; session id in `expo-secure-store`). API
   wiring only; same invariants as the web.

Each branch has its own `REVIEW_NOTES.md` (before/after map, the flow to try, the
launch command, network-log expectations).

## Why no merge
The visual recompose of each screen still waits for your device — the agent can't see
pixels. These two are the parts that DON'T need eyes; do the tab-IA device pass first,
then the chat-agent pass, then merge each once they look right on the sim.

## Green, but "device-verified" is still on you
- Verified here: `npx tsc --noEmit`, `npx expo lint`, `npx expo export` (iOS + web),
  and the added tests (`frontend/src/test/mobileTabs.test.ts`,
  `frontend/src/test/chatPlanApi.test.ts`, run under the web vitest via `@shared`).
- NOT verified here: how it looks / feels on a real device, and the live
  plan→approve round-trip over the network (documented in the G2 REVIEW_NOTES; run it
  on the sim against the dev backend).

## Guardrails honored (both branches)
No RBAC change, no new endpoint, no fabricated data. The web agent's invariants
transfer verbatim to mobile (planner emits action names only; params resolve
server-side; embedded instructions are data). Neither branch merges.
