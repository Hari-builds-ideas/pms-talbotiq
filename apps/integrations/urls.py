"""
Integration-config routes, mounted under ``/api/integrations/`` by the root
urlconf. Admin-only (see ``views.py``). The literal collection route is declared
before the ``<kind>`` detail route; ``kind`` is JIRA|SLACK (case-insensitive,
upper-cased in the view).
"""
from django.urls import path

from .views import IntegrationDetailView, IntegrationListView

app_name = "integrations"

urlpatterns = [
    path("", IntegrationListView.as_view(), name="list"),
    path("<str:kind>", IntegrationDetailView.as_view(), name="detail"),
]
