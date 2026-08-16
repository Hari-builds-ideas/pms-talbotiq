# B_CONVERSATION_STATE.md — fix the broken multi-step task flow

This is the worst set of bugs and the reason it "feels dumb." The conversation state-machine that runs
multi-step tasks (recognition, check-in, feedback, review draft) is broken: pending questions never get
answered, "do the same" loses the action, intents misroute, and there's no escape from a stuck task.

## Bug 1 — PENDING SLOT IS STUCK (top priority)
Reproduced: assistant asks "how are you feeling this week (1–5)?" → user types "5" → the SAME question
repeats → "start my check-in, mood 4" → repeats again → forever. The pending slot never captures input.

**Fix:** implement the pending-question as a real slot-filling step in the task state:
- When a task step is AWAITING a specific detail, the task holds: which task, which step, which field is
  pending, and how to validate it.
- The user's next message is first offered to the pending slot's PARSER. If it's a valid answer (e.g. a
  number 1–5 for mood, a name for "who to recognise", free text for a note), FILL the field, advance the
  step, and complete or continue the task. Do NOT re-ask on a valid answer.
- If the answer is invalid (e.g. "banana" for a 1–5 mood), say specifically why and re-ask ONCE with the
  expected format — don't silently loop.
- Verify live: open a check-in → answer "4" → the check-in is CREATED and confirmed (mood 4), no repeat.
  Also "start my check-in, mood 4" in one message → parses mood 4 and completes.

## Bug 2 — "DO THE SAME FOR X" LOSES THE ACTION
Reproduced: after "give recognition to Priya Nair", "do the same for Ingrid Garcia" started a CHECK-IN.

**Fix:** track the last COMPLETED task's action type in session state. "do the same for <person>" (and
"same for X", "now do X too") repeats that SAME action type with the newly-resolved person (via the A
resolver, company-wide). Verify: recognition to Priya → "do the same for Ingrid" → a RECOGNITION for
Ingrid (resolved company-wide), not a check-in.

## Bug 3 — INTENT ROUTING
Reproduced: "make a recognition for Ingrid Garcia" did not start a recognition.

**Fix:** each command routes to the action it names. Build/repair a clear intent map:
- recognition: "recognise/recognize/give recognition/kudos/shout out/praise <person>"
- check-in: "check-in", "start my check-in", "log my mood"
- feedback request: "request feedback", "ask for feedback on <person>"
- review draft: "draft a review for <person>"
- data/question: "how is <person>", "who's behind", "compare", etc.
Disambiguate verbs so "recognition" never lands in "check-in". Add tests per intent → correct task.

## Bug 4 — ESCAPE A STUCK STATE
A user must never be trapped. While a question is pending and the user sends a message:
- If it's a valid answer to the pending slot → fill it (Bug 1).
- If it's clearly a NEW command ("make a recognition for Ingrid Garcia", "cancel", "never mind") →
  cleanly ABANDON the pending task and start the new one (or cancel). NEVER ignore it and re-ask.
- Support an explicit "cancel"/"stop" that clears the pending task.
- Verify: mid-pending check-in, "make a recognition for Ingrid Garcia" → abandons the check-in and starts
  that recognition.

## Keep the HITL gate
All of this preserves the approval gate: an action still presents a plan step the user confirms before it
commits (the "Approve"/post step). Slot-filling supplies the details; the human still approves the action.

## Tests (add all)
pending-slot-captures-valid-answer, invalid-answer-re-asks-once-not-loops, do-the-same-repeats-action,
each-intent-routes-correctly, new-command-mid-pending-abandons-and-starts, explicit-cancel-clears.

## Done when
Follow-up questions get answered and tasks complete; "do the same for X" repeats the right action for any
company-wide person; every intent routes correctly; the user can always escape a pending state; HITL
intact; all tests green. Logged in PROGRESS.md.
