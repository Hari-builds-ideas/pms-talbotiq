"""
seed_demo — build a realistic, idempotent demo a company would recognise.

Creates two tenants so the commercial story is demoable:
  * ``acme``   — FULL_AI, the rich tenant (full org, cycle, goals/KPIs/scores,
                 reviews in several states, a 360 cycle, approval workflows,
                 JD library, positions + a vacancy, succession + nine-box + a
                 plan, career roadmaps, audit rows).
  * ``globex`` — STARTER, a smaller tenant whose premium features are LOCKED, so
                 the upgrade-to-FULL_AI flow has a real before/after.

Idempotent: every row is created via ``_ensure`` (reuse-first get-or-create) on
natural keys, so re-running adds nothing and never duplicates — and, unlike
``get_or_create``, it tolerates rows the app itself can create many of (a
SuccessionPlan / DevelopmentRoadmap per generate/enrich), reusing the first match
instead of raising ``MultipleObjectsReturned``. (We never DELETE — audit rows are
delete-blocked by DB triggers by design.) Re-run safely with:

    docker compose run --rm web python manage.py seed_demo
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record as audit_record
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

DEMO_PASSWORD = "Passw0rd!demo"  # documented demo credential (non-secret)


class Command(BaseCommand):
    help = "Seed a realistic, idempotent demo tenant set (acme=FULL_AI, globex=STARTER)."

    @staticmethod
    def _ensure(model, *, defaults=None, **lookup):
        """Idempotent get-or-create that tolerates MULTIPLE existing matches.

        ``get_or_create`` raises ``MultipleObjectsReturned`` when its lookup is not
        a true uniqueness key and more than one row matches — which happens for
        rows the app itself can create many of (a SuccessionPlan / DevelopmentRoadmap
        per generate/enrich, a TargetRoleSelection per chosen target, …). This
        reuses the FIRST existing match (so a re-run never double-creates and never
        crashes), else creates one. Returns ``(obj, created)`` like get_or_create.
        """
        obj = model.objects.filter(**lookup).first()
        if obj is not None:
            return obj, False
        return model.objects.create(**lookup, **(defaults or {})), True

    def handle(self, *args, **options):
        acme = self._seed_tenant(
            slug="acme", name="Acme Corporation", packs=["STARTER", "FULL_AI"], rich=True
        )
        globex = self._seed_tenant(
            slug="globex", name="Globex Industries", packs=["STARTER"], rich=False
        )
        self.stdout.write(self.style.SUCCESS(
            f"Seed complete. Tenants: {acme.slug} (FULL_AI), {globex.slug} (STARTER). "
            f"Login with any seeded email + password '{DEMO_PASSWORD}'."
        ))

    # ── tenant ────────────────────────────────────────────────────────────────
    def _seed_tenant(self, *, slug, name, packs, rich):
        tenant, _ = Tenant.objects.get_or_create(
            slug=slug, defaults={"name": name, "status": "ACTIVE"}
        )
        with tenant_context(tenant.id):
            with transaction.atomic():
                self._build(tenant, packs=packs, rich=rich)
        self.stdout.write(f"  · {slug}: built")
        return tenant

    def _build(self, tenant, *, packs, rich):
        from apps.billing.models import Entitlement

        # Entitlement (commercial story).
        self._ensure(
            Entitlement,
            tenant_id=tenant.id,
            defaults={"seat_count": 50 if rich else 15, "feature_packs": packs},
        )

        people = self._people(tenant, rich=rich)
        cycle = self._cycle(tenant)
        self._goals_and_scores(tenant, cycle, people)
        self._reviews(tenant, cycle, people)
        self._feedback(tenant, people)
        self._approvals(tenant)
        jds = self._jds(tenant, people)
        self._positions(tenant, people, jds)
        if rich:
            self._succession(tenant, cycle, people)
            self._career(tenant, people, jds)
        self._audit(tenant, people)

    # ── people / org tree ───────────────────────────────────────────────────────
    def _people(self, tenant, *, rich):
        """A real reporting tree: Admin → HRBPs → Managers → Employees."""
        admin = self._user(tenant, "admin", "Avery Stone", "ADMIN", manager=None)
        people = {"admin": admin, "employees": [], "managers": [], "hrbps": []}

        hrbp_specs = [("priya", "Priya Nair"), ("dan", "Daniel Cohen")] if rich else [("priya", "Priya Nair")]
        hrbps = [self._user(tenant, e, n, "HRBP", manager=admin) for e, n in hrbp_specs]
        people["hrbps"] = hrbps

        mgr_specs = (
            [("ada", "Ada Lovelace"), ("lin", "Lin Zhao"), ("marco", "Marco Rossi"),
             ("sara", "Sara Haddad"), ("tom", "Tom Becker")]
            if rich else [("ada", "Ada Lovelace")]
        )
        managers = []
        for i, (e, n) in enumerate(mgr_specs):
            mgr = self._user(tenant, e, n, "MANAGER", manager=hrbps[i % len(hrbps)])
            managers.append(mgr)
        people["managers"] = managers

        emp_names = [
            ("reza", "Reza Pahlavi"), ("sam", "Sam Okafor"), ("mia", "Mia Fontaine"),
            ("omar", "Omar Haddad"), ("noah", "Noah Bergstrom"), ("ella", "Ella Nyberg"),
            ("kai", "Kai Andersen"), ("yuki", "Yuki Tanaka"), ("zoe", "Zoe Martin"),
            ("ravi", "Ravi Menon"), ("ines", "Ines Garcia"), ("paul", "Paul Dubois"),
            ("nadia", "Nadia Aziz"), ("leo", "Leo Schmidt"), ("hana", "Hana Kim"),
            ("ben", "Ben Carter"), ("amir", "Amir Khan"), ("clara", "Clara Vidal"),
            ("finn", "Finn O'Brien"), ("gita", "Gita Rao"),
        ]
        if not rich:
            emp_names = emp_names[:4]
        employees = []
        for i, (e, n) in enumerate(emp_names):
            mgr = managers[i % len(managers)]
            employees.append(self._user(tenant, e, n, "EMPLOYEE", manager=mgr))
        people["employees"] = employees
        return people

    def _user(self, tenant, local, display_name, role, manager):
        from apps.identity.models import User

        email = f"{local}@{tenant.slug}.test"
        existing = User.objects.filter(email=email).first()
        if existing:
            changed = False
            if existing.manager_id != (manager.id if manager else None):
                existing.manager = manager
                changed = True
            if existing.display_name != display_name:
                existing.display_name = display_name
                changed = True
            if changed:
                existing.save(update_fields=["manager", "display_name"])
            return existing
        return User.objects.create_user(
            email=email, password=DEMO_PASSWORD, tenant=tenant, role=role,
            display_name=display_name, manager=manager,
        )

    # ── cycle ─────────────────────────────────────────────────────────────────
    def _cycle(self, tenant):
        from apps.cycles.models import PerformanceCycle

        cycle, _ = self._ensure(
            PerformanceCycle,
            tenant_id=tenant.id, name="H1 2026",
            defaults={
                "start_date": datetime.date(2026, 1, 1),
                "end_date": datetime.date(2026, 6, 30),
                "status": "ACTIVE",
            },
        )
        return cycle

    # ── goals + KPIs + measurements + scores ────────────────────────────────────
    def _goals_and_scores(self, tenant, cycle, people):
        from apps.goals.models import Goal, Kpi, KpiMeasurement
        from apps.goals.scoring.engine import compute_cycle_scores

        # Realistic, varied attainment so CycleScores spread across the risk bands
        # (the deterministic engine normalises to cohort-relative T-scores).
        subjects = people["employees"] + people["managers"]
        attainment_cycle = [0.97, 0.62, 0.34, 0.85, 0.48, 0.30, 1.0, 0.74, 0.40, 0.55,
                            0.92, 0.36, 0.68, 0.32, 0.88, 0.58, 0.45, 0.78, 0.38, 0.95,
                            0.70, 0.50, 0.82, 0.42]
        for i, emp in enumerate(subjects):
            goal, _ = self._ensure(
                Goal,
                tenant_id=tenant.id, employee=emp, cycle=cycle, title="Deliver cycle objectives",
                defaults={"weight": Decimal("100.00"), "status": "ACTIVE", "created_by": emp,
                          "description": "Primary objective for the performance cycle.",
                          "objective": "Hit committed KPIs for H1 2026."},
            )
            kpi_specs = [("Throughput", Decimal("60.00")), ("Quality", Decimal("40.00"))]
            attain = attainment_cycle[i % len(attainment_cycle)]
            for name, weight in kpi_specs:
                kpi, _ = self._ensure(
                    Kpi,
                    tenant_id=tenant.id, goal=goal, name=name,
                    defaults={"weight": weight, "target_value": Decimal("100.0000"),
                              "direction": "INCREASING", "unit": "%", "source": "MANUAL"},
                )
                # Refresh on re-run so the demo's score spread is deterministic:
                # replace any existing measurement with the intended actual.
                KpiMeasurement.objects.filter(kpi=kpi).delete()
                KpiMeasurement.objects.create(
                    tenant_id=tenant.id, kpi=kpi,
                    value=Decimal(str(round(attain * 100, 2))),
                    recorded_at=timezone.now(), source="MANUAL",
                )
        compute_cycle_scores(tenant.id, cycle.id)

    # ── reviews (several states) ──────────────────────────────────────────────
    def _reviews(self, tenant, cycle, people):
        from apps.reviews.models import Review, ReviewAssessment

        emps = people["employees"]
        if not emps:
            return
        # (employee_index, state) — exercise the spectrum.
        specs = [
            (0, "PENDING_HUMAN_REVIEW"), (1, "DRAFT"), (2, "APPROVED"),
            (3, "REJECTED"),
        ]
        for idx, state in specs:
            if idx >= len(emps):
                continue
            emp = emps[idx]
            reviewer = emp.manager
            defaults = {
                "reviewer": reviewer,
                "state": state,
                "draft_body": "Strong, consistent delivery this cycle with clear growth areas.",
                "source": "MANUAL",
            }
            if state == "APPROVED":
                defaults.update(human_reviewer=reviewer, approved_at=timezone.now(),
                                final_body="Endorsed: a solid half with room to stretch next cycle.")
            if state == "REJECTED":
                defaults.update(rejected_reason="Needs concrete KPI evidence before approval.")
            review, _ = self._ensure(
                Review,
                tenant_id=tenant.id, employee=emp, cycle=cycle, defaults=defaults,
            )
            self._ensure(
                ReviewAssessment,
                tenant_id=tenant.id, review=review, assessment_type="SELF",
                defaults={"assessor": emp, "body": "Proud of my delivery; want to grow in communication.",
                          "submitted_at": timezone.now()},
            )
            if reviewer:
                self._ensure(
                    ReviewAssessment,
                    tenant_id=tenant.id, review=review, assessment_type="MANAGER",
                    defaults={"assessor": reviewer, "body": "Reliable and technically strong.",
                              "submitted_at": timezone.now()},
                )

    # ── 360 feedback ──────────────────────────────────────────────────────────
    def _feedback(self, tenant, people):
        from apps.feedback.models import Feedback, FeedbackCycle, FeedbackRequest

        emps = people["employees"]
        if len(emps) < 4:
            return
        subject = emps[0]
        opener = subject.manager
        fc, _ = self._ensure(
            FeedbackCycle,
            tenant_id=tenant.id, subject=subject,
            defaults={"opened_by": opener, "status": "COLLECTING", "min_volume": 3},
        )
        givers = [emps[1], emps[2], emps[3]] + ([subject.manager] if subject.manager else [])
        rels = ["PEER", "PEER", "PEER", "MANAGER"]
        bodies = [
            "Dependable teammate who unblocks others quickly.",
            "Communicates trade-offs clearly; could delegate more.",
            "Strong technical judgement on the platform work.",
            "Consistently meets commitments; ready for more scope.",
        ]
        for giver, rel, body in zip(givers, rels, bodies):
            if giver is None:
                continue
            self._ensure(
                FeedbackRequest,
                tenant_id=tenant.id, cycle=fc, giver=giver,
                defaults={"relationship": rel, "status": "SUBMITTED"},
            )
            self._ensure(
                Feedback,
                tenant_id=tenant.id, cycle=fc, giver=giver, kind="THREE_SIXTY",
                defaults={"subject": subject, "relationship": rel,
                          "body": body, "giver_marked_sensitive": False},
            )

    # ── approval workflows ────────────────────────────────────────────────────
    def _approvals(self, tenant):
        from apps.approvals.models import ApprovalStep, ApprovalWorkflow

        wf, created = self._ensure(
            ApprovalWorkflow,
            tenant_id=tenant.id, name="Review sign-off", artifact_type="review",
            defaults={"mode": "SEQUENTIAL", "active": True},
        )
        if created:
            ApprovalStep.objects.create(tenant_id=tenant.id, workflow=wf, order=1,
                                        approver_kind="ROLE", approver_role="MANAGER", required=True)
            ApprovalStep.objects.create(tenant_id=tenant.id, workflow=wf, order=2,
                                        approver_kind="ROLE", approver_role="HRBP", required=True)
        wf2, created2 = self._ensure(
            ApprovalWorkflow,
            tenant_id=tenant.id, name="JD publication", artifact_type="jd",
            defaults={"mode": "PARALLEL", "active": True},
        )
        if created2:
            ApprovalStep.objects.create(tenant_id=tenant.id, workflow=wf2, order=1,
                                        approver_kind="ROLE", approver_role="HRBP", required=True)

    # ── JD library ────────────────────────────────────────────────────────────
    def _jds(self, tenant, people):
        from apps.jd.models import JDVersion, JobDescription

        author = people["hrbps"][0] if people["hrbps"] else people["admin"]
        out = {}
        specs = [
            ("Staff Engineer", "L5", "Engineering", "PUBLISHED"),
            ("Engineering Manager", "M3", "Engineering", "PUBLISHED"),
            ("Analytics Engineer", "L4", "Data", "DRAFT"),
            ("Site Reliability Engineer", "L4", "Engineering", "PENDING_HUMAN_REVIEW"),
        ]
        for title, level, dept, status in specs:
            jd, created = self._ensure(
                JobDescription,
                tenant_id=tenant.id, title=title,
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
            out[title] = jd
        return out

    # ── org positions (incl. an OPEN vacancy) ───────────────────────────────────
    def _positions(self, tenant, people, jds):
        from apps.org.models import Position

        mgr = people["managers"][0] if people["managers"] else people["admin"]
        published = next((j for j in jds.values() if j.status == "PUBLISHED"), None)
        self._ensure(
            Position,
            tenant_id=tenant.id, title="Senior Engineer", reports_to=mgr,
            defaults={"department": "Engineering", "status": "OPEN", "created_by": mgr,
                      "opened_at": timezone.now(),
                      "published_jd": published if published else None},
        )
        self._ensure(
            Position,
            tenant_id=tenant.id, title="Engineering Manager",
            reports_to=people["hrbps"][0] if people["hrbps"] else people["admin"],
            defaults={"department": "Engineering", "status": "FILLED", "created_by": people["admin"],
                      "filled_by": mgr, "opened_at": timezone.now(), "filled_at": timezone.now()},
        )

    # ── succession + nine-box + plan ─────────────────────────────────────────────
    def _succession(self, tenant, cycle, people):
        from apps.succession.models import (
            BenchCandidate, CriticalRole, NineBoxPlacement, SuccessionPlan,
        )

        hrbp = people["hrbps"][0]
        managers = people["managers"]
        emps = people["employees"]
        cr1, _ = self._ensure(
            CriticalRole,
            tenant_id=tenant.id, name="Head of Platform",
            defaults={"marked_by": hrbp, "criticality": "CRITICAL", "knowledge_risk": "HIGH",
                      "status": "ACTIVE", "incumbent": managers[0] if managers else None,
                      "risk_notes": "Sole owner of the deploy pipeline."},
        )
        self._ensure(
            CriticalRole,
            tenant_id=tenant.id, name="Lead Data Scientist",
            defaults={"marked_by": hrbp, "criticality": "HIGH", "knowledge_risk": "MEDIUM",
                      "status": "ACTIVE", "incumbent": managers[1] if len(managers) > 1 else None},
        )
        # Bench for cr1
        for cand, readiness in zip(emps[:3], ["READY_SOON", "DEVELOPING", "NOT_READY"]):
            self._ensure(
                BenchCandidate,
                tenant_id=tenant.id, critical_role=cr1, candidate=cand,
                defaults={"readiness": readiness, "readiness_overridden": False},
            )
        # Nine-box placements across boxes for the calibration grid.
        box_specs = [("HIGH", "HIGH", 9), ("HIGH", "MEDIUM", 6), ("MEDIUM", "HIGH", 8),
                     ("MEDIUM", "MEDIUM", 5), ("LOW", "MEDIUM", 2), ("HIGH", "LOW", 3),
                     ("MEDIUM", "LOW", 4), ("LOW", "HIGH", 7)]
        for emp, (perf, pot, box) in zip(emps, box_specs):
            self._ensure(
                NineBoxPlacement,
                tenant_id=tenant.id, employee=emp, cycle=cycle,
                defaults={"performance_band": perf, "potential_band": pot, "box": box,
                          "assessed_by": hrbp, "assessed_at": timezone.now()},
            )
        # A deterministic plan PENDING_HUMAN_REVIEW for cr1. The app creates a NEW
        # SuccessionPlan on every generate/enrich, so (tenant, role, source) is NOT
        # unique — _ensure reuses the first existing one instead of crashing.
        self._ensure(
            SuccessionPlan,
            tenant_id=tenant.id, critical_role=cr1, source="DETERMINISTIC",
            defaults={"status": "PENDING_HUMAN_REVIEW", "coverage_status": "AMBER",
                      "ranked_bench": [{"candidate": str(emps[0].id), "readiness": "READY_SOON"}],
                      "red_flags": [], "action_items": [{"text": "Pair successor with incumbent for one quarter."}],
                      "generated_at": timezone.now()},
        )

    # ── career roadmaps ──────────────────────────────────────────────────────────
    def _career(self, tenant, people, jds):
        from apps.career.models import DevelopmentRoadmap, TargetRoleSelection

        published = next((j for j in jds.values() if j.status == "PUBLISHED"), None)
        if published is None:
            return
        for emp in people["employees"][:3]:
            # An employee may hold several targets/roadmaps (per chosen target;
            # regenerate/enrich add more) — these lookups are NOT unique, so use
            # _ensure (reuse-first) rather than get_or_create.
            self._ensure(
                TargetRoleSelection,
                tenant_id=tenant.id, employee=emp,
                defaults={"selected_by": emp, "target_jd": published, "selected_at": timezone.now()},
            )
            self._ensure(
                DevelopmentRoadmap,
                tenant_id=tenant.id, employee=emp,
                defaults={"status": "ACTIVE", "source": "DETERMINISTIC", "advisory": True,
                          "target_jd": published, "generated_at": timezone.now(),
                          "tiers": [{"index": 0, "title": "Reach sustained HIGH performance",
                                     "detail": "Close the current gap on quality KPIs.", "basis": "deterministic"},
                                    {"index": 1, "title": "Lead a cross-team initiative",
                                     "detail": "Demonstrate scope beyond your team.", "basis": "deterministic"}],
                          "skill_gap": {"current_performance_band": "MEDIUM", "required_performance_band": "HIGH",
                                        "performance_band_gap": 1, "weak_categories": ["Quality"]}},
            )

    # ── audit rows ───────────────────────────────────────────────────────────────
    def _audit(self, tenant, people):
        from apps.audit.models import AuditLog

        if AuditLog.objects.filter(tenant_id=tenant.id, action="demo.seeded").exists():
            return
        admin = people["admin"]
        audit_record(action="demo.seeded", actor=admin, target_type="tenant",
                     target_id=str(tenant.id), justification="Demo data seeded.",
                     metadata={"source": "seed_demo"}, tenant=tenant)
        if people["employees"]:
            audit_record(action="user.created", actor=admin, target_type="user",
                         target_id=str(people["employees"][0].id),
                         metadata={"role": "EMPLOYEE"}, tenant=tenant)
