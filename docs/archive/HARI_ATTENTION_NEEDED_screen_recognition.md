# HARI_ATTENTION_NEEDED — Recognition recompose (File D, screen 2)

**Status:** NOT recomposed this run — deliberately (visual recompose needs your eyes; blind-shipping a
working screen risks an invisible regression). Plan handed over for a fast one-screen-with-approval pass.

**Branch to cut:** `hari/recognition-recompose`.

## Target composition — from `overnight/OVERNIGHT_D_HIGH_IMPACT_SCREENS.md`
- Hero: a recent notable **moment** (the real kudos with the fullest story).
- **"Moments" feed:** each kudos as a moment — avatars, the story text prominent, the value category a
  small pill, timestamp muted. **Not a form. Not a card-inside-card grid.**
- **"Give recognition"** as a compact composer (not the dominant element); use the AI-suggested category
  from `agent_config` if available.
- Filter row (giver / recipient / category / team) — real data only.

## Non-goals / real-data rule
No invented leaderboards / streaks / weekly winners (no real source — skip). Reaction emoji stay
(they're the real API value). Everything from existing recognition endpoints; no new backend.

## Note — this pairs with the new agent action
File A added a **`give_recognition`** chat action (propose → human approve → `create_recognition`). The
recomposed composer and the chat action are the same underlying audited path — worth showing together.

**Files:** `frontend/src/features/recognition/`.
