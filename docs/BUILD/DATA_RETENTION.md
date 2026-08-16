# Data retention

What this system stores, why it stores it, and how long it keeps it. Every model
in the product is listed — including the ones that hold nothing personal, because
"it is not on the list" and "it holds nothing" are different answers and only one
of them is reassuring.

Compiled from the model registry, not from memory.

---

## The short version

| | |
| --- | --- |
| Personal data with a **time limit** | Login events and device sessions: **90 days** |
| Personal data kept **for the life of the tenant** | Everything else about employment — reviews, goals, feedback, check-ins |
| **Never** deleted | The audit log |
| Removed on **request** | Anything about an individual, via erasure — see `DATA_RIGHTS_DESIGN.md` |
| Removed when the **tenant leaves** | Everything, by dropping the tenant's rows |

The honest summary: this product deletes almost nothing on a clock. A
performance management system is a record of an employment relationship, and the
retention period for that is set by the employer's own obligations — which vary
by country and by industry and are not ours to guess. So the default is to keep
it while the tenant exists and to give the tenant precise tools (export, erasure)
to act on their own policy.

The one category with an automatic clock is the one with no long-term purpose:
authentication telemetry.

---

## Automatic deletion

### `identity.LoginEvent` — 90 days

**Holds:** the email typed, the outcome (success, failure, lockout), the IP
address, the user agent, the timestamp.

**Why:** to answer "was this account reached by somebody else, and when". It also
backs the lockout counters.

**Why it expires:** across a tenant this is a movement log of the entire
workforce — where each person was, and on what device, every working day. Its
investigative value is measured in days and weeks. After three months there is no
question it can answer that anyone is still asking.

**How:** `apps.identity.tasks.purge_expired_auth_events_task`, daily on
celery-beat. Window: `AUTH_EVENT_RETENTION_DAYS` (default 90).

### `identity.DeviceSession` — 90 days

**Holds:** IP, user agent, last-seen timestamp, revocation timestamp. Referenced
by the `did` claim in access tokens, which is how a session is killed mid-life.

**Why it expires on age and not on revocation:** a session revoked yesterday is
evidence about a possible compromise today. Deleting it at revocation would
remove precisely the row an investigation wants. Past the window, the token that
referenced it is long expired and the row protects nothing.

**Set `AUTH_EVENT_RETENTION_DAYS=0`** to disable both purges — an explicit
opt-out for a deployment under a legal hold. It deletes nothing rather than
treating 0 as "everything is older than now".

---

## Kept for the life of the tenant

None of these expires on a clock. Each is a record of something that happened in
an employment relationship, and deleting it by default would destroy the history
the product exists to keep.

### People

| Model | Holds | Notes |
| --- | --- | --- |
| `identity.User` | email, display name, phone, title, department, employee id, timezone, language, avatar, preferences | Survives erasure as a tombstone — see below |
| `identity.Invitation` | invited email, role, inviter | Consumed or expires; the row remains as the record of who was invited |
| `identity.SamlIdpConfig` | the tenant's IdP metadata and signing certificate | Public metadata only; no secret |
| `org.Position` | job title, department, reporting line, who fills it | Org structure, not personal history |

### Performance content — the sensitive core

| Model | Holds |
| --- | --- |
| `reviews.Review` | the review body itself, draft and final, plus AI provenance and confidence |
| `reviews.ReviewAssessment` | what an assessor wrote about someone |
| `reviews.ReviewComment` | the comment thread on a review |
| `reviews.ReviewStateTransition` | who moved a review to which state, and when |
| `feedback.Feedback` | 360 and continuous feedback text, with the giver stored but never egressed |
| `feedback.FeedbackCycle`, `FeedbackRequest` | who was asked for feedback about whom |
| `feedback.FeedbackSummary` | the anonymised, HITL-gated summary |
| `feedback.OneOnOneNote` | private 1:1 notes between a manager and a report |
| `checkins.CheckIn`, `CheckInPriority`, `ManagerResponse` | weekly wins, blockers, mood, and the manager's reply |
| `goals.Goal`, `GoalUpdate` | objectives and the update thread on them |
| `goals.Kpi`, `KpiMeasurement`, `KpiTemplate` | targets and recorded values |
| `goals.CycleScore` | the computed score, z/t score, cohort size, risk status |
| `career.DevelopmentRoadmap`, `RoadmapProgress`, `TargetRoleSelection` | development plans and progress |
| `succession.NineBoxPlacement` | a performance/potential placement the employee is usually never shown |
| `succession.BenchCandidate`, `CriticalRole`, `SuccessionPlan` | who is being considered to replace whom, with notes |
| `recognition.Recognition`, `RecognitionReaction` | kudos and reactions |
| `cycles.PerformanceCycle` | the cycle definitions everything above hangs off |

