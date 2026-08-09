#!/usr/bin/env python
"""
agent_selftest — run the FINAL2 prompt bank and report a per-category table.

    docker compose exec web python manage.py shell -c "exec(open('scripts/agent_selftest.py').read())"
    docker compose exec web python scripts/agent_selftest.py --tenant acme
    docker compose exec web python scripts/agent_selftest.py --tenant acme --live --cat "small talk"

**It spends nothing by default.** The deterministic classifier stands in for Gemini, so
every run exercises the real routing, the real tools, the real scope checks and the real
approval gate against the real database — the parts that are ours — with no API call at
all. `--live` swaps in the configured provider for a subset when you want to see what the
model actually does; that is the only mode that costs money, and it prints what it is
about to spend before it does.

Why a second harness when `agent_eval.py` exists: that one asks "is the ANSWER good",
which needs a model and a large tenant. This asks "does the message ROUTE correctly" —
does a team question reach the team, does an out-of-scope name get refused, does small
talk get the redirect, is a write still a plan. Routing is deterministic, so it can be
checked for free, on a fifteen-person tenant, as often as you like.

Exit code 0 = every category passed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402

from apps.ai.agents.chat import chat_answer  # noqa: E402
from apps.ai.selftest import check_scope, judge  # noqa: E402
from apps.ai.models import ChatPlan, ChatSession, ChatTurn  # noqa: E402
from apps.ai.planner import refs_for_plan  # noqa: E402
from apps.ai.sessions import append_turn  # noqa: E402
from apps.identity.models import User  # noqa: E402
from apps.rbac.scope import actor_can_access  # noqa: E402
from apps.tenancy.context import tenant_context  # noqa: E402
from apps.tenancy.models import Tenant  # noqa: E402

BANK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "docs", "FINAL2", "test_bank.jsonl")

def load(path, only_cat=""):
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "_comment" in row or (only_cat and row.get("cat") != only_cat):
                continue
            rows.append(row)
    return rows


def pick_actors(tenant):
    """A manager with reports, one of their reports, an employee, an HRBP — and a person
    the manager genuinely cannot read. All discovered, so the bank holds no names."""
    managers = [m for m in User.objects.filter(role="MANAGER", is_active=True)[:200]
                if User.objects.filter(manager_id=m.id, is_active=True).exists()]
    if not managers:
        raise SystemExit(f"tenant {tenant.slug!r} has no manager with reports — seed it first")
    manager = max(managers, key=lambda m: User.objects.filter(manager_id=m.id).count())
    reports = list(User.objects.filter(manager_id=manager.id, is_active=True)[:5])

    stranger = next(
        (u for u in User.objects.filter(is_active=True)[:400]
         if u.id != manager.id and not actor_can_access(manager, u)), None)
    hrbp = User.objects.filter(role="HRBP", is_active=True).first() or manager
    return {
        "manager": manager, "employee": reports[0], "hrbp": hrbp,
        "_reports": reports, "_stranger": stranger,
    }


def _typo(name):
    parts = name.split()
    if len(parts) < 2 or len(parts[-1]) < 4:
        return name + "e"
    last = parts[-1]
    return " ".join(parts[:-1] + [last[:-2] + last[-1] + last[-2]])


def _duplicate_name(default):
    from django.db.models import Count

    row = (User.objects.filter(is_active=True).values("display_name")
           .annotate(n=Count("id")).filter(n__gt=1).order_by("display_name").first())
    return row["display_name"] if row else default


def fill(text, a, dup):
    reports = a["_reports"]
    second = reports[1] if len(reports) > 1 else reports[0]
    stranger = a["_stranger"]
    return (text
            .replace("{report2}", second.display_name)
            .replace("{report}", reports[0].display_name)
            .replace("{stranger}", stranger.display_name if stranger else "Nobody Atall")
            .replace("{typo}", _typo(reports[0].display_name))
            .replace("{duplicate}", dup))


def run(cases, actors, dup, live):
    from apps.ai.agents import chat as chat_mod
    from apps.ai.providers import register_fake_output

    calls = []
    if not live:
        settings.LLM_PROVIDER = "apps.ai.providers.FakeLLMProvider"

        original = chat_mod._fake

        def counting(prompt, model):
            calls.append(prompt)
            return original(prompt, model)

        register_fake_output(chat_mod.AGENT_CODE, counting)

    results = []
    for case in cases:
        actor = actors[case["as"]]
        session = ChatSession.objects.create(tenant_id=actor.tenant_id, owner=actor)
        before = len(calls)
        question = fill(case["q"], actors, dup)
        out = _say(actor, session, question)
        for follow in case.get("then", []):
            out = _say(actor, session, fill(follow, actors, dup))
        answer = out.get("answer") or ""

        ok, why = judge(case, out, answer, actors, live)
        scope_ok, scope_why = check_scope(answer, actor, asked=question)
        if not scope_ok:
            ok, why = False, "SCOPE LEAK: " + scope_why
        if case.get("no_model_call") and not live and len(calls) > before:
            ok, why = False, "spent a model call it did not need"

        results.append({**case, "q_filled": question, "answer": answer,
                        "ok": ok, "why": why, "status": out.get("status")})
    return results


def _say(user, session, text):
    append_turn(session, ChatTurn.Role.USER, text)
    result = chat_answer(user, text, session=session)
    plan = result.get("plan")
    answer = result.get("answer") or (plan.summary if plan is not None else "")
    append_turn(session, ChatTurn.Role.ASSISTANT, answer,
                refs=result.pop("refs", None) or (refs_for_plan(plan) if plan else None),
                plan=plan)
    return {**result, "answer": answer}


def report(results, live) -> int:
    cats: dict = {}
    for r in results:
        cats.setdefault(r["cat"], []).append(r)

    width = max(len(c) for c in cats) + 2
    mode = "LIVE (spending)" if live else "no model calls"
    print(f"\nSELF-TEST — {len(results)} prompts, {mode}")
    print("=" * (width + 26))
    print(f"  {'category'.ljust(width)}{'pass':>7}{'total':>7}   result")
    print("  " + "-" * (width + 22))
    failed_cats = 0
    for cat in sorted(cats):
        rows = cats[cat]
        passed = sum(1 for r in rows if r["ok"])
        mark = "PASS" if passed == len(rows) else "FAIL"
        if passed != len(rows):
            failed_cats += 1
        print(f"  {cat.ljust(width)}{passed:>7}{len(rows):>7}   {mark}")
    print("  " + "-" * (width + 22))
    total = sum(1 for r in results if r["ok"])
    print(f"  {'TOTAL'.ljust(width)}{total:>7}{len(results):>7}")

    for r in results:
        if not r["ok"]:
            print(f"\n  [FAIL] {r['id']} ({r['cat']}) — {r['why']}")
            print(f"         q: {r['q_filled'][:100]}")
            print(f"         a: {r['answer'][:160]}")
    print()
    return 1 if failed_cats else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", default="acme",
                        help="Small tenant to run against (default acme).")
    parser.add_argument("--cat", default="", help="Only this category.")
    parser.add_argument("--live", action="store_true",
                        help="Use the configured provider. COSTS MONEY.")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    tenant = Tenant.objects.filter(slug=args.tenant).first()
    if tenant is None:
        print(f"No tenant {args.tenant!r}.")
        return 2

    cases = load(BANK, args.cat)
    if args.limit:
        cases = cases[:args.limit]
    if args.live:
        print(f"! LIVE mode: about to make roughly {len(cases)}-{len(cases) * 3} model "
              f"calls against {settings.LLM_PROVIDER.rsplit('.', 1)[-1]}.")

    with tenant_context(tenant.id):
        actors = pick_actors(tenant)
        dup = _duplicate_name(actors["_reports"][0].display_name)
        print(f"tenant {tenant.slug!r} · manager {actors['manager'].display_name!r} "
              f"({len(actors['_reports'])} reports) · employee "
              f"{actors['employee'].display_name!r} · out-of-scope "
              f"{getattr(actors['_stranger'], 'display_name', None)!r}")
        results = run(cases, actors, dup, args.live)
        return report(results, args.live)


if __name__ == "__main__":
    raise SystemExit(main())
