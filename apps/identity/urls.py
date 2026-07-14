from django.urls import path

from . import invite_views, profile_views, signup_views, views
from .saml import views as saml_views

app_name = "identity"

urlpatterns = [
    # ─── self-serve new-organization signup (PUBLIC; PROD_B) ───
    path("signup", signup_views.SignupView.as_view(), name="signup"),
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
    # ─── self-service profile & account security (PHASE2 L1.1) ───
    path("profile", profile_views.ProfileView.as_view(), name="profile"),
    path("profile/photo", profile_views.ProfilePhotoView.as_view(), name="profile-photo"),
    path("users/<uuid:pk>/photo", profile_views.UserPhotoView.as_view(), name="user-photo"),
    path("password-change", profile_views.PasswordChangeView.as_view(), name="password-change"),
    path("email-change", profile_views.EmailChangeRequestView.as_view(), name="email-change"),
    path(
        "email-change/confirm",
        profile_views.EmailChangeConfirmView.as_view(),
        name="email-change-confirm",
    ),
    path("mfa/disable", profile_views.MfaDisableView.as_view(), name="mfa-disable"),
    path("my-activity", profile_views.MyActivityView.as_view(), name="my-activity"),
    # ─── invitation onboarding — PUBLIC accept surface (PHASE2 L1.2) ───
    path(
        "invitations/<str:token>/accept",
        invite_views.InvitationAcceptView.as_view(),
        name="invitation-accept",
    ),
    path(
        "invitations/<str:token>",
        invite_views.InvitationDetailView.as_view(),
        name="invitation-detail",
    ),
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
