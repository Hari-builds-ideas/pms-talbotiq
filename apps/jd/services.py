"""
JD library services that sit alongside the lifecycle: template seeding +
instantiation, role-scoped library search, and export rendering.

* Templates — a deterministic per-role-family catalogue, idempotently seeded per
  tenant (mirrors the Module-2 KPI-template seed), and instantiated into a real
  DRAFT JobDescription (+ v1) through the audited ``lifecycle.create_jd`` path.
* Search — ``visible_jds`` returns the JDs an actor may see, applying the §2
  scope rule: managers+ see the whole tenant library; everyone else sees only
  PUBLISHED entries. ``search_jds`` filters that base by text/status.
* Export — ``render_jd_text`` / ``jd_export`` render a published (or working)
  version as plain text and structured JSON. NO binary PDF/docx (out of scope;
  Module 14).
"""
from django.db.models import Q

from apps.audit.services import record
from apps.rbac.matrix import Role
from apps.tenancy.context import tenant_context

from . import lifecycle
from .exceptions import IllegalJDTransition
from .models import JDRequest, JDTemplate, JobDescription

# Deterministic role-family scaffolds. Each carries a complete body skeleton so
# an instantiated JD is immediately editable (and, once the must-haves are filled,
# submittable). Text only — no AI.
DEFAULT_TEMPLATES = [
    {
        "role_family": "Engineering",
        "title_pattern": "Software Engineer",
        "level": "L3",
        "default_body": {
            "summary": "Builds and maintains software in a product team.",
            "responsibilities": [
                "Design, build and ship features",
                "Review peers' code and uphold quality",
                "Operate and support what you build",
            ],
            "must_haves": [
                "Professional software engineering experience",
                "Fluency in at least one production language",
            ],
            "nice_to_haves": ["Domain experience", "Cloud platform familiarity"],
        },
    },
    {
        "role_family": "Engineering",
        "title_pattern": "Engineering Manager",
        "level": "M1",
        "default_body": {
            "summary": "Leads an engineering team's delivery and growth.",
            "responsibilities": [
                "Own team delivery and roadmap execution",
                "Coach, grow and performance-manage engineers",
                "Partner with product and design on priorities",
            ],
            "must_haves": [
                "Experience leading software teams",
                "Track record of shipping with a team",
            ],
            "nice_to_haves": ["Experience scaling teams", "Hiring experience"],
        },
    },
    {
        "role_family": "Sales",
        "title_pattern": "Account Executive",
        "level": "IC2",
        "default_body": {
            "summary": "Owns a sales quota and closes new business.",
            "responsibilities": [
                "Manage a pipeline from prospecting to close",
                "Run discovery and demos with prospects",
                "Forecast accurately each period",
            ],
            "must_haves": [
                "Quota-carrying sales experience",
                "Consultative selling skills",
            ],
            "nice_to_haves": ["Industry network", "CRM proficiency"],
        },
    },
    {
        "role_family": "People",
        "title_pattern": "HR Business Partner",
        "level": "P3",
        "default_body": {
            "summary": "Partners with a business unit on its people agenda.",
            "responsibilities": [
                "Advise managers on performance and development",
                "Drive cycle completion across the business unit",
                "Support org design and workforce planning",
            ],
            "must_haves": [
                "HR business-partnering experience",
                "Strong stakeholder management",
            ],
            "nice_to_haves": ["People-analytics literacy", "Coaching certification"],
        },
    },
]


def seed_templates_for_tenant(tenant) -> int:
    """Idempotently create :class:`JDTemplate` rows for ``tenant`` from
    :data:`DEFAULT_TEMPLATES`; return the number created.

    Skips any template already present for ``(tenant, role_family, title_pattern)``
    so repeated runs never duplicate. Runs under ``tenant_context`` so it works
    from system code (the seed command) with no bound request.
    """
    created = 0
    with tenant_context(tenant):
        for definition in DEFAULT_TEMPLATES:
            _, was_created = JDTemplate.objects.get_or_create(
                role_family=definition["role_family"],
                title_pattern=definition["title_pattern"],
                defaults={
                    "level": definition["level"],
                    "default_body": definition["default_body"],
                },
            )
            if was_created:
                created += 1
    return created


def instantiate_template(*, template, actor, title=None, level=None, department=""):
    """Create a DRAFT :class:`JobDescription` (+ v1) from ``template`` via the
    audited ``lifecycle.create_jd`` path. Title/level default to the template's
    pattern/level; the body is a deep copy of the template scaffold so later
    edits never mutate the template."""
    import copy

    return lifecycle.create_jd(
        title=title or template.title_pattern,
        level=level or template.level,
        department=department,
        actor=actor,
        body=copy.deepcopy(template.default_body),
        inputs={"template_id": str(template.id), "role_family": template.role_family},
        source=JobDescription.Source.MANUAL,
    )


