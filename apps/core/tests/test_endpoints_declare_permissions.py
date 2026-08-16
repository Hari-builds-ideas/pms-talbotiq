"""
Every authenticated endpoint states its own permission stack (C13).

Three views relied on the project-wide ``DEFAULT_PERMISSION_CLASSES`` rather than
declaring anything. Their behaviour was correct — each scopes its queryset to the
caller — but an auditor reading the view could not tell "deliberately open to any
authenticated caller" apart from "somebody forgot", and a change to the project
default would have moved them silently.

Rather than assert the three by name, this walks the whole URLconf. A new view
that forgets its permissions is the thing worth catching, and naming three views
would not catch the fourth.
"""
import pytest
from django.urls import get_resolver
from rest_framework.views import APIView

#: Views that are PUBLIC by necessity — pre-login surfaces, provider callbacks and
#: the ops probes. Each already declares `permission_classes = [AllowAny]`, so
#: they are not exempt from declaring; they are exempt from requiring auth.
_PUBLIC_BY_DESIGN = {
    "LoginView", "SignupView", "PublicConfigView", "MfaChallengeView",
    "PasswordResetRequestView", "PasswordResetConfirmView", "OidcCompleteView",
    "InvitationDetailView", "InvitationAcceptView",
    "SamlMetadataView", "SamlLoginView", "SamlAcsView",
    "StripeWebhookView", "RazorpayWebhookView", "_WebhookView",
    "DeviceAwareTokenRefreshView", "TokenRefreshView",
}


def _drf_views():
    """Every DRF view class reachable from the root URLconf."""
    seen = {}

    def walk(patterns, prefix=""):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                walk(p.url_patterns, prefix + str(p.pattern))
                continue
            cb = getattr(p, "callback", None)
            cls = getattr(cb, "cls", None) or getattr(cb, "view_class", None)
            if cls is not None and issubclass(cls, APIView):
                seen.setdefault(cls.__name__, (cls, prefix + str(p.pattern)))

    walk(get_resolver().url_patterns)
    return seen


def test_every_api_view_declares_its_permission_stack():
    """A view must SAY what it gates, in its own body — either an explicit
    ``permission_classes`` or an RBAC ``required_capability`` / ``_caps`` map."""
    missing = []
    for name, (cls, route) in sorted(_drf_views().items()):
        if name in _PUBLIC_BY_DESIGN:
            continue
        declares = (
            "permission_classes" in cls.__dict__
            or "required_capability" in cls.__dict__
            or "_caps" in cls.__dict__
            or "get_permissions" in cls.__dict__
            # RBACMixin subclasses inherit enforcement and declare the capability
            # somewhere in their own MRO below APIView.
            or any(
                "required_capability" in base.__dict__ or "_caps" in base.__dict__
                for base in cls.__mro__[1:]
                if base is not APIView
            )
        )
        if not declares:
            missing.append(f"{name} ({route})")

    assert not missing, (
        "These views inherit DEFAULT_PERMISSION_CLASSES without saying so, so a "
        "reader cannot tell deliberate from forgotten and a change to the project "
        "default would move them silently:\n  " + "\n  ".join(missing)
    )


@pytest.mark.parametrize(
    "name",
    ["AIJobDetailView", "AIJobListView", "MyFeaturesView"],
)
def test_the_three_previously_implicit_views_now_declare(name):
    """Named explicitly as a regression guard: these are the three the audit
    found relying on the project default."""
    from rest_framework.permissions import IsAuthenticated

    cls, _route = _drf_views()[name]
    assert "permission_classes" in cls.__dict__, f"{name} lost its declaration"
    assert IsAuthenticated in cls.permission_classes
