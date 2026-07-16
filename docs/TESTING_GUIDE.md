# TESTING_GUIDE — Axiom PMS (for the security/QA testing team)

Self-contained. How to get a demo environment, what's already covered, where to
focus exploratory + security testing, and how to file bugs.

## 1. The role / tenant model

- **Tenant** = the isolation boundary. Every row is tenant-scoped; a JWT carries
  `tenant_id` + `role`; a cross-tenant id returns **404** (never leaks). RBAC is
  enforced **server-side on every endpoint** — the SPA never gates.
- **Four roles**, increasing data scope: `EMPLOYEE` (own) < `MANAGER` (own + team)
  < `HRBP` (business-unit) < `ADMIN` (whole tenant).
- Every AI output is saved **PENDING_HUMAN_REVIEW** (HITL) and the audit log is
  **INSERT-only**.

## 2. Demo accounts

Tenant **`acme`**, password **`Passw0rd!demo`** for all:

| Login | Role |
|---|---|
| `admin@acme.test` | ADMIN |
| `priya@acme.test` | HRBP |
| `ada@acme.test` | MANAGER (has a team; MFA-capable) |
| `akhil@acme.test` | EMPLOYEE (showcase record) |

Cross-tenant fixture — tenant **`globex`** (`gadmin@ / gmgr@ / gemp@globex.test`,
same password) — use it to prove tenant isolation (globex must never see acme data
and vice-versa).

## 3. Get a demo environment

```bash
# Bring the stack up, then seed the rich ACME demo (~210 people, all modules):
docker compose up -d
docker compose exec web python manage.py seed_demo_rich          # idempotent; also purges QA junk
# Cross-tenant fixture:
docker compose exec -T web python manage.py shell < scripts/qa_seed_globex.py
# App: http://localhost:8090
```

The seed is **idempotent** and self-cleans test artifacts, so you can re-run it any
time to get a pristine, presentable demo (real varied goals/reviews/feedback/
recognition — no placeholder junk).

## 4. Run the automated suite first (extend, don't repeat)

```bash
./scripts/qa_handover.sh            # one command: reseed → globex fixture → 131 API checks → reseed
QA_SKIP_AI=1 ./scripts/qa_handover.sh   # skip live-Gemini checks (fast)
docker compose exec web pytest      # ~1500 backend unit/integration tests
```

`scripts/qa_verify.py` (131 checks) already covers, per module × 4 roles:
allowed-vs-denied (403/404), negative/edge cases (no 500s), **cross-tenant
isolation**, data validation/persistence, the fixed bug regressions, and data
hygiene. **Extend beyond these — don't repeat them.**

## 5. Where to focus manual / exploratory + security attention

- **Auth**: login, password reset (no account enumeration), **MFA** (TOTP,
  anti-replay), device sessions + lockout, **self-serve signup** (`/signup`, public,
  IP-throttled), **Sign-in-with-Google** (OIDC, no-JIT) — see STAGED.
- **RBAC boundaries + the role ceiling**: try every capability as each role; confirm
  an **HRBP cannot mint an ADMIN** via invite *or* CSV import (role ceiling).
- **Tenant isolation**: signup makes a fresh isolated tenant; **CSV import** must
  never link a manager across tenants; **payment webhooks** for tenant A must never
  touch tenant B.
- **Payment webhooks** (`POST /api/billing/webhooks/{stripe,razorpay}`): PUBLIC but
  **signature-verified** (HMAC). Try forged/missing signature (→401), replayed event
  (idempotent — one activation), unknown-tenant event (ignored), and a client trying
  to self-activate via `/api/billing/checkout` (must stay PENDING). TEST MODE only.
- **File upload**: profile photo (`PUT /api/auth/profile/photo`) — type/size limits,
  and the scope-checked serve endpoint (`/api/auth/users/<id>/photo`).
- **AI degrade-under-failure**: force provider errors/timeouts and confirm the job
  resolves to an honest FAILED/retry state — never an infinite spinner, never
  fabricated content. It runs off the request thread (can't block the web tier).
- **Text / UX overflow**: long / no-space content (recognition, comments, review &
  goal text, feedback, chat) must wrap inside its card, never overflow horizontally.

## 6. Already covered (baseline — extend these)

Injection matrix, cross-tenant isolation harness, RBAC-per-role matrix, auth edges,
the 5 QA-NIGHT bug regressions, the payment trust-boundary (9 tests), AI
retry/degrade (6 tests). See `BUGS_FOUND.md`, `docs/QA_NIGHT/*`,
`docs/FUNCTIONAL_TEST_MATRIX.md`, `docs/SECURITY_TESTING_HANDOVER.md`.

## 7. Honest STAGED list (known, not bugs)

- **Payments are TEST-MODE.** Live keys pending; `create_checkout` returns a test
  descriptor until the provider SDK call is wired at go-live
  (`docs/PHASE2/PAYMENTS_VERIFIED.md`). The signed-webhook trust boundary IS built.
- **Google / SSO** need the human's real OAuth creds / a real IdP to exercise the
  full round-trip (the no-JIT tenant binding + JWT issuance are tested vs a mock IdP).
  The login button is hidden until `VITE_GOOGLE_SSO_ENABLED=true`.
- **Mobile app** deferred to v2 — test the responsive web only.
- **Email** uses the console backend in dev (mail prints to `docker compose logs web`);
  a real SMTP provider is a deploy step.

## 8. Bug-reporting format

Please file each bug as:

```
Title:        <concise symptom>
Severity:     Critical / High / Medium / Low
Environment:  commit <git sha>, tenant <acme/globex>, role <EMPLOYEE/MANAGER/HRBP/ADMIN>
Steps:        1. … 2. … 3. …
Expected:     <what should happen>
Actual:       <what happened>  (attach screenshot / response body / status code)
Evidence:     request (method + path + payload), response status + body,
              browser console errors, and `docker compose logs web` around the time
Isolation?:   does it cross tenants or roles? (flag security impact explicitly)
Reproducible: always / intermittent (X of Y)
```

Security-impacting findings (auth bypass, cross-tenant leak, RBAC escalation,
webhook signature bypass, injection) → mark **Critical/High** and include the exact
request + token/role used.
