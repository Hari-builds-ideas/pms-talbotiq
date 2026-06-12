"""
Shared factory_boy factories. Importable from any app's tests:

    from apps.testsupport.factories import TenantFactory, UserFactory

Model references are lazy strings so importing this module never requires the
app registry to be ready. ``UserFactory`` routes through the custom
``create_user`` manager so passwords are Argon2-hashed exactly as in production.
"""
import datetime
from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory


class TenantFactory(DjangoModelFactory):
    class Meta:
        model = "tenancy.Tenant"

    name = factory.Sequence(lambda n: f"Tenant {n}")
    slug = factory.Sequence(lambda n: f"tenant-{n}")
    status = "ACTIVE"


class UserFactory(DjangoModelFactory):
    class Meta:
        model = "identity.User"

    tenant = factory.SubFactory(TenantFactory)
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    role = "EMPLOYEE"
    is_active = True
    mfa_enabled = False
    password = "pass12345!"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", None)
        manager = model_class._default_manager
        return manager.create_user(*args, password=password, **kwargs)


class ScopedThingFactory(DjangoModelFactory):
    class Meta:
        model = "testsupport.ScopedThing"

    # tenant is intentionally NOT a SubFactory: callers pass it explicitly so
    # cross-tenant tests stay unambiguous about which tenant owns each row.
    name = factory.Sequence(lambda n: f"thing-{n}")


# ── Module 2 — Goals & KPI engine ──────────────────────────────────────────
# For the goal tree, tenant is DERIVED from the parent (employee/goal/kpi) via
# SelfAttribute so the whole graph stays in one tenant — passing independent
# SubFactories would create cross-tenant rows that the write-isolation save()
# rejects. Callers pass the parent objects explicitly.


class CycleFactory(DjangoModelFactory):
    class Meta:
        model = "cycles.PerformanceCycle"

    tenant = factory.SubFactory(TenantFactory)
    name = factory.Sequence(lambda n: f"Cycle {n}")
    start_date = datetime.date(2026, 1, 1)
    end_date = datetime.date(2026, 3, 31)
    status = "ACTIVE"


class GoalFactory(DjangoModelFactory):
    class Meta:
        model = "goals.Goal"

    # Pass employee= and cycle= (same tenant); tenant is derived from employee.
    tenant = factory.SelfAttribute("employee.tenant")
    created_by = factory.SelfAttribute("employee")
    title = factory.Sequence(lambda n: f"Goal {n}")
    weight = Decimal("100.00")
    status = "ACTIVE"


class KpiFactory(DjangoModelFactory):
    class Meta:
        model = "goals.Kpi"

    # Pass goal=; tenant is derived from the goal.
    tenant = factory.SelfAttribute("goal.tenant")
    name = factory.Sequence(lambda n: f"KPI {n}")
    weight = Decimal("100.00")
    target_value = Decimal("100.0000")
    direction = "INCREASING"
    unit = ""
    source = "MANUAL"


class KpiMeasurementFactory(DjangoModelFactory):
    class Meta:
        model = "goals.KpiMeasurement"

    # Pass kpi=; tenant is derived from the kpi.
    tenant = factory.SelfAttribute("kpi.tenant")
    value = Decimal("100.0000")
    recorded_at = factory.LazyFunction(timezone.now)
    source = "MANUAL"


class KpiTemplateFactory(DjangoModelFactory):
    class Meta:
        model = "goals.KpiTemplate"

    tenant = factory.SubFactory(TenantFactory)
    role = "EMPLOYEE"
    name = factory.Sequence(lambda n: f"Template KPI {n}")
    target_value = Decimal("100.0000")
    direction = "INCREASING"
    unit = ""
    default_weight = Decimal("100.00")


# ── Module 3 — Reviews & Appraisal Cycles ──────────────────────────────────


class ReviewFactory(DjangoModelFactory):
    class Meta:
        model = "reviews.Review"

    # Pass employee= and cycle= (same tenant); reviewer defaults to the
    # employee's manager when present. Tenant is derived from the employee.
    tenant = factory.SelfAttribute("employee.tenant")
    reviewer = factory.LazyAttribute(lambda o: o.employee.manager)
    state = "DRAFT"
    draft_body = ""


