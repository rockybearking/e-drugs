"""
================================================================================
[파일명] Backend/config/urls.py
[역할] 프로젝트 최상위 루트 URL 라우터 (Root URL Dispatcher / 안내 데스크)
================================================================================

[백엔드 아키텍처 호출 흐름 (출발지 ➔ 현재 파일 ➔ 목적지)]
1. 출발지 (From):
   - 브라우저(또는 `Frontend/app.js`)가 `http://127.0.0.1:8000/...`로 HTTP 요청을 보냄
   - `Backend/config/settings.py`의 `ROOT_URLCONF = "config.urls"` 설정이 이 파일을 가리킴
2. 현재 파일 (config/urls.py)이 가리키는 목적지 파일들 (To):
   - `"admin/"` 요청 ➔ Django 내장 관리자 사이트 및 `Backend/drugs/admin.py`에 등록된 모델 관리 화면으로 연결
   - `"style.css"` 요청 ➔ `Backend/drugs/views.py`의 `serve_frontend_asset(request, filename="style.css")`로 연결
     (최종적으로 `Frontend/style.css` 파일을 반환)
   - `"app.js"` 요청 ➔ `Backend/drugs/views.py`의 `serve_frontend_asset(request, filename="app.js")`로 연결
     (최종적으로 `Frontend/app.js` 파일을 반환)
   - `"favicon.ico"` 요청 ➔ `Backend/drugs/views.py`의 `serve_favicon(request)`로 연결
     (브라우저의 자동 파비콘 요청 시 `Not Found: /favicon.ico` 404 로그가 뜨지 않도록 SVG 아이콘 반환)
   - `""` (그 외 모든 경로) ➔ `Backend/drugs/urls.py` 파일로 처리를 위임(`include("drugs.urls")`)

[현재 구현된 서비스]
- Django 관리자 페이지(`/admin/`) 라우팅
- 프론트엔드 정적 자산(`/style.css`, `/app.js`) 및 파비콘(`/favicon.ico`) 루트 매핑
- 의약품 도메인 앱(`Backend/drugs/urls.py`)으로 메인 페이지(`/`) 및 REST API(`/api/...`) 라우팅 위임

[향후 확장(구현) 가능한 서비스 가이드]
- 만약 새로운 앱(예: `users` 회원 앱)을 추가했다면:
  `path("api/users/", include("users.urls")),` 한 줄을 `urlpatterns`에 추가하면
  `/api/users/login/` 같은 모든 회원 관련 URL을 `Backend/users/urls.py`로 분기시킬 수 있습니다.
================================================================================
"""
from __future__ import annotations

from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path

from drugs.views import serve_favicon, serve_frontend_asset

# [수정 가이드]
# - 예1) 관리자 페이지 주소를 보안상 `/admin/` 대신 `/secret-admin/`으로 바꾸고 싶다면:
#   `path("secret-admin/", admin.site.urls)`로 변경하세요.
# - 예2) `Frontend` 폴더에 새로운 스크립트 파일(예: `chart.js`)을 추가하고 루트에서 불러오고 싶다면:
#   `path("chart.js", serve_frontend_asset, {"filename": "chart.js"}),`를 추가하고
#   `Backend/drugs/views.py`의 `ALLOWED_FRONTEND_ASSETS` 화이트리스트에도 `"chart.js"`를 등록하세요.
urlpatterns: list[URLPattern | URLResolver] = [
    # [목적지] Backend/drugs/admin.py 에 등록된 관리자 페이지
    path("admin/", admin.site.urls),
    # [목적지] Backend/drugs/views.py -> serve_frontend_asset() -> Frontend/style.css
    path("style.css", serve_frontend_asset, {"filename": "style.css"}, name="frontend_css"),
    # [목적지] Backend/drugs/views.py -> serve_frontend_asset() -> Frontend/app.js
    path("app.js", serve_frontend_asset, {"filename": "app.js"}, name="frontend_js"),
    # [목적지] Backend/drugs/views.py -> serve_favicon() (404 Not Found 방지용 인라인 아이콘 응답)
    path("favicon.ico", serve_favicon, name="favicon"),
    # [목적지] Backend/drugs/urls.py 의 urlpatterns 목록으로 위임
    path("", include("drugs.urls")),
]
