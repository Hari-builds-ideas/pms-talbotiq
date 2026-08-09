"""
seed_scale_tenant — a LARGE synthetic tenant, so "it works" can be proven at real
company size instead of at demo size.

    docker compose exec web python manage.py seed_scale_tenant            # 5,000 people
    docker compose exec web python manage.py seed_scale_tenant --headcount 500
    docker compose exec web python manage.py seed_scale_tenant --reset    # rebuild

This is a TEST FIXTURE. It creates its own tenant (default slug ``scale``) and refuses
to touch ``acme`` or any other existing tenant it didn't create, so it can never
scribble on the demo or on real data. Everything is deterministic and idempotent: the
same headcount always produces the same people with the same emails, and a re-run adds
nothing.

It deliberately seeds the cases that break naive name lookup, because a resolver that
only handles tidy names is not a resolver:

  * **exact duplicate full names** — several people who genuinely share a name, which
    is the ONLY case where asking "which one?" is correct;
  * **one person's first name is another's last name** ("Cameron Reyes" / "Ada Cameron");
  * **accented and non-ASCII names** (José Álvarez, Zoë Ćirić, 山田 太郎);
  * **very long multi-part names**, and names with apostrophes/hyphens;
  * **near-duplicates** a typo could plausibly land between.

Speed matters at this size, so users are written with ``bulk_create`` and share ONE
pre-computed password hash — hashing 5,000 passwords with Argon2 would take minutes and
prove nothing. Every seeded account logs in with the same password (printed at the end).
"""
from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

SCALE_PASSWORD = "Passw0rd!scale"

#: Tenants this command must never write to, whatever is passed on the command line.
PROTECTED_SLUGS = {"acme", "globex", "default", "public"}

#: The CLOSED cycle seeded before the active one, so cycle-over-cycle questions ("who
#: improved most since last cycle?") have two comparable scores per person to work from.
PRIOR_CYCLE_NAME = "Scale Test Cycle (previous)"

FIRST_NAMES = [
    "Aarav", "Mei", "Liam", "Sofia", "Noah", "Aisha", "Ethan", "Priya", "Lucas", "Hana",
    "Mateo", "Yuki", "Omar", "Elena", "Kai", "Zara", "Diego", "Anya", "Ravi", "Clara",
    "Ibrahim", "Nadia", "Leon", "Ingrid", "Tariq", "Lena", "Hugo", "Amara", "Felix", "Rina",
    "Dmitri", "Maya", "Carlos", "Freya", "Jamal", "Saanvi", "Theo", "Lucia", "Arjun", "Nora",
    "Cameron", "Rowan", "Sana", "Bilal", "Elif", "Nikhil", "Marta", "Tobias", "Wren", "Isla",
]
# Large enough that 50 × 110 = 5,500 distinct first+last pairs cover the default
# 5,000 headcount WITHOUT falling back to middle initials. That matters: a fixture
# full of "Sofia Menon" / "Sofia A. Menon" pairs manufactures near-duplicates that
# don't exist in most real companies, and then typo tolerance can't be assessed at
# all — every mistyped name legitimately resolves to the shorter neighbour.
LAST_NAMES = [
    "Sharma", "Chen", "Okafor", "Rossi", "Haddad", "Nguyen", "Andersen", "Garcia", "Kim", "Muller",
    "Patel", "Tanaka", "Silva", "Novak", "Khan", "Lindqvist", "Mbeki", "Costa", "Dubois", "Reyes",
    "Bergstrom", "Aziz", "Schmidt", "Fontaine", "Menon", "Vidal", "O'Brien", "Rao", "Carter", "Yamamoto",
    "Ferrari", "Cohen", "Ivanov", "Santos", "Larsen", "Bauer", "Travers", "Nair", "Walsh", "Petrova",
    "Adeyemi", "Kowalski", "Fernandes", "Haugen", "Batista", "Nakamura", "Oyelaran", "Vasquez",
    "Lindgren", "Achebe", "Bianchi", "Moreau", "Sorensen", "Delacroix", "Aguilar", "Bhatt",
    "Castellanos", "Dvorak", "Eriksen", "Falconer", "Gallagher", "Hoffmann", "Iqbal", "Jankowski",
    "Kovalenko", "Lombardi", "Marchetti", "Nakagawa", "Olsen", "Pereira", "Quintero", "Radcliffe",
    "Sandoval", "Tremblay", "Ueda", "Villanueva", "Whitfield", "Yilmaz", "Zielinski", "Abbott",
    "Bergeron", "Cardoso", "Dalgaard", "Espinoza", "Fitzgerald", "Grimaldi", "Hartmann", "Ismail",
    "Jorgensen", "Kaminski", "Laurent", "Mancini", "Nikolaev", "Ortega", "Pedersen", "Rahman",
    "Steinberg", "Takahashi", "Ulrich", "Voronin", "Wagner", "Xiong", "Yusuf", "Zamora",
    "Ashworth", "Beaumont", "Cavendish", "Donnelly", "Ekstrom", "Freeman", "Guerrero", "Halvorsen",
    "Ingram", "Jimenez",
]