class ReviewAssessmentFactory(DjangoModelFactory):
    class Meta:
        model = "reviews.ReviewAssessment"

    # Pass review= and assessor= (same tenant); tenant derives from the review.
    tenant = factory.SelfAttribute("review.tenant")
    assessment_type = "MANAGER"
    body = factory.Sequence(lambda n: f"Assessment body {n}")
    submitted_at = factory.LazyFunction(timezone.now)


# ── Module 4 — 360° Feedback & anonymisation ───────────────────────────────


class FeedbackCycleFactory(DjangoModelFactory):
    class Meta:
        model = "feedback.FeedbackCycle"

    # Pass subject= ; tenant derives from the subject.
    tenant = factory.SelfAttribute("subject.tenant")
    opened_by = factory.LazyAttribute(lambda o: o.subject.manager)
    status = "COLLECTING"


class FeedbackRequestFactory(DjangoModelFactory):
    class Meta:
        model = "feedback.FeedbackRequest"

    # Pass cycle= and giver= (same tenant); tenant derives from the cycle.
    tenant = factory.SelfAttribute("cycle.tenant")
    relationship = "PEER"
    status = "PENDING"


class FeedbackFactory(DjangoModelFactory):
    class Meta:
        model = "feedback.Feedback"

    # Pass cycle= (or cycle=None + subject=) and giver=; tenant from the giver.
    tenant = factory.SelfAttribute("giver.tenant")
    subject = factory.LazyAttribute(lambda o: o.cycle.subject if o.cycle else None)
    relationship = "PEER"
    kind = "THREE_SIXTY"
    body = factory.Sequence(lambda n: f"Feedback body {n}")
    giver_marked_sensitive = False


class OneOnOneNoteFactory(DjangoModelFactory):
    class Meta:
        model = "feedback.OneOnOneNote"

    # Pass manager= and employee= (same tenant); tenant from the manager.
    tenant = factory.SelfAttribute("manager.tenant")
    body = factory.Sequence(lambda n: f"1:1 notes {n}")
    meeting_date = datetime.date(2026, 5, 1)


# ── Module 5 — Approval Workflows ───────────────────────────────────────────


class ApprovalWorkflowFactory(DjangoModelFactory):
    class Meta:
        model = "approvals.ApprovalWorkflow"

    tenant = factory.SubFactory(TenantFactory)
    name = factory.Sequence(lambda n: f"Workflow {n}")
    artifact_type = "review"
    mode = "SEQUENTIAL"
    active = True


class ApprovalStepFactory(DjangoModelFactory):
    class Meta:
        model = "approvals.ApprovalStep"

    # Pass workflow= ; tenant derives from the workflow.
    tenant = factory.SelfAttribute("workflow.tenant")
    order = factory.Sequence(lambda n: n + 1)
    approver_kind = "ROLE"
    approver_role = "HRBP"
    approver_user = None
    required = True


# ── Module 6 — JD Library & AI JD Generator ─────────────────────────────────
# tenant is derived from created_by / jd via SelfAttribute so the JD + its
# versions stay in one tenant; callers pass the parent objects explicitly.


def _sample_jd_body(n):
    return {
        "summary": f"Owns delivery for role {n}.",
        "responsibilities": ["Ship features", "Mentor peers"],
        "must_haves": ["3+ years experience"],
        "nice_to_haves": ["Domain knowledge"],
    }


class JobDescriptionFactory(DjangoModelFactory):
    class Meta:
        model = "jd.JobDescription"

    # Pass created_by= ; tenant is derived from the author.
    tenant = factory.SelfAttribute("created_by.tenant")
    title = factory.Sequence(lambda n: f"Engineer {n}")
    level = "L3"
    department = "Engineering"
    status = "DRAFT"
    source = "MANUAL"


class JDVersionFactory(DjangoModelFactory):
    class Meta:
        model = "jd.JDVersion"

    # Pass jd= ; tenant is derived from the JD. created_by defaults to its author.
    tenant = factory.SelfAttribute("jd.tenant")
    created_by = factory.SelfAttribute("jd.created_by")
    version_number = factory.Sequence(lambda n: n + 1)
    body = factory.Sequence(_sample_jd_body)
    inputs_snapshot = factory.LazyFunction(dict)
    is_published = False


