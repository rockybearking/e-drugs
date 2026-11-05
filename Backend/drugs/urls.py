"""
================================================================================
[파일명] Backend/drugs/urls.py
[역할] `drugs` 앱 내부의 세부 URL 주소를 각각의 뷰 함수(`Backend/drugs/views.py`)로 연결하는 라우팅 테이블
================================================================================

[백엔드 아키텍처 호출 흐름 (출발지 ➔ 현재 파일 ➔ 목적지)]
1. 출발지 (From):
   - 프론트엔드 `Frontend/app.js`에서 `fetch("/api/...")` 호출 또는 브라우저에서 `/` 접속
   - `Backend/config/urls.py`의 `path("", include("drugs.urls"))`가 이 파일로 요청을 전달함
2. 현재 파일 (drugs/urls.py)이 가리키는 목적지 (To):
   - 모든 URL 경로는 `Backend/drugs/views.py` 안에 정의된 함수(`views.xxx`)를 정확히 1:1로 가리킵니다:
     * `""`                      ➔ `views.index` (`Frontend/index.html` 메인 화면 렌더링)
     * `"api/status/"`           ➔ `views.api_status` (프론트엔드 `app.js`의 `checkBackendStatus()`가 호출)
     * `"api/unified-search/"`   ➔ `views.api_unified_search` (프론트엔드 `app.js`의 `runUnifiedSearch()`가 호출)
     * `"api/grain-search/"`     ➔ `views.api_grain_search` (낱알 외형 전용 검색 엔드포인트)
     * `"api/permission-search/"`➔ `views.api_permission_search` (프론트엔드 `app.js`의 `runPermissionSearch()`가 호출)
     * `"api/drug-detail/"`      ➔ `views.api_drug_detail` (프론트엔드 `app.js`의 `openDetailModal()`이 호출)
     * `"api/pillbox/"`          ➔ `views.api_pillbox` (프론트엔드 `app.js`의 `loadPillbox()`, `addToPillbox()`, `removeFromPillbox()`가 호출)

[현재 구현된 서비스]
- 메인 반응형 웹 페이지(`/`) 라우팅 1개 및 JSON REST API 엔드포인트 6개 매핑

[향후 확장(구현) 가능한 서비스 가이드 및 수정 예제]
- 예) 약국 위치 찾기 API(`/api/pharmacies/`)를 새로 만들고 싶다면:
  1) `Backend/drugs/views.py`에 `def api_pharmacies(request: HttpRequest) -> JsonResponse:` 함수를 작성합니다.
  2) 이 파일(`Backend/drugs/urls.py`)의 `urlpatterns` 리스트에
     `path("api/pharmacies/", views.api_pharmacies, name="api_pharmacies"),`를 추가합니다.
  3) 프론트엔드(`Frontend/app.js`)에서 `fetch("/api/pharmacies/")`를 호출하면 즉시 연결됩니다!
================================================================================
"""
from __future__ import annotations

from django.urls import URLPattern, path

from . import views

urlpatterns: list[URLPattern] = [
    # [출발지] 브라우저 GET "/" ➔ [목적지] Backend/drugs/views.py :: index() ➔ Frontend/index.html
    path("", views.index, name="index"),
    # [출발지] Frontend/app.js :: checkBackendStatus() ➔ [목적지] Backend/drugs/views.py :: api_status()
    path("api/status/", views.api_status, name="api_status"),
    # [출발지] Frontend/app.js :: runUnifiedSearch() ➔ [목적지] Backend/drugs/views.py :: api_unified_search()
    path("api/unified-search/", views.api_unified_search, name="api_unified_search"),
    # [출발지] 외형 단독 검색 요청 ➔ [목적지] Backend/drugs/views.py :: api_grain_search()
    path("api/grain-search/", views.api_grain_search, name="api_grain_search"),
    # [출발지] Frontend/app.js :: runPermissionSearch() ➔ [목적지] Backend/drugs/views.py :: api_permission_search()
    path("api/permission-search/", views.api_permission_search, name="api_permission_search"),
    # [출발지] Frontend/app.js :: openDetailModal() ➔ [목적지] Backend/drugs/views.py :: api_drug_detail()
    path("api/drug-detail/", views.api_drug_detail, name="api_drug_detail"),
    # [출발지] Frontend/app.js :: loadPillbox/addToPillbox/removeFromPillbox ➔ [목적지] Backend/drugs/views.py :: api_pillbox()
    path("api/pillbox/", views.api_pillbox, name="api_pillbox"),
]