DEPARTMENTS = ["Engineering", "Product", "Data", "Design", "Sales", "Customer Success",
               "Finance", "People", "Legal", "Operations"]

#: Deterministic attainment spread (0..1) so risk bands and pace vary believably.
ATTAINMENT = [
    0.97, 0.61, 0.34, 0.85, 0.48, 0.30, 1.00, 0.74, 0.41, 0.55,
    0.92, 0.36, 0.68, 0.32, 0.88, 0.58, 0.45, 0.78, 0.39, 0.95,
    0.70, 0.50, 0.82, 0.43, 0.66, 0.28, 0.90, 0.52, 0.47, 0.80,
]

#: Names inserted verbatim to exercise the awkward cases. ``dupes`` is how many people
#: get that EXACT name — >1 means a genuine ambiguity the assistant must ask about.
EDGE_NAMES = [
    ("Priya Nair", 3),            # a real triple duplicate — must disambiguate
    ("Cameron Reyes", 2),         # duplicate, and "Cameron" is also a first name below
    ("Ada Cameron", 1),           # first name of one person is the last name of another
    ("José Álvarez", 1),          # accents
    ("Zoë Ćirić", 1),             # diacritics beyond Latin-1
    ("山田 太郎", 1),               # non-Latin script
    ("Ana-Lucía O'Brien-Fitzgerald", 1),   # hyphens + apostrophe + long
    ("Maximilian Alexander Fitzgerald-Montgomery III", 1),  # very long
    ("Jon Smith", 1),             # near-duplicate pair: a typo could land between
    ("Jon Smyth", 1),
    ("Akhil Menon", 1),           # the classic typo target ("Akil Menonn")
]


