# Data subject rights — design

Written before the code, because erasure is the one operation in this product
that cannot be undone by a later commit. Everything below is derived from the
actual model registry: 40 models carry a foreign key to `User`.

---

## The two requests

| | Export | Erasure |
| --- | --- | --- |
| Endpoint | `GET /api/admin/users/<id>/export` | `POST /api/admin/users/<id>/erase` |
| Who | Admin only (`MANAGE_TENANT`) | Admin only (`MANAGE_TENANT`) |
| Effect | none — reads | irreversible |
| Audited | yes, the export itself | yes, before it runs |

Both are Admin-only and tenant-scoped. An id from another tenant is a 404, not a
403 — the scoped manager never sees the row, so the endpoint cannot be used to
probe whether a person exists elsewhere.

---

## The rule that decides every field

The settled semantics (R10):

> Content **about** a person is anonymised. Content they **authored about others**
> is retained, with the author replaced by a stable pseudonymous id. The audit log
> is never deleted from.

The reason this asymmetry exists, and why it is not a compromise: a 360-degree
feedback system is a record of what *many* people said. Erasing everything a
departing employee ever wrote would silently rewrite other people's review
history — their manager's assessment of them would lose the peer input that
justified a rating, and a review that was fair when written becomes
unexplainable. So their voice stays and their identity goes.

Every user FK therefore falls into exactly one of three buckets, and the erasure
code is organised by that split rather than by app:

