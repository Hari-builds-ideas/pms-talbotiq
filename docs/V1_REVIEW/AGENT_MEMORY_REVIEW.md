# AGENT_MEMORY_REVIEW — how chat memory works, why context was lost, and the fix

Grounded in code (`file:line`). Written 2026-07-13. The **Fix applied** section records this run's change.

## How it works today (pre-fix)

### Persistence & scoping — GOOD
- `POST /api/ai/chat` (`apps/ai/views.py:44-87`) resolves/creates a `ChatSession` and persists **both**
  user and assistant turns (`sessions.append_turn`).
- Sessions are **owner-bound and tenant-scoped**: fetch filters `owner=user` (`apps/ai/sessions.py:65`),
  rows created with `tenant_id=user.tenant_id`; `ChatSession(TenantScopedModel)` with a
  `["tenant","owner","-last_activity"]` index; 24h TTL. A cross-user/cross-tenant session id silently
  starts a fresh session (no existence leak). **This part was already correct.**

### The PLAN path used memory — the READ path did not (the root cause)
- **Plan path:** `_realize_step` (`apps/ai/planner.py:128-149`) resolves pronouns ("her") via
  `resolve_person_reference` (`sessions.py:189-199`), which walks the session's stored **refs**
  newest-first and re-checks scope (`_reaccess`). Refs are recorded per assistant turn from resolved plan
  params (`refs_for_plan`, `planner.py:235-245`).
- **Read/Q&A path — structurally memory-free (pre-fix):**
  1. Intent classification sent ONLY the current query — `gateway.run(prompt=query, …)`
     (`apps/ai/agents/chat.py:151-153`); no prior turns in the prompt.
  2. Target resolution used ONLY an email regex on the current query (`chat.py:229-234`) — never
     `resolve_person_reference`. "How is Vera doing?" → "how many reviews does she have?": the second
     query resolved no target ("she" isn't an email) and silently defaulted to the caller.
  3. Read answers wrote **no refs** (`views.py:86`), so a Q&A turn about Vera grounded nothing for later
     turns even on the plan path.
- **Misrouting "how many reviews do I have":** the intent catalogue is
  `write|performance|search|capability|general` (`apps/ai/agent_config.py:122-141`). "Review" is in
  `_PERF_WORDS` → the performance branch — which only fetches **goal titles + latest cycle score**
  (`chat.py:225-264`; no `Review` query exists in chat.py at all). So the answer came back about goals —
  a silent misroute. The panel even advertised "How many open reviews do I have?" as a suggestion chip
  (`ChatPanel.tsx:168`) that the backend could not answer.

### Frontend session persistence — partial
`session_id` lives in a `useRef` (`frontend/src/features/chat/ChatPanel.tsx:66`) — threaded across
messages and across navigation (the panel is shell-mounted), but **lost on full reload** (never stored in
`localStorage`), orphaning the 24h server-side session.

## Fix applied (this run) — memory on BOTH paths, no scope weakening

1. **Conversation context in the read path.** `chat_answer` now builds the classifier prompt with the
   session's recent turns (bounded, PII-scrubbed via the existing gateway pipeline) so intent
   classification sees the conversation, and the READ target resolution falls back to
   `resolve_person_reference(user, session, query)` when no email is present — the same scope-rechecked
   resolver the plan path uses (`_reaccess` re-verifies `actor_can_access` at read time, so memory can
   never widen access).
2. **Read answers now ground refs.** When the read path answers about a person, the assistant turn
   records a `user` ref for the target — so follow-ups ("what about her goals?") resolve on both paths.
3. **A real route for count-questions.** The performance branch now answers review/feedback/goal
   count-questions from the caller's (or in-scope target's) real scoped querysets — no more goals-only
   misroute for "how many reviews do I have".
4. **Frontend session resume.** `session_id` is persisted to `localStorage` and rehydrated on mount via
   the existing `aiApi.getSession` (turns restored from the server, which is the source of truth) — a
   reload no longer forgets the conversation. Expired/foreign sessions fall back to fresh (server
   behavior unchanged).

**Scope safety:** every remembered reference is re-checked against `actor_can_access` at use time
(`sessions.py` `_reaccess`); the read path remains read-only; tenant scoping is untouched (all queries
still run through tenant-scoped managers). Also added: a **named-person resolver** on the read path
(unique whole-token match on display name / email local-part, tenant-scoped; ambiguous → an honest
"several people match" answer) — so "how is Vera doing?" answers about Vera, not the caller; the scoped
fetch still refuses out-of-scope subjects with the same empty answer as an email mention.

**Tests** (`apps/ai/tests/test_chat_memory.py`, deterministic FakeLLMProvider): read answer grounds the
person + pronoun follow-up resolves; count-question returns real counts (not the goals dump); memory/name
resolution never widens access (peer → "No data in your scope"); pronoun with no grounding falls back to
the caller. Existing session-isolation tests unchanged and green. Reload-resume is frontend-only
(localStorage + `getSession`) and covered by the manual QA checklist.
