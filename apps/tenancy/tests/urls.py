from django.urls import path

from .views import WhoTenantView

urlpatterns = [
    path("whoami-tenant", WhoTenantView.as_view(), name="whoami-tenant"),
]
