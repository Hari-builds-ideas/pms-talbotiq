from django.urls import path

from . import views
from .saml import views as saml_views

app_name = "identity"

urlpatterns = [
    path("login", views.LoginView.as_view(), name="login"),
    # Device-aware refresh (L1.3): stock rotation+blacklist PLUS the did claim
    # is re-checked so a revoked device session cannot rotate.
    path("token/refresh", views.DeviceAwareTokenRefreshView.as_view(), name="token-refresh"),
    path("logout", views.LogoutView.as_view(), name="logout"),
    # ─── device sessions + login history (self-only) ───
    path("sessions", views.SessionListView.as_view(), name="sessions"),
    path("sessions/revoke-others", views.SessionRevokeOthersView.as_view(), name="sessions-revoke-others"),
    path("sessions/<uuid:pk>/revoke", views.SessionRevokeView.as_view(), name="session-revoke"),
    path("login-history", views.LoginHistoryView.as_view(), name="login-history"),
    # ─── self-service password reset (no enumeration; emailed single-use link) ───
    path("password-reset", views.PasswordResetRequestView.as_view(), name="password-reset"),
    path(
        "password-reset/confirm",
        views.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("mfa/enroll", views.MfaEnrollView.as_view(), name="mfa-enroll"),
    path("mfa/enroll/confirm", views.MfaEnrollConfirmView.as_view(), name="mfa-enroll-confirm"),
    path("mfa/challenge", views.MfaChallengeView.as_view(), name="mfa-challenge"),
    path("me", views.MeView.as_view(), name="me"),
    path("oidc/complete", views.OidcCompleteView.as_view(), name="oidc-complete"),
    # ─── SAML 2.0 SP (per tenant by slug) ───
    path("saml/<slug:tenant_slug>/metadata", saml_views.SamlMetadataView.as_view(), name="saml-metadata"),
    path("saml/<slug:tenant_slug>/login", saml_views.SamlLoginView.as_view(), name="saml-login"),
    path("saml/<slug:tenant_slug>/acs", saml_views.SamlAcsView.as_view(), name="saml-acs"),
]