class JDTemplateFactory(DjangoModelFactory):
    class Meta:
        model = "jd.JDTemplate"

    tenant = factory.SubFactory(TenantFactory)
    role_family = "Engineering"
    title_pattern = factory.Sequence(lambda n: f"Engineer {n}")
    level = "L3"
    default_body = factory.Sequence(_sample_jd_body)


class JDRequestFactory(DjangoModelFactory):
    class Meta:
        model = "jd.JDRequest"

    # Pass requested_by= ; tenant is derived from the requester.
    tenant = factory.SelfAttribute("requested_by.tenant")
    title = factory.Sequence(lambda n: f"Requested role {n}")
    level = "L3"
    notes = ""
    status = "OPEN"


# ── Module 7 — Live Org Chart ────────────────────────────────────────────────


class PositionFactory(DjangoModelFactory):
    class Meta:
        model = "org.Position"

    # Pass reports_to= (a User); tenant is derived from that manager. created_by
    # defaults to the same manager unless overridden.
    tenant = factory.SelfAttribute("reports_to.tenant")
    created_by = factory.SelfAttribute("reports_to")
    title = factory.Sequence(lambda n: f"Open Role {n}")
    department = "Engineering"
    status = "OPEN"
    opened_at = factory.LazyFunction(timezone.now)


# ── Module 8 — Succession & Talent ───────────────────────────────────────────


class CriticalRoleFactory(DjangoModelFactory):
    class Meta:
        model = "succession.CriticalRole"

    # Pass marked_by= (a User); tenant is derived from that HRBP/Admin.
    tenant = factory.SelfAttribute("marked_by.tenant")
    name = factory.Sequence(lambda n: f"Critical Role {n}")
    criticality = "HIGH"
    knowledge_risk = "LOW"
    status = "ACTIVE"


class BenchCandidateFactory(DjangoModelFactory):
    class Meta:
        model = "succession.BenchCandidate"

    # Pass critical_role= and candidate= (same tenant); tenant from the role.
    tenant = factory.SelfAttribute("critical_role.tenant")
    readiness = "NOT_READY"
    readiness_overridden = False


class NineBoxPlacementFactory(DjangoModelFactory):
    class Meta:
        model = "succession.NineBoxPlacement"

    # Pass employee= and cycle= (same tenant); tenant from the employee.
    tenant = factory.SelfAttribute("employee.tenant")
    performance_band = "MEDIUM"
    potential_band = "MEDIUM"
    box = 5
    assessed_at = factory.LazyFunction(timezone.now)


class SuccessionPlanFactory(DjangoModelFactory):
    class Meta:
        model = "succession.SuccessionPlan"

    # Pass critical_role= ; tenant from the role.
    tenant = factory.SelfAttribute("critical_role.tenant")
    status = "PENDING_HUMAN_REVIEW"
    ranked_bench = factory.LazyFunction(list)
    coverage_status = "RED"
    red_flags = factory.LazyFunction(list)
    action_items = factory.LazyFunction(list)
    source = "DETERMINISTIC"
    generated_at = factory.LazyFunction(timezone.now)


# ── Module 9 — Career Development (Roadmap LITE) ──────────────────────────────


class TargetRoleSelectionFactory(DjangoModelFactory):
    class Meta:
        model = "career.TargetRoleSelection"

    # Pass employee= and exactly one of target_jd= / target_position=; tenant
    # derives from the employee.
    tenant = factory.SelfAttribute("employee.tenant")
    selected_by = factory.SelfAttribute("employee")
    selected_at = factory.LazyFunction(timezone.now)


class DevelopmentRoadmapFactory(DjangoModelFactory):
    class Meta:
        model = "career.DevelopmentRoadmap"

    # Pass employee= and a target; tenant derives from the employee.
    tenant = factory.SelfAttribute("employee.tenant")
    status = "ACTIVE"
    tiers = factory.LazyFunction(list)
    skill_gap = factory.LazyFunction(dict)
    source = "DETERMINISTIC"
    advisory = True
    generated_at = factory.LazyFunction(timezone.now)


class RoadmapProgressFactory(DjangoModelFactory):
    class Meta:
        model = "career.RoadmapProgress"

    # Pass roadmap= ; tenant derives from the roadmap.
    tenant = factory.SelfAttribute("roadmap.tenant")
    tier_index = 0
    status = "NOT_STARTED"
