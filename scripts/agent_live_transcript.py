#!/usr/bin/env python3
"""
agent_live_transcript — record REAL conversations against the running stack.

    python scripts/agent_live_transcript.py                 # all scenarios
    python scripts/agent_live_transcript.py --only checkin

Unlike the pytest suite and the scale harness, this talks HTTP to
http://localhost:8090 as a real logged-in user, against the demo tenant, with the
REAL LLM provider — no fakes anywhere. Its job is evidence: it prints each turn
verbatim so the transcripts in `docs/AGENT_REBUILD/REPORT.md` are things that actually
happened, not things I believe would happen.

Each scenario names the bug it demonstrates, and prints an ASSESSMENT line that says
plainly whether the behaviour looks right, so a skim shows what to trust.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8090"
TENANT = "acme"
PW = "Passw0rd!demo"
BLURB = "read-only performance assistant"


def reset_llm_budget():
    """The metered gateway will refuse after a fixed number of calls per window, which
    looks exactly like a broken assistant. Clear it before recording."""
    for args, snippet in (
        (["-c"], "from apps.billing import atomic; atomic.reset_window('llm:global:calls')"),
        (["manage.py", "shell", "-c"],
         "from apps.billing import atomic, services;"
         "from apps.billing.models import AgentBudget;"
         "from apps.tenancy.models import Tenant;"
         f"t=Tenant.objects.get(slug='{TENANT}');"
         "[atomic.reset_window(services.tenant_cache_key("
         "t.id, services._BUDGET_COUNTER_PART, a, w, services._budget_period(w)))"
         " for a in ('chat','chat_phrase','planner')"
         " for w in (AgentBudget.Window.DAILY, AgentBudget.Window.MONTHLY)]"),
    ):
        try:
            subprocess.run(["docker", "compose", "exec", "-T", "web", "python"] + args + [snippet],
                           check=False, capture_output=True, timeout=60)
        except Exception:  # noqa: BLE001 — a convenience, never fatal
            pass


def clear_this_weeks_checkin(email):
    """Remove the actor's current-week check-in so a scenario can open a fresh one.

    Needed because the check-in action is deliberately non-destructive: once you have
    a check-in for the week it navigates you to it instead of asking for a mood. That's
    correct, but it means a scenario recorded after another scenario already created
    one has no pending question to demonstrate. Must be a HARD delete — the ordinary
    delete only stamps `deleted_at`, and the soft-deleted row keeps the (author, week)
    unique slot.
    """
    snippet = (
        "from apps.tenancy.context import tenant_context;"
        "from apps.tenancy.models import Tenant;"
        f"t=Tenant.objects.get(slug='{TENANT}');"
        "ctx=tenant_context(t.id); ctx.__enter__();"
        "from apps.identity.models import User;"
        "from apps.checkins.models import CheckIn;"
        f"u=User.objects.filter(email='{email}').first();"
        "qs=CheckIn.all_objects.filter(author_id=u.id);"
        "qs.hard_delete() if hasattr(qs,'hard_delete') else qs.delete()"
    )
    try:
        subprocess.run(["docker", "compose", "exec", "-T", "web", "python", "manage.py", "shell", "-c", snippet],
                       check=False, capture_output=True, timeout=60)
    except Exception:  # noqa: BLE001
        pass


def _post(path, body, token=None, timeout=90):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return {"_http_error": exc.code, "detail": exc.read().decode()[:300]}


class Chat:
    """One user's conversation — a real session, carried across turns."""

    def __init__(self, email):
        self.email = email
        out = _post("/api/auth/login", {"tenant_slug": TENANT, "email": email, "password": PW})
        if "access" not in out:
            raise SystemExit(f"login failed for {email}: {out}")
        self.token = out["access"]
        self.sid = None
        self.last = None

    def say(self, text):
        body = {"query": text}
        if self.sid:
            body["session_id"] = self.sid
        out = _post("/api/ai/chat", body, self.token)
        self.sid = out.get("session_id", self.sid)
        self.last = out
        answer = out.get("answer") or out.get("detail") or json.dumps(out)[:200]
        print(f"\n  \033[1muser\033[0m  › {text}")
        print(f"  \033[36massistant\033[0m ‹ {answer}")
        # The API deliberately does NOT serialize step params (they're internal,
        # server-resolved values), so assertions here read the step's action, feel and
        # human-facing summary — which is also all the SPA and the user ever see.
        for step in (out.get("plan") or {}).get("steps", []) or []:
            print(f"      · step: action={step.get('action')} feel={step.get('feel')} "
                  f"| {step.get('summary', '')[:120]}")
        return out

    def approve_last_step(self):
        plan = (self.last or {}).get("plan")
        if not plan or not plan.get("steps"):
            print("      ! nothing to approve")
            return None
        step = plan["steps"][0]
        out = _post(f"/api/ai/chat/plan/{plan['id']}/step/{step['id']}/approve", {}, self.token)
        print(f"      \033[32mapprove\033[0m → {json.dumps(out)[:220]}")
        return out


