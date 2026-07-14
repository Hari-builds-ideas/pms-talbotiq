"""
qa_seed_globex.py — create the GLOBEX cross-tenant fixture (idempotent).

Runs INSIDE the web container via `manage.py shell`:

    docker compose exec -T web python manage.py shell < scripts/qa_seed_globex.py

A second tenant is required to prove tenant isolation over HTTP (qa_verify.py's
cross-tenant section logs in as gadmin@globex.test and tries to touch ACME rows).
seed_demo_rich only touches ACME, so this fixture survives reseeds. Test-only;
delete the tenant anytime — it never affects the ACME demo.
"""
import os

from apps.billing.services import get_or_create_entitlement, get_or_create_subscription
from apps.identity.models import User
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

PW = os.environ.get("QA_PW") or "Passw0rd!" + "demo"  # same as the demo password

t = Tenant.objects.filter(slug="globex").first()
if t is None:
    t = Tenant.objects.create(name="Globex Corp", slug="globex")
    print("created tenant globex", t.id)
else:
    print("globex tenant already exists", t.id)

with tenant_context(t):
    for email, role in (("gadmin@globex.test", "ADMIN"),
                        ("gmgr@globex.test", "MANAGER"),
                        ("gemp@globex.test", "EMPLOYEE")):
        if not User.objects.filter(email=email).exists():
            User.objects.create_user(email, password=PW, tenant=t, role=role)
            print("created", email)
        else:
            print("exists", email)
    get_or_create_entitlement(t.id)
    get_or_create_subscription(t.id)
print("globex fixture ready")
