"""
Secret resolution for integrations.

Secrets are read from the ENVIRONMENT by name — never stored in the DB and NEVER
logged. ``resolve_secret`` returns ``None`` when the env var is unset, which makes
the integration a clean no-op. Production should swap the env lookup for a real
secrets manager (KMS / Vault) — this single function is the seam (see
``NEEDS_HARI_secrets.md``).
"""
from __future__ import annotations

import os


def secret_env_name(integration) -> str:
    """The env-var NAME holding ``integration``'s token: the explicit ``secret_ref``
    if set, else the convention ``<KIND>_TOKEN_<TENANT_SLUG_UPPER>``."""
    if integration.secret_ref:
        return integration.secret_ref
    slug = getattr(integration.tenant, "slug", str(integration.tenant_id))
    return f"{integration.kind}_TOKEN_{str(slug).upper().replace('-', '_')}"


def resolve_secret(integration) -> str | None:
    """Return the secret token for ``integration`` from the environment, or
    ``None`` when unset. NEVER log the return value."""
    return os.environ.get(secret_env_name(integration)) or None