**`succession` is the most sensitive category in the product** — a person is not
told they are on a bench list, or which box they were placed in. It is exported
under an access request and redacted under an erasure like everything else, and
its ordinary visibility is gated by RBAC scope.

### AI

| Model | Holds | Notes |
| --- | --- | --- |
| `ai.AIJob` | which agent ran, on what, the outcome — and `params`, the prompt payload | `params` can quote review text verbatim, so erasure empties it |
| `ai.ChatSession`, `ChatTurn`, `ChatPlan`, `ChatPlanStep` | the assistant conversation, including anything the user pasted into it | Deleted outright on erasure — the person's own conversations |
| `ai.TenantAIConfig` | the tenant's provider choice and its **encrypted** API key | Only the last 4 characters are ever readable back |
| `billing.TokenLedger`, `AgentBudget` | token spend per tenant | Cost control, no personal content |

### Commercial

`billing.Entitlement`, `Subscription`, `BillingProfile`, `Payment`,
`PaymentEvent`, `Invoice`, `administration.TenantConfig`,
`integrations.TenantIntegration`, `jd.*`, `approvals.*`, `tenancy.Tenant`.

These are about the tenant, not about a person, with two exceptions worth naming:
`approvals.ApprovalStepInstance.comment` is written by an approver about
something under review, and `jd.JDRequest.notes` is free text. Both are covered
by erasure as authored content — the text stays, the author becomes the
pseudonym.

Financial records typically carry a statutory retention period of their own
(commonly 6–7 years). They are kept for the life of the tenant, which is longer,
so no separate clock applies.

---

## Never deleted

### `audit.AuditLog`

Append-only, enforced at three layers including `BEFORE UPDATE` and
`BEFORE DELETE` triggers in MySQL that raise. Nothing in this product can update
or delete an audit row — not an admin, not an erasure, not a migration written by
somebody who forgot.

**Holds:** the action, the actor, the target, a justification string typed by a
human, and a metadata bag.

**The residual, stated plainly:** `justification` and `metadata` are free text
supplied at the time of an action and may name a person. Erasure leaves them
alone. An audit log that can be edited after the fact to remove a name is an
audit log that can be edited after the fact, and its entire value is that it
cannot be. What *does* change is the display: `actor` is a foreign key, so once
the user row is tombstoned every historical row renders `Former employee 4f2a`
without a single audit row being touched.

---

## Erasure

`POST /api/admin/users/<id>/erase` removes an individual on request, at any time,
regardless of the retention rules above. The semantics — what is redacted, what
is kept, and why the asymmetry exists — are in
[`DATA_RIGHTS_DESIGN.md`](DATA_RIGHTS_DESIGN.md).

In short: content **about** the person is redacted in place (rows kept, so
aggregates do not silently shift), content they **authored about others** keeps
its text with the author replaced by a stable pseudonym, and the user row itself
survives as that pseudonym.

## Tenant offboarding

There is no automated tenant-deletion flow, deliberately: an irreversible
"delete everything for this customer" button is a support incident waiting to
happen. When a tenant leaves, the sequence is:

1. export what they are owed (`/export` per employee, or a database extract);
2. suspend the tenant — `Tenant.status`, which now terminates live sessions;
3. delete their rows once the contractual window has passed. Every model is
   tenant-scoped, so this is a delete by `tenant_id`, and `audit_log` is the one
   table that requires an explicit decision because the triggers block deletion.

## Backups

The nightly dumps in `gs://axiom-backups` are kept **35 days** (lifecycle rule),
with superseded object versions kept 14 days. See
[`BACKUP_RESTORE.md`](BACKUP_RESTORE.md).

This is a real qualifier on everything above: **a backup holds the pre-erasure
and pre-purge rows until it ages out.** Nothing is fully gone until the last
backup containing it has expired, and a restore must be followed by re-running
any erasure performed since that backup was taken. That is written into the
restore runbook rather than left to somebody's memory.

## Logs and error reporting

- **Application logs** are JSON to stdout, retained by whatever collects them on
  the host. They carry a request id, tenant id and route — not request bodies.
- **Sentry** receives stack traces with the request body **dropped wholesale**,
  not key-redacted: in this product the sensitive fields (`draft_body`, `body`,
  `blockers`) would never make a denylist. Query strings are scrubbed too, since
  invitation and reset links carry a single-use token. Retention is Sentry's own,
  configured in that project.

## Where each number lives

| Setting | Default | What it controls |
| --- | --- | --- |
| `AUTH_EVENT_RETENTION_DAYS` | 90 | Login events and device sessions |
| `AUTH_EVENT_PURGE_INTERVAL_SECONDS` | 86400 | How often the sweep runs |
| `RETAIN_DAYS` (GCS lifecycle) | 35 | Backup archives |
| `RETAIN_NONCURRENT_DAYS` (GCS lifecycle) | 14 | Superseded backup versions |
