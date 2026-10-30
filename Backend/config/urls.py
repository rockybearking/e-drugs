"""URL configuration for e-Drug Care (알약이가) project."""
from django.contrib import admin
from django.urls import include, path
from drugs.views import serve_frontend_asset

urlpatterns = [
    path("admin/", admin.site.urls),
    path("style.css", serve_frontend_asset, {"filename": "style.css"}),
    path("app.js", serve_frontend_asset, {"filename": "app.js"}),
    path("", include("drugs.urls")),
]
