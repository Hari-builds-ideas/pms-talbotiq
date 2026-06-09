from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

app_name = "identity"

urlpatterns = [
    path("login", views.LoginView.as_view(), name="login"),
    path("token/refresh", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout", views.LogoutView.as_view(), name="logout"),
    path("mfa/enroll", views.MfaEnrollView.as_view(), name="mfa-enroll"),
    path("mfa/enroll/confirm", views.MfaEnrollConfirmView.as_view(), name="mfa-enroll-confirm"),
    path("mfa/challenge", views.MfaChallengeView.as_view(), name="mfa-challenge"),
    path("me", views.MeView.as_view(), name="me"),
    path("oidc/complete", views.OidcCompleteView.as_view(), name="oidc-complete"),
]
