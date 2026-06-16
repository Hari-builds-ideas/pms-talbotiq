#!/usr/bin/env python3
"""
End-to-end SMOKE script for the Talbotiq PMS — exercises the core journeys of
every surface over real HTTP against the running stack, as each role, and prints
a PASS/FAIL table. QA (and Hari) can re-run it after a deploy to confirm the
product is genuinely wired end-to-end (no 500s, RBAC boundaries hold, AI alive).

Usage:
    docker compose up -d --build
    docker compose run --rm web python manage.py seed_demo
    python3 scripts/smoke.py                 # defaults to http://localhost:8080
    BASE=http://localhost:8080 python3 scripts/smoke.py

It is READ-MOSTLY (a couple of safe writes: a score recompute, a chat query) so
it can be run repeatedly without corrupting the demo data. Exit code is non-zero
if any check fails.
"""
import json
import os
import sys
import urllib.request as u

BASE = os.environ.get("BASE", "http://localhost:8080")
TENANT = os.environ.get("TENANT", "acme")
PASSWORD = os.environ.get("DEMO_PASSWORD", "Passw0rd!demo")

ACCOUNTS = {
    "ADMIN": "admin@acme.test",
    "HRBP": "priya@acme.test",
    "MANAGER": "ada@acme.test",
    "EMPLOYEE": "reza@acme.test",
}

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
results = []  # (ok, label, detail)


def call(method, path, token=None, body=None):
    req = u.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
    )
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        r = u.urlopen(req, timeout=60)
        return r.status, json.loads(r.read() or b"null")
    except u.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:120].decode(errors="replace")
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def login(email):
    st, d = call("POST", "/api/auth/login", body={"tenant_slug": TENANT, "email": email, "password": PASSWORD})
    if st == 200 and isinstance(d, dict) and d.get("access"):
        return d["access"]
    return None


def check(label, method, path, token, expect=(200,), body=None):
    st, d = call(method, path, token, body)
    ok = st in expect
    results.append((ok, label, f"{method} {path} → {st} (want {expect})"))
    return st, d


def section(title):
    print(f"\n{DIM}── {title} ──{RESET}")


def run():
    tokens = {role: login(email) for role, email in ACCOUNTS.items()}
    for role, tok in tokens.items():
        results.append((tok is not None, f"login {role}", ACCOUNTS[role]))
    admin, hrbp, mgr, emp = (tokens["ADMIN"], tokens["HRBP"], tokens["MANAGER"], tokens["EMPLOYEE"])

    section("Identity + entitlements")
    for role, tok in tokens.items():
        check(f"me ({role})", "GET", "/api/auth/me", tok)
    check("my-features (mgr)", "GET", "/api/billing/my-features", mgr)
    check("entitlement (admin)", "GET", "/api/billing/entitlement", admin)
    check("feature-flags (admin)", "GET", "/api/billing/feature-flags", admin)
    check("upgrade-prompt (admin)", "GET", "/api/billing/upgrade-prompt", admin)

    section("Admin + governance + RBAC boundaries")
    check("users (admin)", "GET", "/api/admin/users", admin)
    check("users DENIED (mgr→403)", "GET", "/api/admin/users", mgr, expect=(403,))
    check("tenant-config (admin)", "GET", "/api/admin/tenant-config", admin)
    check("audit logs (hrbp)", "GET", "/api/audit/logs", hrbp)
    check("audit DENIED (mgr→403)", "GET", "/api/audit/logs", mgr, expect=(403,))
    check("integrations (admin)", "GET", "/api/integrations/", admin)

    section("Goals & KPIs · cycles · reviews")
    st, cycles = check("cycles (hrbp)", "GET", "/api/cycles/", hrbp)
    cycle_id = (cycles[0]["id"] if isinstance(cycles, list) and cycles else None)
    check("goals (mgr)", "GET", "/api/goals/", mgr)
    check("goals (employee own)", "GET", "/api/goals/", emp)
    if cycle_id:
        check("cycle scores (hrbp)", "GET", f"/api/cycles/{cycle_id}/scores", hrbp)
        check("recompute (hrbp)", "POST", f"/api/cycles/{cycle_id}/recompute", hrbp, expect=(200, 202))
    check("reviews (mgr)", "GET", "/api/reviews/", mgr)
    check("reviews (employee own)", "GET", "/api/reviews/", emp)

    section("Approvals · JD · Org")
    check("approvals inbox (mgr)", "GET", "/api/approvals/inbox", mgr)
    check("approvals workflows (hrbp)", "GET", "/api/approvals/workflows", hrbp)
    check("jd library (mgr)", "GET", "/api/jd/", mgr)
    check("jd published (employee)", "GET", "/api/jd/?status=PUBLISHED", emp)
    check("org tree (mgr)", "GET", "/api/org/tree", mgr)
    check("org vacancies (hrbp)", "GET", "/api/org/vacancies", hrbp)
    check("org positions (hrbp)", "GET", "/api/org/positions", hrbp)

    section("Succession (management-only; invisible to employees)")
    check("succession dashboard (hrbp)", "GET", "/api/succession/dashboard", hrbp)
    check("nine-box (hrbp)", "GET", "/api/succession/nine-box", hrbp)
    check("critical-roles (hrbp)", "GET", "/api/succession/critical-roles", hrbp)
    check("succession HIDDEN (employee→404)", "GET", "/api/succession/dashboard", emp, expect=(403, 404))

    section("Analytics (+ min-cohort suppression boundary is a manual check)")
    check("individual (employee own)", "GET", "/api/analytics/individual", emp)
    check("dept analytics DENIED (employee→403)", "GET", "/api/analytics/department", emp, expect=(400, 403))
    if cycle_id:
        check("calibration (hrbp)", "GET", f"/api/analytics/calibration?cycle={cycle_id}", hrbp)

    section("360 Feedback · Career")
    check("my-cycles (employee)", "GET", "/api/feedback/my-cycles", emp)
    check("summaries review (hrbp)", "GET", "/api/feedback/summaries/review", hrbp)
    check("requests mine (employee)", "GET", "/api/feedback/requests/mine", emp)
    check("career roadmap (employee)", "GET", "/api/career/roadmap", emp)

    section("AI (alive on Groq, scope-bound, HITL)")
    check("nudges (mgr)", "GET", "/api/ai/nudges", mgr)
    check("nudges DENIED (employee→403)", "GET", "/api/ai/nudges", emp, expect=(403,))
    st, chat = check("chat read (mgr)", "POST", "/api/ai/chat", mgr,
                     expect=(200,), body={"query": "how are my reports doing?"})
    st, blocked = check("chat write-blocked (mgr)", "POST", "/api/ai/chat", mgr,
                        expect=(200,), body={"query": "approve all reviews"})
    if isinstance(blocked, dict) and blocked.get("status") not in (None, "blocked"):
        # chat answered but should classify a write as blocked
        results.append((blocked.get("intent") == "write" or blocked.get("status") == "blocked",
                        "chat classifies write→blocked", str(blocked.get("status"))))

    # Summary
    passed = sum(1 for ok, *_ in results if ok)
    failed = [r for r in results if not r[0]]
    print(f"\n{'='*60}")
    for ok, label, detail in results:
        mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  {mark}  {label:42s} {DIM}{detail}{RESET}")
    print(f"{'='*60}\n{GREEN if not failed else RED}{passed}/{len(results)} checks passed{RESET}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(run())
