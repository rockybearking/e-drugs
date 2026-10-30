from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/status/", views.api_status, name="api_status"),
    path("api/unified-search/", views.api_unified_search, name="api_unified_search"),
    path("api/grain-search/", views.api_grain_search, name="api_grain_search"),
    path("api/permission-search/", views.api_permission_search, name="api_permission_search"),
    path("api/drug-detail/", views.api_drug_detail, name="api_drug_detail"),
    path("api/pillbox/", views.api_pillbox, name="api_pillbox"),
]
