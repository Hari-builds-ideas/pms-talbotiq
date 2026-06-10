"""
JD Library routes, mounted under ``/api/jd/`` by the root urlconf.

Paths are declared WITHOUT a leading slash because they are appended to the
``api/jd/`` mount point. The literal prefixes (``templates``, ``requests`` and
their actions) are declared BEFORE the bare ``<uuid:pk>`` detail / action routes
so they match first. RBAC gating lives on the views; state legality / HITL rules
live in the lifecycle; the §2 visibility rule lives in the services.
"""
from django.urls import path

from .views import (
    JDApproveView,
    JDArchiveView,
    JDDetailView,
    JDExportView,
    JDGenerateView,
    JDListCreateView,
    JDReviseView,
    JDRequestDeclineView,
    JDRequestFulfilView,
    JDRequestListCreateView,
    JDSaveDraftView,
    JDSubmitView,
    JDTemplateInstantiateView,
    JDTemplateListView,
    JDVersionListView,
)

app_name = "jd"

urlpatterns = [
    path("", JDListCreateView.as_view(), name="list-create"),
    # Literal prefixes — before the bare <uuid:pk> routes.
    path("templates", JDTemplateListView.as_view(), name="template-list"),
    path(
        "templates/<uuid:pk>/instantiate",
        JDTemplateInstantiateView.as_view(),
        name="template-instantiate",
    ),
    path("requests", JDRequestListCreateView.as_view(), name="request-list-create"),
    path(
        "requests/<uuid:pk>/fulfil",
        JDRequestFulfilView.as_view(),
        name="request-fulfil",
    ),
    path(
        "requests/<uuid:pk>/decline",
        JDRequestDeclineView.as_view(),
        name="request-decline",
    ),
    # JD detail + sub-resources.
    path("<uuid:pk>", JDDetailView.as_view(), name="detail"),
    path("<uuid:pk>/versions", JDVersionListView.as_view(), name="versions"),
    path("<uuid:pk>/export", JDExportView.as_view(), name="export"),
    # Lifecycle transitions.
    path("<uuid:pk>/save-draft", JDSaveDraftView.as_view(), name="save-draft"),
    path("<uuid:pk>/submit", JDSubmitView.as_view(), name="submit"),
    path("<uuid:pk>/approve", JDApproveView.as_view(), name="approve"),
    path("<uuid:pk>/revise", JDReviseView.as_view(), name="revise"),
    path("<uuid:pk>/archive", JDArchiveView.as_view(), name="archive"),
    path("<uuid:pk>/generate", JDGenerateView.as_view(), name="generate"),
]