**SUBJECT** — the row is *about* them. Free text is redacted.
`reviews.Review.employee`, `feedback.Feedback.subject`,
`feedback.FeedbackCycle.subject`, `feedback.FeedbackSummary.subject`,
`feedback.OneOnOneNote.employee`, `checkins.CheckIn.author` (a check-in is a
person's own account of their week — about them, by them),
`career.DevelopmentRoadmap.employee`, `career.TargetRoleSelection.employee`,
`succession.BenchCandidate.candidate`, `succession.NineBoxPlacement.employee`,
`succession.CriticalRole.incumbent`, `goals.Goal.employee`,
`goals.CycleScore.employee`, `recognition.Recognition.recipient`,
`org.Position.filled_by`.

**AUTHOR** — they wrote it, about someone else. Text is kept; the FK is
repointed at the tombstone user, which *is* the stable pseudonymous id.
`reviews.ReviewAssessment.assessor`, `reviews.ReviewComment.author`,
`reviews.Review.reviewer` / `.human_reviewer`, `feedback.Feedback.giver`,
`feedback.OneOnOneNote.manager`, `checkins.ManagerResponse.responder`,
`goals.GoalUpdate.author`, `goals.KpiMeasurement.recorded_by`,
`recognition.Recognition.sender`, `approvals.*.approver` / `.decided_by`,
`jd.*.created_by` / `.requested_by`, `succession.*.assessed_by` / `.added_by` /
`.marked_by` / `.reviewed_by` / `.override_by`, `career.*.generated_by` /
`.selected_by`, `org.Position.created_by`, `ai.AIJob.requested_by`.

**MACHINERY** — operational rows, deleted outright. `identity.DeviceSession`,
`identity.LoginEvent`, `account.EmailAddress`, `ai.ChatSession` (and its turns
and plans, by cascade). These are the person's own session and chat records; no
one else's history depends on them, so anonymising rather than deleting would
keep IP addresses and user agents for no purpose.

### The pseudonymous id is the tombstoned user row itself

Not a separate `pseudonym` table, and not a nulled FK.

Nulling the author would be simpler and is wrong: `ReviewComment.author` is
`PROTECT`/non-null, and more importantly a thread of comments from
"—" and "—" is unreadable, while two comments from `Former employee 4f2a` are
still a conversation. Keeping one tombstone row per erased person gives
referential integrity for free, keeps every `select_related` in the codebase
working untouched, and makes the pseudonym stable by construction — the id never
changes because the row never moves.

The tombstone is the same row, mutated:

| Field | After erasure |
| --- | --- |
| `email` | `erased+<uuid4>@erased.invalid` — `.invalid` is reserved by RFC 2606 and can never route |
| `display_name` | `Former employee <first 4 of pk>` |
| `phone`, `title`, `department`, `employee_id` | `""` |
| `photo` | file deleted from storage, field cleared |
| `preferences` | `{}` |
| `password` | unusable (`set_unusable_password()`) |
| `is_active` | `False` |
| `manager` | `None` |
| `tenant`, `pk`, `role` | **unchanged** |

`tenant` stays because the row must remain inside tenant isolation — a tombstone
outside a tenant would be visible to every tenant through the unscoped manager.
`role` stays because a stripped role would silently re-grant nothing but would
break `select_related("author").role` reads in serializers.

The email tombstone is unique per erasure (`uuid4`), which matters: the
`(tenant, email)` unique constraint means a fixed sentinel would make the
*second* erasure in a tenant fail with an IntegrityError — after the first half
of the transaction had already run.

---

## Redaction, field by field

Redacting means replacing text with a marker, not emptying it. `""` is
indistinguishable from "nobody wrote anything", and a reviewer looking at a
blank assessment cannot tell whether the process failed or the content was
removed on request. The marker is `[redacted — erased at the subject's request]`.

| Model | Field(s) |
| --- | --- |
| `reviews.Review` | `draft_body`, `final_body`, `rejected_reason`, `citations` → `[]` |
| `reviews.ReviewAssessment` | `body` (where `review.employee` is the subject) |
| `reviews.ReviewComment` | `body` (same condition) |
| `reviews.ReviewStateTransition` | `note` |
| `feedback.Feedback` | `body`, `sentiment` |
| `feedback.FeedbackSummary` | `sections` → `{}`, `insufficient_groups` → `[]` |
| `feedback.OneOnOneNote` | `body` |
| `checkins.CheckIn` | `wins`, `blockers`, `learning` |
| `checkins.ManagerResponse` | `comment` (on their check-ins) |
| `goals.Goal` | `title`, `description`, `objective` |
| `goals.GoalUpdate` | `text` (on their goals) |
| `career.DevelopmentRoadmap` | `tiers` → `[]`, `skill_gap` → `{}` |
| `succession.BenchCandidate` | `notes` |
| `succession.NineBoxPlacement` | `override_rationale` |
| `succession.CriticalRole` | `risk_notes` (where they are incumbent) |
| `succession.SuccessionPlan` | entries naming them inside `ranked_bench`, `red_flags`, `action_items` |
| `recognition.Recognition` | `message`, `value` (received) |
| `ai.AIJob` | `params` → `{}` (the prompt payload can quote review text verbatim) |

Rows are **not deleted**. A missing `CycleScore` changes a tenant's aggregate
performance distribution and the analytics silently shift; a redacted one keeps
the shape of history honest. Numbers stay, words go.

### What is deliberately not redacted, and why

- **`goals.Goal` on a shared team goal.** Goals are per-employee here
  (`Goal.employee` is a single FK), so there is no shared row to damage. If team
  goals are ever added, this decision needs revisiting — noted in the code.
- **`AuditLog.justification`.** See below.
- **Numeric scores, ratings, nine-box coordinates, timestamps.** They are the
  record that a process happened. Removing them would not protect the person
  (their name is already gone) and would corrupt every aggregate.

---

## The audit log

Never deleted from, never updated — the table has `BEFORE UPDATE` and
`BEFORE DELETE` triggers at the MySQL level that raise, so an attempt would
fail loudly rather than partially succeeding. This is not something erasure gets
an exception from; it is the reason the audit log is trustworthy at all.

What actually happens: `AuditLog.actor` is a FK to `User`, so once the user row
is tombstoned every historical row automatically displays
`Former employee 4f2a` instead of a name. **No audit row is written, updated or
deleted to achieve this** — the display changes because the referenced row
changed. That is the whole mechanism, and it is why the pseudonym had to be the
user row.

`justification` and `metadata` are free text supplied by an admin at the time of
an action and may name the person. They are left alone. An audit record that can
be edited after the fact to remove a name is an audit record that can be edited
after the fact, and the value of the log is that it cannot. This is a deliberate,
documented residual — recorded here rather than discovered later.

The erasure itself is audited **before** it runs (via `audit_action`), so the
evidence of intent exists even if the operation then fails halfway.

---

## Idempotency

Erasing twice must be safe, because the second call is usually a retry after a
timeout, and the caller has no way to know whether the first one landed.

A `User.erased_at` timestamp records it. A second call returns `200` with
`{"already_erased": true, "erased_at": ...}` rather than `409`: the caller's
intent is satisfied, and a 409 invites them to "fix" it by trying something more
destructive. Redaction is written to be re-runnable regardless — replacing an
already-redacted marker with the same marker is a no-op.

## Atomicity

The whole erasure runs in one `transaction.atomic()` block. A half-erased user —
profile anonymised, review bodies still present — is worse than either outcome,
and it is the state that a timeout produces if this is not wrapped.

The photo file deletion is the one part that cannot be transactional (it is
object storage, not the database). It runs **last**, after the commit, via
`transaction.on_commit`, so a rolled-back erasure never deletes a file it should
have kept. The opposite failure — a committed erasure whose file delete fails —
leaves an orphaned avatar reachable only by an unguessable path with no user row
pointing at it, and is logged.

## Sessions

Every `DeviceSession` is revoked and the rows deleted. Access tokens carry a
device id checked against `is_session_revoked()` on each request, so a live
access token dies on its next call rather than at its natural expiry. Without
this, an erased user keeps a working session for up to the token lifetime — with
a tombstoned identity attached to it.

---

## Export

`GET /api/admin/users/<id>/export` returns one JSON document containing
everything held about the person, assembled from the SUBJECT list above plus
their authored content:

`profile`, `reporting_line`, `goals` (with `kpis` and `measurements`),
`cycle_scores`, `reviews` (with `assessments` and `comments`),
`feedback_received`, `feedback_given`, `one_on_one_notes`, `check_ins`,
`recognition_sent`, `recognition_received`, `career_roadmaps`,
`nine_box_placements`, `bench_candidacies`, `login_history`, `device_sessions`,
`ai_jobs`, `approvals_acted_on`.

Two decisions worth stating:

- **Feedback given is included, with the recipients' names.** It is the person's
  own writing, so it is theirs under any access-request framing — but it
  discloses who they reviewed. That is unavoidable in a 360 system and is why
  the endpoint is Admin-only rather than self-service.
- **Anonymous feedback stays anonymous in the export.** `Feedback` rows carry an
  anonymity flag; where set, the giver is reported as `anonymous`, in an export
  requested *about* the subject. Exposing it here would retroactively break the
  promise made to every person who gave feedback under it, and would do so
  through an endpoint nobody thinks of as a disclosure surface.

The export is audited with the subject's id — an admin reading an employee's
entire performance history is exactly the kind of legitimate-but-sensitive access
the audit console exists for.

Streaming/pagination is not used: one employee's full history is a few hundred
KB at most, and a partial export that looks complete is worse than a slow one.

---

## Retention (D3)

`AUTH_EVENT_RETENTION_DAYS` (default 90). A Celery beat task purges `LoginEvent`
and `DeviceSession` rows older than that.

90 days is chosen to be longer than any plausible incident-investigation window
and shorter than "forever". These rows hold IP addresses and user agents — a
movement log of every employee — and their only real use is answering "was this
account accessed by someone else, recently". After three months they are a
liability with no remaining purpose.

Revoked sessions are purged on the same clock rather than immediately: a session
revoked yesterday is evidence about a possible compromise today.

---

## What this design does not do

Stated so it is a decision rather than a gap:

- **No self-service portal.** Erasure and export are Admin actions. In an SME
  performance system the request arrives through HR, not through the app.
- **No cross-tenant erasure.** A person employed by two tenants using this
  product is two separate users with two separate histories, and erasing one
  must not touch the other. Tenant scoping gives this for free.
- **No backup rewriting.** The nightly dumps in `gs://axiom-backups` still
  contain the pre-erasure rows until they age out under the 35-day lifecycle
  rule (`docs/BUILD/BACKUP_RESTORE.md`). Restoring an old backup would restore
  erased data. This is the normal, accepted position — but it means a restore
  must be followed by re-running any erasure performed since that backup, and
  that is written into the restore runbook rather than left to memory.