def answer_of(out):
    return (out.get("answer") or "").strip()


def steps_of(out):
    return ((out.get("plan") or {}).get("steps")) or []


def first_action(out):
    for step in steps_of(out):
        if step.get("action") == "clarify":
            return (step.get("params") or {}).get("clarify_action", "clarify")
        return step.get("action")
    return None


def verdict(label, ok, note=""):
    mark = "\033[32mOK  \033[0m" if ok else "\033[31mFAIL\033[0m"
    print(f"  [{mark}] {label}" + (f" — {note}" if note else ""))
    return ok


# ── scenarios ────────────────────────────────────────────────────────────────────


def scenario_checkin(results):
    """BUG 1 — the pending question that could never be answered."""
    print("\n" + "═" * 78)
    print("SCENARIO: a check-in follow-up question actually gets answered")
    print("  (before: replying '5' re-asked the same question, forever)")
    print("═" * 78)
    clear_this_weeks_checkin("ada@acme.test")
    chat = Chat("ada@acme.test")
    asked = chat.say("start my check-in")
    # The API doesn't serialize which action a clarify belongs to, so identify the
    # question by what it asks for — which is what the user sees anyway.
    results.append(verdict("the assistant asks for a mood",
                           any(s.get("feel") == "clarify" and "feeling this week" in s.get("summary", "")
                               for s in steps_of(asked))))
    answered = chat.say("5")
    steps = steps_of(answered)
    ok = (steps and steps[0].get("action") == "open_checkin"
          and steps[0].get("feel") == "confirm"
          and "5" in steps[0].get("summary", ""))
    results.append(verdict('a bare "5" fills the slot and completes the check-in', ok,
                           f"action={first_action(answered)}"))
    if ok:
        chat.approve_last_step()


def scenario_stuck_escape(results):
    """BUG 4 — the user can always escape a pending question."""
    print("\n" + "═" * 78)
    print("SCENARIO: a new command mid-question is obeyed, and cancel works")
    print("  (before: both were ignored and the question was re-asked)")
    print("═" * 78)
    clear_this_weeks_checkin("ada@acme.test")
    chat = Chat("ada@acme.test")
    chat.say("start my check-in")
    out = chat.say("give recognition to Priya Nair for her excellent work")
    results.append(verdict("a new command abandons the pending question",
                           first_action(out) == "give_recognition",
                           f"action={first_action(out)}"))

    clear_this_weeks_checkin("ada@acme.test")
    chat2 = Chat("ada@acme.test")
    chat2.say("start my check-in")
    cancelled = chat2.say("never mind")
    results.append(verdict("cancel clears the pending question",
                           not steps_of(cancelled) and "cancel" in answer_of(cancelled).lower()))


def scenario_invalid_answer(results):
    """BUG 1b — an invalid answer explains itself and does not loop."""
    print("\n" + "═" * 78)
    print("SCENARIO: a nonsense answer is explained once, then let go")
    print("  (before: the same question came back forever)")
    print("═" * 78)
    clear_this_weeks_checkin("ada@acme.test")
    chat = Chat("ada@acme.test")
    chat.say("start my check-in")
    first = chat.say("banana")
    results.append(verdict("says what it expects", "1" in answer_of(first) and "5" in answer_of(first)))
    second = chat.say("banana")
    results.append(verdict("does not ask a third time",
                           not any(s.get("feel") == "clarify" for s in steps_of(second))))


