"""
[역할] 최상위 URL 라우터 (관리자 페이지, 프론트엔드 정적 자산, 의약품 앱 URL 분기)
[경로] 브라우저 HTTP 요청 -> Backend/config/urls.py -> Backend/drugs/views.py 또는 Backend/drugs/urls.py
[수정] Frontend에 새 정적 파일(예: chart.js)을 추가하면 이곳과 views.py의 ALLOWED_FRONTEND_ASSETS에 함께 등록하세요.
"""
from __future__ import annotations

from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path

from drugs.views import serve_favicon, serve_frontend_asset

urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
    path("style.css", serve_frontend_asset, {"filename": "style.css"}, name="frontend_css"),
    path("app.js", serve_frontend_asset, {"filename": "app.js"}, name="frontend_js"),
    path("favicon.ico", serve_favicon, name="favicon"),
    path("", include("drugs.urls")),
]
