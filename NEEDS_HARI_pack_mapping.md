# NEEDS_HARI — feature-pack mapping for the AI agents (Module 11)

> ## ✅ RESOLVED — Hari's decision: **Agent 1 is now PREMIUM (FULL_AI).**
> STARTER = `{agent2, chat}`; FULL_AI = `{agent1, agent2, agent3, agent4, agent5,
> chat, jd_generator, career_roadmap}`. Applied in `apps/billing/packs.py`
> (`FEATURE_PACKS` STARTER = `{agent2}`, `PACK_FEATURES` STARTER = `{agent2, chat}`)
> and all billing/feature-flag tests; full suite green. Commit:
> "Agent 1 → FULL_AI (commercial repackaging)". The original analysis is kept below
> for the record; the "keep Agent 1 in STARTER" safe-default it recommended is now
> superseded by this decision.

**Status:** ✅ RESOLVED (was: non-blocking; a safe default was chosen and the build proceeded).

## The question
Which pack should each AI feature live in (STARTER vs FULL_AI)? There is a small
internal contradiction between two parts of the spec:

- **The locked Module-1 pack registry** (`apps/billing/packs.py`, shipped + tested
  since Module 1) maps: `STARTER → {agent1, agent2}`, `FULL_AI → {agent1..agent5}`.
  So **Agent 1 is in STARTER**.
- **`docs/tonight_build.md` Module-10 decision 3** says: *"Agent 2 + Chat available
  in STARTER per the pack registry; Agents 1/3/4, JD, Career → FULL_AI."* That line
  puts **Agent 1 in FULL_AI** — contradicting the registry it cites.

## The safe default I chose (and built on)
I kept the **existing Module-1 registry unchanged** (Agent 1 stays in STARTER) and
only *added* the new non-agent feature codes:

- `STARTER` → `{agent1, agent2, chat}`
- `FULL_AI` → `{agent1, agent2, agent3, agent4, agent5, chat, jd_generator, career_roadmap}`

Rationale:
1. The registry is the source of truth the spec itself defers to ("per the pack
   registry"), and changing Agent 1's pack would break the Module-1 billing tests
   that assert `STARTER → {agent1, agent2}`.
2. The **headline commercial property is preserved**: a STARTER tenant has
   **agents 3–5 locked** and the paid generative seams (`jd_generator`,
   `career_roadmap`) locked; upgrading to FULL_AI unlocks them instantly. This is
   exactly the Module-11 DoD ("a STARTER tenant has agents 3–5 locked … upgrade →
   flags flip"), and it passed live.
3. `chat` was placed in STARTER per Module-10 decision 3 (Chat is the Fast,
   read-only assistant).

## What Hari needs to decide
- Should **Agent 1 (Review Assistant)** be a STARTER feature (current) or a FULL_AI
  feature (as the M10 prose suggests)? This is a **commercial packaging** call, not
  a technical one — flip it by editing one line in `apps/billing/packs.py`
  (`PACK_FEATURES`/`FEATURE_PACKS`) and updating the Module-1 billing test
  expectation. No schema or code-flow change.
- Confirm `chat` belongs in STARTER and `jd_generator` / `career_roadmap` in
  FULL_AI (current).

Until you say otherwise, the build uses the mapping above. Module 10 wires
`requires_entitlement(...)` gates against these codes, so a change here just moves
which tenants can reach those agents — no rework.