class Command(BaseCommand):
    help = ("Create a large synthetic tenant (default 5,000 people) for scale testing. "
            "Deterministic, idempotent, and refuses to touch the demo tenants.")

    def add_arguments(self, parser):
        parser.add_argument("--headcount", type=int, default=5000,
                            help="How many people to create (default 5000).")
        parser.add_argument("--tenant", default="scale",
                            help="Tenant slug to create/populate (default 'scale').")
        parser.add_argument("--reset", action="store_true",
                            help="Delete the tenant first and rebuild it from scratch.")
        parser.add_argument("--force", action="store_true",
                            help="Required to run when DEBUG is off. This is a test "
                                 "fixture and must never be seeded into production.")

    def handle(self, *args, **options):
        slug = options["tenant"].strip().lower()
        headcount = max(int(options["headcount"]), 10)

        if slug in PROTECTED_SLUGS:
            raise CommandError(
                f"Refusing to write to '{slug}' — that's a real/demo tenant. "
                "This fixture creates its own (try --tenant scale)."
            )
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "DEBUG is off, so this looks like a real deployment. This command seeds "
                "thousands of fake people and must never run in production. Pass --force "
                "only if you are certain this is a throwaway environment."
            )

        if options["reset"]:
            existing = Tenant.objects.filter(slug=slug).first()
            if existing is not None:
                self.stdout.write(f"--reset: deleting tenant '{slug}' …")
                self._reset(existing)

        tenant, _ = Tenant.objects.get_or_create(
            slug=slug, defaults={"name": f"Scale Test Co ({slug})", "status": "ACTIVE"}
        )
        started = timezone.now()
        with tenant_context(tenant.id):
            people = self._people(tenant, headcount)
            cycle = self._cycle(tenant)
            self._performance_data(tenant, cycle, people)
            self._prior_cycle_scores(tenant, people)

        took = (timezone.now() - started).total_seconds()
        self.stdout.write(self.style.SUCCESS(
            f"seed_scale_tenant complete: '{slug}' has {len(people)} people "
            f"({took:.1f}s). Password for every account: {SCALE_PASSWORD!r}. "
            f"Admin: admin@{slug}.test"
        ))

    def _reset(self, tenant):
        """Empty the fixture tenant so it can be rebuilt — as far as the system's own
        invariants allow, and no further.

        Three things make this less trivial than `tenant.delete()`, and all three are
        the product behaving correctly:

        1. **`audit_log` is append-only at the DATABASE level** — a trigger rejects
           DELETE outright. That is a real guarantee, not an obstacle to route around,
           so audit rows are left strictly alone. (The tenant row therefore also stays:
           audit history is bound to it.)
        2. **Audit PROTECTs its actor**, so the handful of users who appear in audit
           history cannot be deleted either. They are RETIRED instead — deactivated and
           their name/email moved aside — which removes them from the directory
           (resolution only searches active users) and frees their email for reuse.
        3. **Queryset `.delete()` is a SOFT delete** on tenant-scoped models. Soft-
           deleted rows still occupy unique constraints, so a rebuild would collide;
           this uses `hard_delete()` where the manager offers it.

        Every query is filtered to THIS tenant's id, and the slug was already checked
        against PROTECTED_SLUGS, so it cannot reach another tenant's data.
        """
        from django.apps import apps as django_apps
        from django.db.models import ProtectedError

        from apps.audit.models import AuditLog
        from apps.identity.models import User

        def wipe(qs):
            qs.hard_delete() if hasattr(qs, "hard_delete") else qs.delete()

        # Everything except people first — each pass frees references the next can
        # then delete, so the order needn't be hand-maintained as models are added.
        models = [
            m for m in django_apps.get_models()
            if any(f.name == "tenant" for f in m._meta.fields)
            and m not in (AuditLog, Tenant, User)
        ]
        for _ in range(len(models)):
            blocked = []
            for model in models:
                try:
                    wipe(model._base_manager.filter(tenant_id=tenant.id))
                except ProtectedError:
                    blocked.append(model)
            models = blocked
            if not models:
                break

        # Now people. A bulk delete is all-or-nothing, so a handful of audit-referenced
        # actors would otherwise block all 5,000 and leave the whole population to be
        # retired — the table then grows by a full generation on every reset. Exclude
        # the protected few up front so the rest are genuinely deleted.
        audited = set(
            AuditLog._base_manager.filter(tenant_id=tenant.id, actor__isnull=False)
            .values_list("actor_id", flat=True)
        )
        try:
            wipe(User._base_manager.filter(tenant_id=tenant.id).exclude(id__in=audited))
        except ProtectedError as exc:
            self.stdout.write(self.style.WARNING(f"  some users are still referenced: {exc}"))

        survivors = list(User._base_manager.filter(tenant_id=tenant.id))
        if survivors:
            for user in survivors:
                short = str(user.id)[:8]
                user.is_active = False
                user.display_name = f"Retired {short}"
                user.email = f"retired-{short}@{tenant.slug}.invalid"
                user.manager = None
            User._base_manager.bulk_update(
                survivors, ["is_active", "display_name", "email", "manager"], batch_size=500)
            self.stdout.write(
                f"  retired {len(survivors)} user(s) that audit history protects "
                "(append-only audit is working as designed)")
        if models:
            self.stdout.write(self.style.WARNING(
                "  could not clear: " + ", ".join(m.__name__ for m in models)))

    # ── people ──────────────────────────────────────────────────────────────────

    def _display_names(self, headcount: int) -> list[str]:
        """One name per person: the awkward edge cases first (so they exist at every
        headcount), then deterministic combinations.

        Every generated name is UNIQUE, which matters more than it sounds. The pools
        give 50 × 48 = 2,400 pairs, so at 5,000 people a naive first+last scheme makes
        roughly half the company an accidental duplicate — and then "resolve an exact
        full name" is *supposed* to ask, and the harness can no longer tell a real
        resolver bug from a fixture artefact. Collisions therefore take a middle
        initial ("Jamal K. Cohen"), which is both realistic and unambiguous.

        The only duplicates in the tenant are the ones EDGE_NAMES asks for on purpose.
        """
        # Leadership slots (index 0 = admin, then the HRBPs) get ordinary generated
        # names. The edge cases start after them: putting the deliberately-triplicated
        # "Priya Nair" at index 0 made the ADMIN one of three people with that name,
        # which reads as a bug in every harness line that prints the actor.
        leadership = max(headcount // 500, 2) + 1
        names: list[str] = []
        edge: list[str] = []
        for name, copies in EDGE_NAMES:
            edge.extend([name] * copies)
        used = set(edge)

        nf, nl = len(FIRST_NAMES), len(LAST_NAMES)
        i = 0
        while len(names) < headcount:
            # (first, last) must be a BIJECTION over i, not merely "spread out". An
            # earlier version walked the surnames with a stride of 351, which shares a
            # factor of 3 with the 114-name pool — so each pair recurred every 38
            # blocks and 3,087 of 5,000 people ended up needing a middle initial.
            # Fixing the first name by `i % nf` and stepping the surname by the block
            # index is unique by construction for the first nf × nl people, and the
            # `+ i % nf` keeps surnames from clustering inside a block.
            first = FIRST_NAMES[i % nf]
            last = LAST_NAMES[(i // nf + i % nf) % nl]
            candidate = f"{first} {last}"
            # Beyond nf × nl people the pairs run out. The fallback used to be a middle
            # initial ("Aarav A. Sharma"), which is unique but sits a hair away from
            # "Aarav Sharma" — so at 25,000 people almost everyone had a near-twin, and
            # the harness's typo check (which must skip near-twins, since a typo
            # legitimately lands on the closer name) ended up covering NOTHING.
            #
            # A hyphenated second surname is unique AND well separated: a typo of
            # "Aarav Sharma-Chen" still lands clearly on it rather than on "Aarav
            # Sharma". Deliberate near-duplicates stay the job of EDGE_NAMES, where
            # they're visible and intentional.
            extra = 0
            while candidate in used:
                second = LAST_NAMES[(i // nf + i % nf + 1 + extra) % nl]
                candidate = f"{first} {last}-{second}" if second != last else candidate
                extra += 1
                if extra > nl:  # pathological: fall back to a distinguishing initial
                    candidate = f"{first} {chr(65 + extra % 26)}. {last}"
            used.add(candidate)
            names.append(candidate)
            i += 1
            if len(names) == leadership:      # leadership filled — now the edge cases
                names.extend(edge)

        # Fail loudly if the scheme ever regresses: the ONLY duplicates in this tenant
        # must be the ones EDGE_NAMES asks for, or the harness can no longer distinguish
        # a resolver bug from a fixture artefact.
        intended = sum(copies for _, copies in EDGE_NAMES if copies > 1)
        actual = len(names) - len(set(names))
        if actual > intended:
            raise CommandError(
                f"name generation produced {actual} duplicates but only {intended} were "
                f"intended — the first/last pairing is no longer unique."
            )
        return names[:headcount]

    def _people(self, tenant, headcount: int):
        """Build the org: 1 admin → HRBPs → managers → employees, ~10 reports per
        manager. Written with bulk_create and a SHARED password hash — Argon2 on 5,000
        rows would dominate the runtime and prove nothing about the agent."""
        from apps.identity.models import User

        existing = list(User.objects.filter(is_active=True).order_by("email"))
        if len(existing) >= headcount:
            self.stdout.write(f"'{tenant.slug}' already has {len(existing)} people — reusing "
                              "(pass --reset to rebuild).")
            return existing

        names = self._display_names(headcount)
        pw_hash = make_password(SCALE_PASSWORD)  # hashed ONCE, shared by every fixture row
        now = timezone.now()

        n_hrbp = max(headcount // 500, 2)
        n_manager = max(headcount // 10, 3)

        def role_for(idx: int) -> str:
            if idx == 0:
                return "ADMIN"
            if idx <= n_hrbp:
                return "HRBP"
            if idx <= n_hrbp + n_manager:
                return "MANAGER"
            return "EMPLOYEE"

        rows, meta = [], []
        for idx, display in enumerate(names):
            role = role_for(idx)
            uid = uuid.uuid4()
            rows.append(User(
                id=uid, tenant_id=tenant.id, email=f"p{idx}@{tenant.slug}.test" if idx else f"admin@{tenant.slug}.test",
                password=pw_hash, display_name=display, role=role, is_active=True,
                department=DEPARTMENTS[idx % len(DEPARTMENTS)],
                created_at=now, updated_at=now,
            ))
            meta.append((idx, uid, role))

        User.objects.bulk_create(rows, batch_size=1000)

        # Reporting lines, as a second pass: every employee to a manager, every manager
        # to an HRBP, every HRBP to the admin. Done with bulk_update so the whole org
        # costs a handful of statements rather than one per person.
        by_idx = {idx: uid for idx, uid, _ in meta}
        admin_id = by_idx[0]
        hrbp_ids = [by_idx[i] for i in range(1, n_hrbp + 1)]
        manager_ids = [by_idx[i] for i in range(n_hrbp + 1, n_hrbp + n_manager + 1)]

        created = {u.id: u for u in rows}
        for idx, uid, role in meta:
            u = created[uid]
            if role == "ADMIN":
                u.manager_id = None
            elif role == "HRBP":
                u.manager_id = admin_id
            elif role == "MANAGER":
                u.manager_id = hrbp_ids[idx % len(hrbp_ids)]
            else:
                u.manager_id = manager_ids[idx % len(manager_ids)]
        User.objects.bulk_update(rows, ["manager"], batch_size=1000)

        self.stdout.write(f"created {len(rows)} people "
                          f"(1 admin, {n_hrbp} HRBP, {n_manager} managers, "
                          f"{len(rows) - 1 - n_hrbp - n_manager} employees)")
        return rows

    # ── performance data ────────────────────────────────────────────────────────

    def _cycle(self, tenant):
        from apps.cycles.models import PerformanceCycle

        cycle = PerformanceCycle.objects.filter(status="ACTIVE").order_by("-start_date").first()
        if cycle is not None:
            return cycle
        today = timezone.now().date()
        return PerformanceCycle.objects.create(
            tenant_id=tenant.id, name="Scale Test Cycle",
            start_date=today - datetime.timedelta(days=45),
            end_date=today + datetime.timedelta(days=45),
            status="ACTIVE",
        )

    def _performance_data(self, tenant, cycle, people):
        """One active goal + one measured KPI + one cycle score per person, so every
        person is a legitimate subject for "how is X doing?". Attainment walks a fixed
        spread, so risk bands and pace vary and answers differ person to person — a
        tenant where everyone looks identical could not detect a templated answer."""
        from apps.goals.models import CycleScore, Goal, Kpi, KpiMeasurement

        if CycleScore.objects.filter(cycle=cycle).exists():
            self.stdout.write("performance data already present — skipping.")
            return

        now = timezone.now()
        goals, kpis, measurements, scores = [], [], [], []
        for idx, person in enumerate(people):
            frac = ATTAINMENT[idx % len(ATTAINMENT)]
            attained = Decimal(str(round(frac * 100, 2)))

            gid, kid = uuid.uuid4(), uuid.uuid4()
            goals.append(Goal(
                id=gid, tenant_id=tenant.id, employee_id=person.id, cycle_id=cycle.id,
                title=f"{person.department} objective {idx % 7 + 1}",
                weight=Decimal("100.00"), status="ACTIVE", created_by_id=person.id,
                created_at=now, updated_at=now,
            ))
            kpis.append(Kpi(
                id=kid, tenant_id=tenant.id, goal_id=gid, name="Attainment",
                weight=Decimal("100.00"), target_value=Decimal("100"),
                direction="INCREASING", unit="%", source="MANUAL",
                created_at=now, updated_at=now,
            ))
            measurements.append(KpiMeasurement(
                id=uuid.uuid4(), tenant_id=tenant.id, kpi_id=kid, value=attained,
                recorded_at=now, source="MANUAL", created_at=now, updated_at=now,
            ))
            risk = ("ON_TRACK" if frac >= 0.75 else "AT_RISK" if frac >= 0.40 else "CRITICAL")
            scores.append(CycleScore(
                id=uuid.uuid4(), tenant_id=tenant.id, employee_id=person.id, cycle_id=cycle.id,
                raw_score=attained, z_score=Decimal(str(round((frac - 0.6) * 2, 4))),
                t_score=Decimal(str(round(50 + (frac - 0.6) * 20, 4))),
                cohort_size=len(people), risk_status=risk, pace_behind=frac < 0.6,
                computed_at=now, created_at=now, updated_at=now,
            ))

        Goal.objects.bulk_create(goals, batch_size=1000)
        Kpi.objects.bulk_create(kpis, batch_size=1000)
        KpiMeasurement.objects.bulk_create(measurements, batch_size=1000)
        CycleScore.objects.bulk_create(scores, batch_size=1000)
        self.stdout.write(f"created goals/KPIs/scores for {len(people)} people")

    #: How each person's score moved between the previous cycle and the current one, in
    #: T-score points. Walked by index like ATTAINMENT, and deliberately UNCORRELATED
    #: with it: a fixture where the strongest people are always the fastest improvers
    #: makes "who improved most" and "who's top" the same question, and then neither is
    #: really being tested. Sums to a small negative, so a team is not uniformly rising.
    DELTAS = [
        6.4, -2.1, 11.8, 0.0, -5.3, 8.7, -1.2, 3.9, -9.4, 2.6,
        -3.8, 14.2, 1.1, -6.7, 4.5, -0.9, 7.3, -4.4, 9.6, -2.8,
        0.5, -8.1, 5.2, 12.7, -1.6, 3.3, -7.5, 1.9, -3.1, 6.0,
    ]

    def _prior_cycle_scores(self, tenant, people):
        """A CLOSED cycle before the current one, with a score for every person.

        Without this the tenant has exactly one score each, and "who improved most since
        last cycle?" is honestly unanswerable — which is correct behaviour but proves
        nothing about the question class. Cycle-over-cycle deltas are the one thing a
        single-cycle fixture cannot exercise at all.
        """
        from apps.cycles.models import PerformanceCycle
        from apps.goals.models import CycleScore

        prior = PerformanceCycle.objects.filter(name=PRIOR_CYCLE_NAME).first()
        if prior is not None and CycleScore.objects.filter(cycle_id=prior.id).exists():
            self.stdout.write("prior-cycle scores already present — skipping.")
            return
        if prior is None:
            today = timezone.now().date()
            prior = PerformanceCycle.objects.create(
                tenant_id=tenant.id, name=PRIOR_CYCLE_NAME,
                start_date=today - datetime.timedelta(days=225),
                end_date=today - datetime.timedelta(days=135),
                status="CLOSED",
            )

        # Older than every current score, so "newest first" orders the pair correctly
        # whatever order the rows were written in.
        then = timezone.now() - datetime.timedelta(days=150)
        rows = []
        for idx, person in enumerate(people):
            frac = ATTAINMENT[idx % len(ATTAINMENT)]
            now_t = round(50 + (frac - 0.6) * 20, 4)
            was_t = round(now_t - self.DELTAS[idx % len(self.DELTAS)], 4)
            was_frac = (was_t - 50) / 20 + 0.6
            rows.append(CycleScore(
                id=uuid.uuid4(), tenant_id=tenant.id, employee_id=person.id,
                cycle_id=prior.id, raw_score=Decimal(str(round(was_frac * 100, 2))),
                z_score=Decimal(str(round((was_frac - 0.6) * 2, 4))),
                t_score=Decimal(str(was_t)), cohort_size=len(people),
                risk_status=("ON_TRACK" if was_frac >= 0.75 else
                             "AT_RISK" if was_frac >= 0.40 else "CRITICAL"),
                pace_behind=was_frac < 0.6, computed_at=then,
                created_at=then, updated_at=then,
            ))
        CycleScore.objects.bulk_create(rows, batch_size=1000)
        self.stdout.write(f"created prior-cycle scores for {len(people)} people "
                          f"(cycle {PRIOR_CYCLE_NAME!r})")
