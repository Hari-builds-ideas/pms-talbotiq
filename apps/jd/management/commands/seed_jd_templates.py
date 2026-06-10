"""
Seed the deterministic JD-template catalogue for one tenant.

Runs outside any request, so it resolves the Tenant by slug and delegates to
:func:`apps.jd.services.seed_templates_for_tenant`, which binds the tenant
context itself and creates rows idempotently.

    python manage.py seed_jd_templates --tenant-slug acme
"""
from django.core.management.base import BaseCommand, CommandError

from apps.jd.services import seed_templates_for_tenant
from apps.tenancy.models import Tenant


class Command(BaseCommand):
    help = "Seed the default JD templates for a tenant (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-slug",
            required=True,
            help="Slug of the tenant to seed JD templates for.",
        )

    def handle(self, *args, **options):
        slug = options["tenant_slug"]
        try:
            tenant = Tenant.objects.get(slug=slug)
        except Tenant.DoesNotExist:
            raise CommandError(f"No tenant found with slug '{slug}'.")

        created = seed_templates_for_tenant(tenant)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded JD templates for '{tenant.slug}': {created} created "
                f"(existing templates skipped)."
            )
        )
