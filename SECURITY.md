# Security

This product holds performance reviews, 360-degree feedback and succession
assessments — some of the most sensitive writing an employer keeps about a
person. Please treat a finding here as higher-impact than the codebase size
suggests.

## Reporting a vulnerability

**Email security@talbotiq.com.** Do not open a GitHub issue, and do not include
the detail in a pull request title — both are visible to everyone with repository
access before anyone has had a chance to fix it.

Useful to include, in whatever detail you have:

- what an attacker can reach that they should not;
- the steps to reproduce it, or the request that demonstrates it;
- the tenant, role and account you were acting as, since almost everything here
  is scoped by those three.

You will get an acknowledgement within two working days and an assessment within
five. If a fix is going to take longer than that, we will say so and keep you
updated rather than going quiet.

Please give us a reasonable window to ship a fix before disclosing publicly. We
will credit you when the fix ships unless you would rather we did not.

## What is in scope

The application, its API, the deployment configuration in this repository, and
the container images built from it.

Out of scope: reports from automated scanners with no demonstrated impact, missing
headers on endpoints that serve no content, rate-limit findings on endpoints that
are deliberately unauthenticated (the login throttle is the one that matters —
see below), and anything requiring physical access to a customer's machine.

## The invariants worth attacking

If you are looking for where a real problem would live, these are the properties
the whole design rests on. Any way to break one of them is a serious finding,
even if it looks minor in isolation.

1. **Tenant isolation.** Every model is tenant-scoped and every query runs
   through a manager that filters by the bound tenant and **fails closed** with
   no tenant bound. Any path that returns another tenant's row — including a 403
   that reveals a row exists, where a 404 would not — is a break.
2. **RBAC is server-side.** Capabilities are checked on every endpoint, and data
   scope (own / team / tenant) is enforced in the queryset. The frontend hides
   things for tidiness, never for security.
3. **Human review of AI output.** Every AI-generated artefact is written
   `PENDING_HUMAN_REVIEW`. A path that publishes model output without a human
   approving it is a break, regardless of how good the output is.
4. **Audit-log immutability.** `audit_log` is append-only, enforced at three
   layers including `BEFORE UPDATE` and `BEFORE DELETE` triggers in MySQL. Any
   way to modify or remove a row — including via a migration or the erasure
   flow — is a break.
5. **Feedback anonymity.** The giver of 360 feedback is stored but never
   egressed, except to the giver themselves, and relationship groups below the
   minimum volume are withheld. Any surface that lets a recipient work out who
   said what is a break. This one is easy to reintroduce by accident whenever a
   new endpoint returns feedback.
6. **Login brute-force protection.** The per-IP throttle depends on
   `DJANGO_NUM_PROXIES` matching the real proxy depth. A way to get a fresh
   throttle bucket per request defeats it silently.

## Handling credentials

Secrets come from the environment only — never a committed file, a log line or a
docs example. Per-tenant provider API keys are encrypted at rest with Fernet and
only their last four characters are ever readable back.

If you believe a credential has been committed, report it as a vulnerability and
**do not** push a commit removing it: the value is still in the history, and the
correct response is rotation first.

## Supported versions

This product is deployed as a service from `main`. There are no supported older
releases — fixes ship to the running deployment.
