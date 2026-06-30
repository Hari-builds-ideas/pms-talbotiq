"""
seed_demo_rich — a PLENTIFUL, realistic demo for tenant ACME (FULL_AI).

Builds on top of the base ``seed_demo`` (and is safe to run after it): keeps the
named demo accounts (admin@acme.test, priya@, ada@, …) working exactly as before,
then scales ACME up to ~200 employees across a realistic multi-level org and
populates every screen that has a REAL data source — goals/KPIs/actuals (with
weights that correctly sum to 100), cycle scores spread across the risk bands,
reviews in several states, 360 cycles, weekly check-ins, a recognition feed,
succession + JD library, and pending work for the demo manager (Ada).

It does NOT fabricate data for features with no backing source (engagement,
competency radar, announcements) — those keep their honest empty states.

ACME-only. Idempotent + deterministic (no randomness; stable emails/keys), so a
re-run adds nothing and never duplicates. No live AI (scores are the deterministic
engine; feedback summaries use FakeLLMProvider / direct text).

    docker compose run --rm web python manage.py seed_demo_rich
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

DEMO_PASSWORD = "Passw0rd!demo"

# Deterministic, varied name pools (NOT "Test User"). 40 × 40 → plenty of unique
# combinations; we walk them deterministically by index so re-runs are stable.
FIRST_NAMES = [
    "Aarav", "Mei", "Liam", "Sofia", "Noah", "Aisha", "Ethan", "Priya", "Lucas", "Hana",
    "Mateo", "Yuki", "Omar", "Elena", "Kai", "Zara", "Diego", "Anya", "Ravi", "Clara",
    "Ibrahim", "Nadia", "Leon", "Ingrid", "Tariq", "Lena", "Hugo", "Amara", "Felix", "Rina",
    "Dmitri", "Maya", "Carlos", "Freya", "Jamal", "Saanvi", "Theo", "Lucia", "Arjun", "Nora",
]
LAST_NAMES = [
    "Sharma", "Chen", "Okafor", "Rossi", "Haddad", "Nguyen", "Andersen", "Garcia", "Kim", "Müller",
    "Patel", "Tanaka", "Silva", "Novak", "Khan", "Lindqvist", "Mbeki", "Costa", "Dubois", "Reyes",
    "Bergstrom", "Aziz", "Schmidt", "Fontaine", "Menon", "Vidal", "O'Brien", "Rao", "Carter", "Yamamoto",
    "Ferrari", "Cohen", "Ivanov", "Santos", "Larsen", "Bauer", "Travers", "Nair", "Walsh", "Petrova",
]

DEPARTMENTS = ["Engineering", "Product", "Data", "Design", "Sales", "Customer Success"]

# Deterministic attainment spread (0..1) so cohort-relative T-scores + risk bands
# vary believably. Walked by index, repeating across the population.
ATTAINMENT = [
    0.97, 0.61, 0.34, 0.85, 0.48, 0.30, 1.00, 0.74, 0.41, 0.55,
    0.92, 0.36, 0.68, 0.32, 0.88, 0.58, 0.45, 0.78, 0.39, 0.95,
    0.70, 0.50, 0.82, 0.43, 0.66, 0.28, 0.90, 0.52, 0.47, 0.80,
    0.38, 0.72, 0.33, 0.86, 0.56, 0.49, 0.76, 0.40, 0.93, 0.63,
]


class Command(BaseCommand):
    help = "Populate tenant ACME with plentiful, realistic demo data (idempotent)."

    @staticmethod
    def _ensure(model, *, defaults=None, **lookup):
        obj = model.objects.filter(**lookup).first()
        if obj is not None:
            return obj, False
        return model.objects.create(**lookup, **(defaults or {})), True

    def handle(self, *args, **options):
        tenant, _ = Tenant.objects.get_or_create(
            slug="acme", defaults={"name": "Acme Corporation", "status": "ACTIVE"}
        )
        with tenant_context(tenant.id):
            with transaction.atomic():
                self._entitlement(tenant)
                people = self._people(tenant)
                cycle = self._cycle(tenant)
                self._goals_and_scores(tenant, cycle, people)
                self._make_some_stale(tenant, cycle, people)
                self._reviews(tenant, cycle, people)
                self._recognitions(tenant, people)
                self._checkins(tenant, people)
                self._feedback(tenant, people)
                self._approvals_for_ada(tenant, cycle, people)
                self._jds(tenant, people)
                self._succession(tenant, cycle, people)
        n = len(people["all"])
        self.stdout.write(self.style.SUCCESS(
            f"seed_demo_rich complete: ACME populated with {n} people. "
            f"Login with any seeded email + password '{DEMO_PASSWORD}'. Demo manager: ada@acme.test"
        ))

    # ── entitlement (FULL_AI) ───────────────────────────────────────────────────
    def _entitlement(self, tenant):
        from apps.billing.models import Entitlement

        ent = Entitlement.objects.filter(tenant_id=tenant.id).first()
        if ent is None:
            Entitlement.objects.create(tenant_id=tenant.id, seat_count=250, feature_packs=["STARTER", "FULL_AI"])
        else:
            changed = False
            if "FULL_AI" not in (ent.feature_packs or []):
                ent.feature_packs = ["STARTER", "FULL_AI"]
                changed = True
            if ent.seat_count < 250:
                ent.seat_count = 250
                changed = True
            if changed:
                ent.save(update_fields=["feature_packs", "seat_count"])

    # ── user helper (reuse-by-email; keeps named accounts stable) ───────────────
    def _user(self, tenant, local, display_name, role, manager, *, department=None, hire_offset_days=0):
        from apps.identity.models import User

        email = f"{local}@{tenant.slug}.test"
        existing = User.objects.filter(email=email).first()
        if existing:
            fields = []
            if existing.manager_id != (manager.id if manager else None):
                existing.manager = manager
                fields.append("manager")
            if existing.display_name != display_name:
                existing.display_name = display_name
                fields.append("display_name")
            if fields:
                existing.save(update_fields=fields)
            return existing
        return User.objects.create_user(
            email=email, password=DEMO_PASSWORD, tenant=tenant, role=role,
            display_name=display_name, manager=manager,
        )

    def _gen_name(self, i: int) -> str:
        # Deterministic spread across the pools; the offset on the last name keeps
        # adjacent indices from sharing a surname.
        return f"{FIRST_NAMES[i % len(FIRST_NAMES)]} {LAST_NAMES[(i * 7 + 3) % len(LAST_NAMES)]}"

    # ── people: admin → HRBP → director(MANAGER) → lead(MANAGER) → employee ─────
    def _people(self, tenant):
        admin = self._user(tenant, "admin", "Avery Stone", "ADMIN", manager=None)
        priya = self._user(tenant, "priya", "Priya Nair", "HRBP", manager=admin)
        dan = self._user(tenant, "dan", "Daniel Cohen", "HRBP", manager=admin)
        hrbps = [priya, dan]

        # One director per department (MANAGER role), alternating HRBP parent.
        directors = []
        for d, dept in enumerate(DEPARTMENTS):
            local = f"dir.{dept.split()[0].lower()}"
            director = self._user(tenant, local, self._gen_name(100 + d), "MANAGER", manager=hrbps[d % 2], department=dept)
            directors.append((director, dept))

        # Leads (MANAGER) under each director — 3 per director. Ada is the FIRST
        # Engineering lead so the demo manager (ada@acme.test) has a real team.
        leads = []  # list of (lead_user, dept)
        lead_idx = 0
        for d, (director, dept) in enumerate(directors):
            for k in range(3):
                if d == 0 and k == 0:
                    lead = self._user(tenant, "ada", "Ada Lovelace", "MANAGER", manager=director, department=dept)
                else:
                    lead = self._user(tenant, f"lead{lead_idx:02d}", self._gen_name(200 + lead_idx), "MANAGER", manager=director, department=dept)
                leads.append((lead, dept))
                lead_idx += 1

        # ~180 employees spread across leads (~10 each); Ada (leads[0]) gets 12.
        employees = []
        ei = 0
        for li, (lead, dept) in enumerate(leads):
            count = 12 if li == 0 else 10
            for _ in range(count):
                emp = self._user(tenant, f"emp{ei:03d}", self._gen_name(ei), "EMPLOYEE", manager=lead, department=dept)
                employees.append(emp)
                ei += 1

        ada = leads[0][0]
        # A clean, showcase employee reporting to Ada — a good-looking record to open
        # in the demo (forced high attainment → On Track; check-ins + recognition below).
        akhil = self._user(tenant, "akhil", "Akhil Menon", "EMPLOYEE", manager=ada, department=leads[0][1])
        employees.append(akhil)
        managers = [d for d, _ in directors] + [l for l, _ in leads]
        ada_reports = [e for e in employees if e.manager_id == ada.id]
        return {
            "admin": admin, "hrbps": hrbps, "directors": [d for d, _ in directors],
            "managers": managers, "leads": [l for l, _ in leads], "employees": employees,
            "ada": ada, "ada_reports": ada_reports, "akhil": akhil,
            "all": [admin, *hrbps, *managers, *employees],
        }

    # ── cycle ───────────────────────────────────────────────────────────────────
    def _cycle(self, tenant):
        from apps.cycles.models import PerformanceCycle

        cycle, _ = self._ensure(
            PerformanceCycle, tenant_id=tenant.id, name="H1 2026",
            defaults={"start_date": datetime.date(2026, 1, 1),
                      "end_date": datetime.date(2026, 6, 30), "status": "ACTIVE"},
        )
        return cycle

    # ── goals + KPIs + actuals + scores (weights sum to 100) ────────────────────
    def _goals_and_scores(self, tenant, cycle, people):
        from apps.goals.models import Goal, Kpi, KpiMeasurement
        from apps.goals.scoring.engine import compute_cycle_scores

        # Score everyone except the admin (managers + employees are the cohort).
        from apps.identity.models import User

        # Two goals per person, weights 60 + 40 = 100 (so a person never shows
        # 200/100); each goal's KPIs also sum to 100.
        goal_specs = [
            ("Deliver cycle objectives", Decimal("60.00"),
             [("Throughput", Decimal("60.00")), ("Quality", Decimal("40.00"))]),
            ("Grow craft & collaboration", Decimal("40.00"),
             [("Impact", Decimal("50.00")), ("Collaboration", Decimal("50.00"))]),
        ]
        spec_titles = [s[0] for s in goal_specs]
        # EVERY non-admin in ACME (including accounts seeded by earlier commands /
        # sessions) gets this clean setup; deterministic order keeps scores stable.
        subjects = list(User.objects.filter(tenant_id=tenant.id).exclude(role="ADMIN").order_by("email"))
        for i, emp in enumerate(subjects):
            # Akhil is the showcase record → force strong (On Track) attainment.
            attain = 0.96 if emp.email == "akhil@acme.test" else ATTAINMENT[i % len(ATTAINMENT)]
            for gi, (title, gweight, kpis) in enumerate(goal_specs):
                goal, _ = self._ensure(
                    Goal, tenant_id=tenant.id, employee=emp, cycle=cycle, title=title,
                    defaults={"weight": gweight, "status": "ACTIVE", "created_by": emp.manager or emp,
                              "description": "Primary objective for the performance cycle." if gi == 0 else "Growth objective.",
                              "objective": "Hit committed KPIs for H1 2026."},
                )
                # Keep the weight correct on re-run (in case an older row drifted).
                if goal.weight != gweight or goal.status != "ACTIVE":
                    goal.weight = gweight
                    goal.status = "ACTIVE"
                    goal.save(update_fields=["weight", "status"])
                for ki, (name, kweight) in enumerate(kpis):
                    kpi, _ = self._ensure(
                        Kpi, tenant_id=tenant.id, goal=goal, name=name,
                        defaults={"weight": kweight, "target_value": Decimal("100.0000"),
                                  "direction": "INCREASING", "unit": "%", "source": "MANUAL"},
                    )
                    # Vary actual a little per KPI so it isn't uniform, clamped 0..100.
                    bump = Decimal(str((gi * 7 + ki * 3) - 6))
                    val = max(Decimal("0"), min(Decimal("100"), Decimal(str(round(attain * 100, 2))) + bump))
                    KpiMeasurement.objects.filter(kpi=kpi).delete()
                    KpiMeasurement.objects.create(
                        tenant_id=tenant.id, kpi=kpi, value=val, recorded_at=timezone.now(), source="MANUAL",
                    )
            # Archive any OTHER active goal (e.g. a stray "RW4 live-verify goal")
            # so this person's active goal weight is EXACTLY 100 — never 200/100.
            Goal.objects.filter(
                tenant_id=tenant.id, employee=emp, cycle=cycle, status="ACTIVE",
            ).exclude(title__in=spec_titles).update(status="ARCHIVED")
        compute_cycle_scores(tenant.id, cycle.id)

    # ── make a few of Ada's reports "stale" (no recent KPI measurement) so the
    #    stale-goal nudge + Ada's "My Tasks" populate. Backdates measurement dates
    #    only — the already-computed scores are unaffected. ──────────────────────
    def _make_some_stale(self, tenant, cycle, people):
        from apps.goals.models import KpiMeasurement

        old = timezone.now() - datetime.timedelta(days=45)
        reports = [r for r in people["ada_reports"] if r.email != "akhil@acme.test"]
        for emp in reports[6:9]:
            KpiMeasurement.objects.filter(
                tenant_id=tenant.id, kpi__goal__employee=emp, kpi__goal__cycle=cycle,
            ).update(recorded_at=old)

    # ── reviews (varied states across many employees) ──────────────────────────
    def _reviews(self, tenant, cycle, people):
        from apps.reviews.models import Review, ReviewAssessment

        emps = people["employees"]
        states = ["FINALIZED", "APPROVED", "PENDING_HUMAN_REVIEW", "DRAFT", "REJECTED"]
        # Give a healthy fraction of employees a review, cycling through states so
        # the Reviews list is full and varied. Every 3rd employee gets one.
        for i, emp in enumerate(emps):
            if i % 3 != 0:
                continue
            state = states[(i // 3) % len(states)]
            reviewer = emp.manager
            defaults = {"reviewer": reviewer, "state": state, "source": "MANUAL",
                        "draft_body": "Strong, consistent delivery this cycle with clear growth areas."}
            if state in ("APPROVED", "FINALIZED"):
                defaults.update(human_reviewer=reviewer, approved_at=timezone.now(),
                                final_body="## Summary\nEndorsed: a solid half with room to stretch next cycle.\n\n## Strengths\n- Reliable delivery\n- Strong collaboration\n\n## Growth\n- Take on broader scope")
            if state == "REJECTED":
                defaults.update(rejected_reason="Needs concrete KPI evidence before approval.")
            review, _ = self._ensure(Review, tenant_id=tenant.id, employee=emp, cycle=cycle, defaults=defaults)
            self._ensure(
                ReviewAssessment, tenant_id=tenant.id, review=review, assessment_type="SELF",
                defaults={"assessor": emp, "body": "Proud of my delivery; want to grow in communication.",
                          "submitted_at": timezone.now()},
            )
            if reviewer:
                self._ensure(
                    ReviewAssessment, tenant_id=tenant.id, review=review, assessment_type="MANAGER",
                    defaults={"assessor": reviewer, "body": "Reliable and technically strong.",
                              "submitted_at": timezone.now()},
                )

        # Guarantee a reachable DRAFT review for a FIXED Ada report (emp009) with a
        # SELF assessment, RESET to DRAFT on every run — so the "Request AI draft"
        # demo step is reliably available even after a prior rehearsal advanced it.
        from apps.identity.models import User as _User

        ada = people["ada"]
        target = _User.objects.filter(tenant_id=tenant.id, email="emp009@acme.test").first()
        if target is not None and target.manager_id == ada.id:
            review, _ = self._ensure(
                Review, tenant_id=tenant.id, employee=target, cycle=cycle,
                defaults={"reviewer": ada, "state": "DRAFT", "source": "MANUAL",
                          "draft_body": "Strong, consistent delivery this cycle with clear growth areas."},
            )
            if review.state != "DRAFT":
                review.state = "DRAFT"
                review.human_reviewer = None
                review.approved_at = None
                review.approval_route = None
                review.final_body = ""
                review.save(update_fields=["state", "human_reviewer", "approved_at",
                                           "approval_route", "final_body", "updated_at"])
            self._ensure(
                ReviewAssessment, tenant_id=tenant.id, review=review, assessment_type="SELF",
                defaults={"assessor": target, "body": "Proud of my delivery; want to grow in communication.",
                          "submitted_at": timezone.now()},
            )

    # ── recognition feed (varied, plentiful) ────────────────────────────────────
    def _recognitions(self, tenant, people):
        from apps.recognition.models import Recognition

        emps = people["employees"]
        ada = people["ada"]
        if len(emps) < 6:
            return
        V = Recognition.Visibility
        values = ["Teamwork", "Leadership", "Helping Others", "Innovation", "Ownership", "Customer Focus"]
        vis = [V.COMPANY, V.TEAM, V.TEAM, V.MANAGER_ONLY, V.COMPANY, V.TEAM]
        msgs = [
            "Carried the launch under real pressure — outstanding.",
            "Always the first to unblock a teammate.",
            "Turned a vague ask into a crisp plan the whole team could run with.",
            "Quietly mentored two new joiners this cycle.",
            "Shipped the migration with zero downtime.",
            "Went above and beyond for a frustrated customer.",
        ]
        # ~24 kudos across varied senders/recipients (deterministic pairing).
        for k in range(24):
            sender = ada if k % 4 == 0 else emps[(k * 3) % len(emps)]
            recipient = emps[(k * 5 + 1) % len(emps)]
            if recipient.id == sender.id:
                recipient = emps[(k * 5 + 2) % len(emps)]
            self._ensure(
                Recognition, sender=sender, recipient=recipient, message=msgs[k % len(msgs)],
                defaults={"value": values[k % len(values)], "visibility": vis[k % len(vis)]},
            )
        # A couple of kudos featuring Akhil (showcase) so his profile + the feed shine.
        akhil = people.get("akhil")
        if akhil is not None:
            self._ensure(Recognition, sender=ada, recipient=akhil,
                         message="Owned the API migration end to end — exactly the leadership we want to see.",
                         defaults={"value": "Leadership", "visibility": V.COMPANY})
            other = emps[1] if len(emps) > 1 else ada
            self._ensure(Recognition, sender=akhil, recipient=other,
                         message="Thanks for the thorough review — caught two issues before release.",
                         defaults={"value": "Helping Others", "visibility": V.TEAM})

    # ── weekly check-ins across recent weeks (many employees) ───────────────────
    def _checkins(self, tenant, people):
        from apps.checkins.models import CheckIn, CheckInPriority, ManagerResponse

        emps = people["employees"]
        ada = people["ada"]
        # Last 4 Mondays ending around the cycle's recent window.
        weeks = [datetime.date(2026, 6, 1), datetime.date(2026, 6, 8),
                 datetime.date(2026, 6, 15), datetime.date(2026, 6, 22)]
        moods = [4, 3, 5, 4, 2, 3, 5, 4, 3, 4]
        # Every other employee checks in for each recent week → the screens are full.
        for ei, emp in enumerate(emps):
            if ei % 2 != 0:
                continue
            for wi, week in enumerate(weeks):
                ci, _ = self._ensure(
                    CheckIn, author=emp, week_of=week,
                    defaults={"mood": moods[(ei + wi) % len(moods)],
                              "wins": "Made steady progress on my goals this week.",
                              "blockers": "Waiting on a review from another team." if wi % 2 else "",
                              "learning": "Picked up a new pattern that sped things up."},
                )
                self._ensure(CheckInPriority, check_in=ci, text="Advance my top KPI",
                             defaults={"status": "ACTIVE", "order": 0})
        # Akhil (showcase) checks in every recent week with an upbeat, specific log.
        akhil = people.get("akhil")
        if akhil is not None:
            akhil_logs = [
                ("Drove the API ownership work forward; shipped the v2 endpoints.", 5),
                ("Paired with two teammates on the migration — unblocked both.", 4),
                ("Closed the last reliability gap; the dashboards are green.", 5),
                ("Wrote the platform runbook the team had been missing.", 4),
            ]
            for wi, week in enumerate(weeks):
                win, mood = akhil_logs[wi % len(akhil_logs)]
                self._ensure(CheckIn, author=akhil, week_of=week,
                             defaults={"mood": mood, "wins": win, "blockers": "",
                                       "learning": "Levelled up on the platform internals."})
        # A manager response on a recent Ada-report check-in so the team view + the
        # responded-state are demoable.
        ada_report = people["ada_reports"][0] if people["ada_reports"] else None
        if ada_report is not None:
            ci = CheckIn.objects.filter(author=ada_report, week_of=weeks[-1]).first()
            if ci is None:
                ci, _ = self._ensure(CheckIn, author=ada_report, week_of=weeks[-1],
                                     defaults={"mood": 4, "wins": "Shipped my slice of the feature.",
                                               "blockers": "", "learning": "Faster with the test harness."})
            self._ensure(
                ManagerResponse, check_in=ci,
                defaults={"responder": ada, "comment": "Great week — let's talk scope in our 1-on-1.",
                          "add_to_one_on_one": True},
            )

    # ── 360 feedback: closed-summarizable + in-progress (+ a pending ask for Ada) ─
    def _feedback(self, tenant, people):
        from apps.feedback.models import Feedback, FeedbackCycle, FeedbackRequest, FeedbackSummary

        emps = people["employees"]
        ada = people["ada"]
        if len(emps) < 8:
            return
        # Closed, summarizable cycles: ≥3 PEER + 1 MANAGER (meets min_volume=3 so
        # they're ready for the HRBP to summarize/release). A pending summary
        # artifact is created with sections=None — AI theme text is NEVER fabricated.
        for si, subject in enumerate(emps[:3]):
            peers = [e for e in emps if e.id != subject.id][si * 3 : si * 3 + 3]
            fc, _ = self._ensure(
                FeedbackCycle, tenant_id=tenant.id, subject=subject,
                defaults={"opened_by": subject.manager, "status": "CLOSED", "min_volume": 3},
            )
            entries = [(p, "PEER", "Dependable teammate who unblocks others quickly.") for p in peers]
            if subject.manager:
                entries.append((subject.manager, "MANAGER", "Consistently meets commitments; ready for more scope."))
            for giver, rel, body in entries:
                if giver is None:
                    continue
                self._ensure(FeedbackRequest, tenant_id=tenant.id, cycle=fc, giver=giver,
                             defaults={"relationship": rel, "status": "SUBMITTED"})
                self._ensure(Feedback, tenant_id=tenant.id, cycle=fc, giver=giver, kind="THREE_SIXTY",
                             defaults={"subject": subject, "relationship": rel, "body": body,
                                       "giver_marked_sensitive": False})
            FeedbackSummary.objects.update_or_create(
                cycle=fc,
                defaults={"tenant_id": tenant.id, "subject": subject, "sections": None,
                          "status": "PENDING_HUMAN_REVIEW", "volume_total": len(entries),
                          "insufficient_groups": [], "insufficient_volume": False,
                          "anonymity_passed": True, "sensitive": False, "generated_at": timezone.now()},
            )
        # In-progress (COLLECTING) cycles, including a PENDING request to Ada so her
        # "feedback asks" tile is populated.
        for subject in emps[3:5]:
            fc, _ = self._ensure(
                FeedbackCycle, tenant_id=tenant.id, subject=subject,
                defaults={"opened_by": subject.manager, "status": "COLLECTING", "min_volume": 3},
            )
            self._ensure(FeedbackRequest, tenant_id=tenant.id, cycle=fc, giver=ada,
                         defaults={"relationship": "PEER", "status": "PENDING"})
            for p in emps[5:7]:
                self._ensure(FeedbackRequest, tenant_id=tenant.id, cycle=fc, giver=p,
                             defaults={"relationship": "PEER", "status": "SUBMITTED"})
                self._ensure(Feedback, tenant_id=tenant.id, cycle=fc, giver=p, kind="THREE_SIXTY",
                             defaults={"subject": subject, "relationship": "PEER",
                                       "body": "Strong collaborator who raises the bar.",
                                       "giver_marked_sensitive": False})

    # ── pending approvals + reviews-to-action for the demo manager (Ada) ────────
    def _approvals_for_ada(self, tenant, cycle, people):
        from apps.approvals.models import (
            ApprovalRoute, ApprovalStep, ApprovalStepInstance, ApprovalWorkflow,
        )
        from apps.reviews.models import Review

        ada = people["ada"]
        # Exclude Akhil so the showcase record stays clean (no pending approval on him).
        reports = [r for r in people["ada_reports"] if r.email != "akhil@acme.test"]
        if not reports:
            return
        wf, created = self._ensure(
            ApprovalWorkflow, tenant_id=tenant.id, name="Review sign-off", artifact_type="review",
            defaults={"mode": "SEQUENTIAL", "active": True},
        )
        if created:
            ApprovalStep.objects.create(tenant_id=tenant.id, workflow=wf, order=1,
                                        approver_kind="ROLE", approver_role="MANAGER", required=True)
            ApprovalStep.objects.create(tenant_id=tenant.id, workflow=wf, order=2,
                                        approver_kind="ROLE", approver_role="HRBP", required=True)
        # 6 of Ada's reports: a PENDING_HUMAN_REVIEW review + a PENDING approval step
        # resolved to Ada → her approvals inbox + "Reviews to action" tiles are full.
        for emp in reports[:6]:
            review, _ = self._ensure(
                Review, tenant_id=tenant.id, employee=emp, cycle=cycle,
                defaults={"reviewer": ada, "state": "PENDING_HUMAN_REVIEW", "source": "MANUAL",
                          "draft_body": "Strong, consistent delivery this cycle with clear growth areas."},
            )
            route, _ = self._ensure(
                ApprovalRoute, tenant_id=tenant.id, artifact_type="review", artifact_id=review.id,
                defaults={"workflow": wf, "mode": "SEQUENTIAL", "status": "IN_PROGRESS",
                          "initiated_by": ada, "started_at": timezone.now()},
            )
            self._ensure(
                ApprovalStepInstance, tenant_id=tenant.id, route=route, order=1,
                defaults={"approver": ada, "approver_role": "MANAGER", "required": True,
                          "status": "PENDING", "due_at": timezone.now() + datetime.timedelta(days=3)},
            )

    # ── JD library ──────────────────────────────────────────────────────────────
    def _jds(self, tenant, people):
        from apps.jd.models import JDVersion, JobDescription

        author = people["hrbps"][0] if people["hrbps"] else people["admin"]
        specs = [
            ("Staff Engineer", "L5", "Engineering", "PUBLISHED"),
            ("Engineering Manager", "M3", "Engineering", "PUBLISHED"),
            ("Senior Product Manager", "L5", "Product", "PUBLISHED"),
            ("Data Scientist", "L4", "Data", "PUBLISHED"),
            ("Analytics Engineer", "L4", "Data", "DRAFT"),
            ("Site Reliability Engineer", "L4", "Engineering", "PENDING_HUMAN_REVIEW"),
        ]
        for title, level, dept, status in specs:
            jd, created = self._ensure(
                JobDescription, tenant_id=tenant.id, title=title,
                defaults={"created_by": author, "level": level, "department": dept,
                          "status": status, "source": "MANUAL"},
            )
            if created:
                body = {
                    "summary": f"Owns delivery and impact as a {title}.",
                    "responsibilities": ["Lead key initiatives", "Mentor peers", "Drive quality"],
                    "must_haves": ["Relevant experience", "Strong communication"],
                    "nice_to_haves": ["Domain expertise"],
                }
                ver = JDVersion.objects.create(
                    tenant_id=tenant.id, jd=jd, created_by=author, version_number=1,
                    body=body, inputs_snapshot={}, is_published=(status == "PUBLISHED"),
                )
                if status == "PUBLISHED":
                    jd.current_version = ver
                    jd.save(update_fields=["current_version"])

    # ── succession + nine-box + plans ───────────────────────────────────────────
    def _succession(self, tenant, cycle, people):
        from apps.succession.models import (
            BenchCandidate, CriticalRole, NineBoxPlacement, SuccessionPlan,
        )

        hrbp = people["hrbps"][0]
        managers = people["managers"]
        emps = people["employees"]
        roles_spec = [
            ("Head of Platform", "CRITICAL", "HIGH", "Sole owner of the deploy pipeline."),
            ("Lead Data Scientist", "HIGH", "MEDIUM", "Deep model knowledge concentrated in one person."),
            ("Principal Designer", "HIGH", "MEDIUM", "Owns the design system end to end."),
        ]
        crit_roles = []
        for i, (name, crit, krisk, notes) in enumerate(roles_spec):
            cr, _ = self._ensure(
                CriticalRole, tenant_id=tenant.id, name=name,
                defaults={"marked_by": hrbp, "criticality": crit, "knowledge_risk": krisk,
                          "status": "ACTIVE", "incumbent": managers[i] if i < len(managers) else None,
                          "risk_notes": notes},
            )
            crit_roles.append(cr)
        # Bench for the first critical role.
        for cand, readiness in zip(emps[:4], ["READY_NOW", "READY_SOON", "DEVELOPING", "NOT_READY"]):
            self._ensure(BenchCandidate, tenant_id=tenant.id, critical_role=crit_roles[0], candidate=cand,
                         defaults={"readiness": readiness, "readiness_overridden": False})
        # Nine-box placements across the grid for the calibration view.
        box_specs = [("HIGH", "HIGH", 9), ("HIGH", "MEDIUM", 6), ("MEDIUM", "HIGH", 8),
                     ("MEDIUM", "MEDIUM", 5), ("LOW", "MEDIUM", 2), ("HIGH", "LOW", 3),
                     ("MEDIUM", "LOW", 4), ("LOW", "HIGH", 7), ("LOW", "LOW", 1)]
        for emp, (perf, pot, box) in zip(emps[:18], box_specs * 2):
            self._ensure(
                NineBoxPlacement, tenant_id=tenant.id, employee=emp, cycle=cycle,
                defaults={"performance_band": perf, "potential_band": pot, "box": box,
                          "assessed_by": hrbp, "assessed_at": timezone.now()},
            )
        # A deterministic plan PENDING_HUMAN_REVIEW for the first role.
        self._ensure(
            SuccessionPlan, tenant_id=tenant.id, critical_role=crit_roles[0], source="DETERMINISTIC",
            defaults={"status": "PENDING_HUMAN_REVIEW", "coverage_status": "AMBER",
                      "ranked_bench": [{"candidate": str(emps[0].id), "readiness": "READY_NOW"}],
                      "red_flags": [], "action_items": [{"text": "Pair successor with incumbent for one quarter."}],
                      "generated_at": timezone.now()},
        )
