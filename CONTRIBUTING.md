# Contributing

A short guide to how this codebase expects to be worked on. Most of it is
conventions you would infer from reading around; the parts you would not infer
are marked.

## Getting a stack up

```bash
docker compose up -d          # web, worker, beat, MySQL, Redis, frontend
docker compose logs -f web    # migrations run automatically in dev
docker compose exec web python manage.py seed_demo_rich   # ~210 people, idempotent
```

The app is on http://localhost:8080. `docs/RUNBOOK.md` has the operational
detail.

## Running the tests

```bash
docker compose exec web pytest apps/<app>      # one app, the usual loop
docker compose exec web pytest                 # everything (slow)
npm --prefix frontend test
```

**The Python suite needs a real MySQL and a real Redis.** It is not mocked, on
purpose: tenant isolation is enforced partly by database constraints and audit
immutability entirely by MySQL triggers, and neither can be tested against
SQLite. If a test passes without a database, it is probably not testing what you
think.

Two markers are excluded by default and should stay that way locally:
`live_ai` (makes real model calls, costs money) and `large_tenant` (slow).

## Commits

Conventional commits, enforced by a hook:

```
<type>(<scope>): <summary>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `ci`, `style`,
`build`, `revert`.

**Write the body for the person who finds this commit while debugging at 2am.**
Not what changed — the diff says that — but why the obvious approach was wrong.
The commits worth imitating are the ones that name the failure mode: "deleting
the sessions here would hand the erased account a working access token, because
`session_is_revoked` reads a missing row as not-revoked."

One commit per logical change. Never commit a broken test.

## The rules that are not style preferences

These are load-bearing. Breaking one is a bug even when everything passes.

1. **Every model inherits `TenantScopedModel`** and is queried through
   `Model.objects`, which filters by the bound tenant and fails closed. The
   `all_tenants()` escape hatch raises on any request path — it is for
   system/migration code only, and if you need it in a view, the design is wrong.
2. **`.delete()` on a tenant-scoped queryset is a SOFT delete.** It stamps
   `deleted_at` and leaves the row. Use `hard_delete()` when you mean it, and be
   sure you mean it. This has caused real bugs: a purge that reports a healthy
   count and removes nothing.
3. **RBAC is checked server-side, on every endpoint.** Declare
   `required_capability` (or a `_caps` map with `get_permissions`) on the view,
   even when the queryset already scopes the rows. There is a test that walks the
   whole URLconf and fails if a view gates nothing — including one you write next
   month.
4. **Every AI output is written `PENDING_HUMAN_REVIEW`.** No exceptions, however
   confident the model was.
5. **All LLM calls go through `LLMGateway`.** Never a provider SDK directly.
6. **Never write to `audit_log` except through `apps.audit.services.record`**,
   and never update or delete a row. The database will refuse you anyway.
7. **Secrets come from the environment.** Not a committed file, not a docs
   example, not a log line, not a test fixture that looks real.

## Code style

Match the file you are editing. Beyond that:

- **Comments explain why, not what.** A comment restating the code is noise; a
  comment naming the failure the code prevents is the reason the next person does
  not undo it.
- **Docstrings carry the decision.** Several modules here open with the argument
  for their own design. That is intentional — it is where a reviewer looks first.
- Views stay thin: gate the capability, validate the body, call the service.
  Services are the only mutators and the only audit writers.
- No speculative abstraction. One caller means one function.

## Tests

- Test the property, not the implementation. "A wrong confirmation erases
  nothing" survives a refactor; "`_tombstone` is called once" does not.
- **Test the failure that looks like success.** Most of the real bugs in this
  codebase have been silent: a soft delete reported as a purge, a link that sends
  fine and arrives dead, a trigger that fails to restore. When a mechanism can
  fail quietly, write the test that would catch it quietly failing — and assert
  through the manager that can actually see the difference (`all_objects`, not
  `objects`).
- Name the test after the claim: `test_login_history_is_really_deleted_not_soft_deleted`.

## Before opening a PR

```bash
docker compose exec web pytest apps/<the apps you touched>
docker compose exec web python manage.py check --deploy
npm --prefix frontend run build
```

CI runs the full suite on every push. In the PR description, record what was
built, what tests were written, known risks, and what the next piece of work
needs from this one.

## Where things are

| Path | What |
| --- | --- |
| `apps/` | Django apps, one per module |
| `config/settings/` | `base` / `dev` / `prod` / `test` |
| `frontend/` | React + TypeScript SPA |
| `shared/` | Types shared between the API and the SPA |
| `docs/BUILD/` | Deployment, backups, TLS, email, data rights |
| `docs/RUNBOOK.md` | Operating the stack |
| `docs/archive/` | Superseded planning documents — history, not instructions |

Security issues do not go in a PR or an issue. See [SECURITY.md](SECURITY.md).