def visible_jds(actor):
    """The JobDescription queryset ``actor`` may see (tenant-scoped already by the
    default manager). §2 scope rule: MANAGER/HRBP/ADMIN see the whole library;
    EMPLOYEE sees PUBLISHED entries only. Returns a queryset (caller can filter)."""
    qs = JobDescription.objects.all()
    if actor.role not in (Role.MANAGER, Role.HRBP, Role.ADMIN):
        qs = qs.filter(status=JobDescription.Status.PUBLISHED)
    return qs


def search_jds(actor, *, q="", status=None):
    """Search the actor-visible library by free text (title/level/department) and
    optional status. Status is applied on top of the scope rule, so an employee
    can never widen past PUBLISHED."""
    qs = visible_jds(actor)
    if q:
        qs = qs.filter(
            Q(title__icontains=q) | Q(level__icontains=q) | Q(department__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)
    # created_by_name derefs the author FK per row — resolve it in one JOIN.
    return qs.select_related("created_by")


# ── JD requests (Manager asks HRBP to author/generate a JD) ──────────────────


def create_jd_request(*, requester, title, level="", notes=""):
    """Create an OPEN :class:`JDRequest` from ``requester`` (a Manager+). The
    requester + tenant are server-set; audited before the row exists."""
    tenant_id = requester.tenant_id
    with tenant_context(tenant_id):
        record(
            action="request.created",
            actor=requester,
            target_type="jd_request",
            target_id="",
            metadata={"title": title, "level": level},
            tenant=tenant_id,
        )
        return JDRequest.objects.create(
            tenant_id=tenant_id,
            requested_by=requester,
            title=title,
            level=level,
            notes=notes,
            status=JDRequest.Status.OPEN,
        )


def fulfil_jd_request(*, request, jd, actor):
    """Mark an OPEN request FULFILLED, linking the JD that satisfies it. 409 if
    the request is not OPEN. Audited before the effect."""
    with tenant_context(request.tenant_id):
        if request.status != JDRequest.Status.OPEN:
            raise IllegalJDTransition(request.status, "fulfil")
        record(
            action="request.fulfilled",
            actor=actor,
            target_type="jd_request",
            target_id=request.id,
            metadata={"jd": str(jd.id)},
            tenant=request.tenant_id,
        )
        request.status = JDRequest.Status.FULFILLED
        request.fulfilled_jd = jd
        request.save(update_fields=["status", "fulfilled_jd", "updated_at"])
        return request


def decline_jd_request(*, request, actor, reason=""):
    """Mark an OPEN request DECLINED. 409 if not OPEN. Audited before the effect."""
    with tenant_context(request.tenant_id):
        if request.status != JDRequest.Status.OPEN:
            raise IllegalJDTransition(request.status, "decline")
        record(
            action="request.declined",
            actor=actor,
            target_type="jd_request",
            target_id=request.id,
            metadata={"reason": reason},
            tenant=request.tenant_id,
        )
        request.status = JDRequest.Status.DECLINED
        request.save(update_fields=["status", "updated_at"])
        return request


def visible_jd_requests(actor):
    """The JDRequest queryset ``actor`` may see: a Manager sees their OWN
    requests; HRBP/Admin see the whole tenant's requests (they fulfil them)."""
    qs = JDRequest.objects.all()
    if actor.role == Role.MANAGER:
        qs = qs.filter(requested_by_id=actor.id)
    return qs


def _resolve_export_version(jd):
    """The version to export: the live published one, else the working draft."""
    if jd.current_version_id:
        return jd.current_version
    return lifecycle.working_version(jd)


def render_jd_text(jd, version=None) -> str:
    """Render a JD version as human-readable plain text (no binary export)."""
    version = version or _resolve_export_version(jd)
    body = (version.body if version else {}) or {}
    lines = [
        f"{jd.title} ({jd.level})",
        f"Department: {jd.department}" if jd.department else "",
        "",
        "Summary",
        body.get("summary", "").strip(),
    ]

    def _section(heading, items):
        if items:
            lines.append("")
            lines.append(heading)
            lines.extend(f"  - {item}" for item in items)

    _section("Responsibilities", body.get("responsibilities") or [])
    _section("Must haves", body.get("must_haves") or [])
    _section("Nice to haves", body.get("nice_to_haves") or [])
    return "\n".join(line for line in lines if line is not None).strip() + "\n"


def jd_export(jd, version=None) -> dict:
    """Structured JSON export of a JD + the rendered text, for the export
    endpoint and any future binary renderer (Module 14)."""
    version = version or _resolve_export_version(jd)
    return {
        "id": str(jd.id),
        "title": jd.title,
        "level": jd.level,
        "department": jd.department,
        "status": jd.status,
        "source": jd.source,
        "version_number": version.version_number if version else None,
        "body": (version.body if version else {}) or {},
        "rendered_text": render_jd_text(jd, version),
    }