def scenario_out_of_team_recognition(results):
    """The product fix — recognise someone you do not manage."""
    print("\n" + "═" * 78)
    print("SCENARIO: a manager recognises a colleague OUTSIDE their team")
    print("  (before: 'not found' — lookup was team-scoped)")
    print("═" * 78)
    chat = Chat("ada@acme.test")
    out = chat.say("make a recognition for Priya Nair")
    ok = first_action(out) == "give_recognition" and steps_of(out)[0].get("feel") == "confirm"
    results.append(verdict("recognition for an out-of-team person is prepared", ok))
    if ok:
        chat.approve_last_step()


def scenario_do_the_same(results):
    """BUG 2 — "do the same for X" keeps the action."""
    print("\n" + "═" * 78)
    print("SCENARIO: 'do the same for <someone else>' repeats the RECOGNITION")
    print("  (before: it started a check-in)")
    print("═" * 78)
    chat = Chat("ada@acme.test")
    one = chat.say("give recognition to Priya Nair for mentoring the new joiners")
    two = chat.say("do the same for Ingrid Garcia")
    results.append(verdict('"do the same" repeats the recognition',
                           first_action(two) == "give_recognition",
                           f"action={first_action(two)}"))
    summary_two = steps_of(two)[0].get("summary", "") if steps_of(two) else ""
    results.append(verdict("…for the NEW person, not the previous one",
                           "Ingrid" in summary_two and "Priya" not in summary_two,
                           summary_two[:90]))
    del one


def scenario_reasoned_answer(results):
    """C — a specific question gets a specific, grounded answer."""
    print("\n" + "═" * 78)
    print("SCENARIO: a real question gets a real answer, not the capability blurb")
    print("═" * 78)
    # People on Ada's OWN team, so this scenario shows a reasoned answer. Asking about
    # someone outside her scope is a different (also correct) behaviour — see
    # scenario_scope_refusal.
    chat = Chat("ada@acme.test")
    out = chat.say("how is Akhil Menon doing this cycle?")
    ans = answer_of(out)
    results.append(verdict("not the capability blurb", BLURB not in ans))
    results.append(verdict("names the person asked about", "Akhil" in ans))

    cmp_out = Chat("ada@acme.test").say("compare Akhil Menon and Mei Patel")
    cmp_ans = answer_of(cmp_out)
    results.append(verdict("a comparison covers both people",
                           "Akhil" in cmp_ans and "Mei" in cmp_ans))


def scenario_scope_refusal(results):
    """The boundary — resolving a name never grants access to their data."""
    print("\n" + "═" * 78)
    print("SCENARIO: directory-wide actions, but data stays permission-scoped")
    print("═" * 78)
    chat = Chat("ada@acme.test")
    out = chat.say("how is Priya Nair doing?")
    ans = answer_of(out).lower()
    leaked = [w for w in ("at risk", "on track", "behind pace", "attainment") if w in ans]
    results.append(verdict("out-of-scope performance data is refused", not leaked,
                           f"leaked {leaked}" if leaked else "honest refusal"))


def scenario_unknown_name(results):
    """A — an unknown name is said plainly, not deflected."""
    print("\n" + "═" * 78)
    print("SCENARIO: a name that doesn't exist is reported as such")
    print("═" * 78)
    out = Chat("ada@acme.test").say("how is Zebediah Quartermain doing?")
    ans = answer_of(out)
    results.append(verdict("says it couldn't find the name", "find" in ans.lower()))
    results.append(verdict("not the capability blurb", BLURB not in ans))


SCENARIOS = {
    "checkin": scenario_checkin,
    "escape": scenario_stuck_escape,
    "invalid": scenario_invalid_answer,
    "recognition": scenario_out_of_team_recognition,
    "dosame": scenario_do_the_same,
    "reasoning": scenario_reasoned_answer,
    "scope": scenario_scope_refusal,
    "unknown": scenario_unknown_name,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=sorted(SCENARIOS), nargs="*")
    args = parser.parse_args()

    reset_llm_budget()
    chosen = args.only or list(SCENARIOS)
    results: list[bool] = []
    for name in chosen:
        try:
            SCENARIOS[name](results)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 — one broken scenario shouldn't hide the rest
            results.append(verdict(f"scenario {name}", False, f"{type(exc).__name__}: {exc}"))

    passed = sum(results)
    print("\n" + "═" * 78)
    print(f"LIVE TRANSCRIPT: {passed}/{len(results)} assertions held "
          f"(real HTTP, real LLM, tenant {TENANT!r})")
    print("═" * 78)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
