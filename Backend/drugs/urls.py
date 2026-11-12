"""
[역할] 의약품 도메인 웹 화면(/) 및 REST API(/api/...) 세부 라우팅 테이블
[경로] Frontend/app.js fetch() -> Backend/config/urls.py -> Backend/drugs/urls.py -> Backend/drugs/views.py
[수정] 신규 API 추가 시 views.py에 함수를 작성한 뒤 아래 urlpatterns 리스트에 path()를 등록하세요.
"""
from __future__ import annotations

from django.urls import URLPattern, path

from . import views

urlpatterns: list[URLPattern] = [
    path("", views.index, name="index"),
    path("api/status/", views.api_status, name="api_status"),
    path("api/unified-search/", views.api_unified_search, name="api_unified_search"),
    path("api/permission-search/", views.api_permission_search, name="api_permission_search"),
    path("api/drug-detail/", views.api_drug_detail, name="api_drug_detail"),
    path("api/pillbox/", views.api_pillbox, name="api_pillbox"),
]
