"""
================================================================================
[파일명] Backend/drugs/views.py
[역할] 프론트엔드(`Frontend/app.js`)의 HTTP 요청을 받아 비즈니스 로직(`services.py`)과
      데이터베이스(`models.py`)를 연결하고 HTML 또는 JSON 응답을 반환하는 컨트롤러(Controller) 모듈
================================================================================

[백엔드 아키텍처 호출 흐름 (출발지 ➔ 현재 파일 ➔ 목적지)]
1. 출발지 (From - 어디서 이 파일의 함수들을 부르는가):
   - `Backend/config/urls.py`:
     * `/style.css`, `/app.js` 요청 ➔ `serve_frontend_asset()` 호출
     * `/favicon.ico` 요청 ➔ `serve_favicon()` 호출
   - `Backend/drugs/urls.py` (프론트엔드 `Frontend/app.js`의 `fetch()`가 호출):
     * `GET /`                      ➔ `index()`
     * `GET /api/status/`           ➔ `api_status()` (호출자: `app.js`의 `checkBackendStatus()`)
     * `GET /api/unified-search/`   ➔ `api_unified_search()` (호출자: `app.js`의 `runUnifiedSearch()`)
     * `GET /api/grain-search/`     ➔ `api_grain_search()` (낱알 외형 식별 전용 API)
     * `GET /api/permission-search/`➔ `api_permission_search()` (호출자: `app.js`의 `runPermissionSearch()`)
     * `GET /api/drug-detail/`      ➔ `api_drug_detail()` (호출자: `app.js`의 `openDetailModal()`)
     * `GET|POST|DELETE /api/pillbox/` ➔ `api_pillbox()` (호출자: `app.js`의 `loadPillbox()`, `addToPillbox()`, `removeFromPillbox()`)

2. 목적지 (To - 이 파일의 함수들이 어디를 가리키는가):
   - [목적지 1] `Frontend/index.html`, `Frontend/style.css`, `Frontend/app.js` (화면 및 정적 리소스 파일)
   - [목적지 2] `Backend/drugs/services.py` (식약처 3대 OpenAPI 병렬 호출·파싱·정규화·캐싱 엔진)
   - [목적지 3] `Backend/drugs/models.py` (`PillCache`, `SavedDrug`, `SearchLog` ➔ `Backend/db.sqlite3`)

[현재 구현된 서비스]
- 메인 반응형 웹 앱(`Frontend/index.html`) 및 정적 파일(`style.css`, `app.js`, `favicon.ico`) 보안 서빙
- 화이트리스트 + `Path.is_relative_to()` 이중 검증을 통한 경로 조작(Path Traversal) 원천 차단
- 통합 의약품 검색(키워드 + 다중 낱알 외형 조건 결합), 제품 허가정보 전문 조회, 실시간 3대 API 상세 교차 조회
- '내 약통' CRUD(조회·등록·수정·삭제) 및 주성분 중복 복용 위험 자동 분석 리포트(`_build_safety_report`)
- 입력값 길이 제한, URL 스킴(`http`/`https`) 검증, JSON 객체 타입 검증 등 시큐어 코딩 적용

[향후 확장(구현) 가능한 서비스 가이드]
- **페이지네이션 서버 사이드 확장**: 현재 프론트엔드에서 페이지당 12개씩 슬라이싱하며, 서버단에서
  대량 데이터를 나눌 때 `django.core.paginator.Paginator`를 연동할 수 있습니다.
- **내 약통 PDF/엑셀 내보내기 뷰**: 복용 중인 약 목록과 중복 성분 리포트를 병원 진료 시 제출할 수 있도록
  다운로드 뷰를 추가할 수 있습니다.
================================================================================
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from django.conf import settings
from django.db.models import F, QuerySet
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .models import PillCache, SavedDrug, SearchLog
from .services import (
    clean_ingredient_text,
    enrich_single_drug_detail,
    fetch_prmsn_list,
    parse_filter_values,
    search_pills_by_appearance,
    seed_initial_pill_cache,
    unified_drug_search,
)

# 루트 경로에서 서빙을 허용할 Frontend 정적 파일 화이트리스트 (경로 조작 취약점 원천 차단)
ALLOWED_FRONTEND_ASSETS: Final[dict[str, str]] = {
    "style.css": "text/css; charset=utf-8",
    "app.js": "application/javascript; charset=utf-8",
}

# 검색 필드 화이트리스트 (비정상 필드명 주입 방지)
_ALLOWED_UNIFIED_FIELDS: Final[frozenset[str]] = frozenset({"itemName", "efcy", "entp"})
_ALLOWED_PRMSN_FIELDS: Final[frozenset[str]] = frozenset({"item_name", "entp"})

# JSON POST 요청 최대 허용 크기 (64KB)
_MAX_JSON_BODY_BYTES: Final[int] = 65_536

# 브라우저가 /favicon.ico 를 자동 요청할 때 404 에러 대신 반환할 경량 SVG 아이콘
_FAVICON_SVG: Final[str] = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="16" fill="#eff6ff"/>'
    '<g transform="rotate(-35 32 32)">'
    '<rect x="18" y="10" width="28" height="44" rx="14" fill="#ffffff" stroke="#2563eb" stroke-width="4"/>'
    '<path d="M18 32 H46 V40 A14 14 0 0 1 32 54 A14 14 0 0 1 18 40 Z" fill="#2563eb"/>'
    "</g></svg>"
)


def _parse_positive_int(raw_val: str | None, default: int = 1, max_val: int = 100) -> int:
    """
    [역할] URL 쿼리 파라미터 문자열(예: `?page=2&rows=60`)을 안전한 양의 정수(`1 ~ max_val`)로 변환합니다.
    [연결 출발지] `api_unified_search()`, `api_permission_search()`에서 호출됩니다.
    [수정 가이드] 한 번에 최대 200건까지 조회를 허용하고 싶다면 호출부의 `max_val=200`으로 변경하세요.
    """
    if not raw_val:
        return default
    try:
        parsed = int(raw_val)
    except (ValueError, TypeError):
        return default
    return max(1, min(parsed, max_val))


def _clean_str(raw_val: Any, max_len: int = 255) -> str:
    """
    [역할] 입력값을 문자열로 변환 후 앞뒤 공백을 제거하고 최대 길이(`max_len`)로 안전하게 자릅니다.
    """
    if raw_val is None:
        return ""
    return str(raw_val).strip()[:max_len]


def _sanitize_http_url(raw_url: Any, max_len: int = 500) -> str:
    """
    [역할]
    - 이미지 URL 등에 `javascript:alert(1)` 또는 `data:` 같은 악성 스크립트 스킴이 주입되는 것을
      차단하고 오직 `http://` 또는 `https://` 주소만 허용하는 보안 함수입니다.
    [연결 출발지] `api_pillbox()`에서 의약품 이미지를 DB에 저장하기 직전에 호출됩니다.
    """
    candidate = _clean_str(raw_url, max_len=max_len)
    if not candidate:
        return ""
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return ""
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return ""
    return candidate


@require_GET
def index(request: HttpRequest) -> HttpResponse:
    """
    [역할] 메인 반응형 웹 애플리케이션(`Frontend/index.html`)을 렌더링하여 브라우저에 반환합니다.
    [연결 출발지] `Backend/drugs/urls.py`의 `path("", views.index, name="index")`
    [연결 목적지] `Backend/config/settings.py`의 `TEMPLATES["DIRS"]` 설정을 따라 `Frontend/index.html`을 가리킵니다.
    """
    return render(request, "index.html")


@require_GET
def serve_favicon(request: HttpRequest) -> HttpResponse:
    """
    [역할]
    - 웹 브라우저가 페이지 접속 시 자동으로 요청하는 `/favicon.ico`에 대해
      `Not Found: /favicon.ico (404)` 경고 로그가 발생하지 않도록 알약 모양 SVG 아이콘을 반환합니다.
    [연결 출발지] `Backend/config/urls.py`의 `path("favicon.ico", serve_favicon)`
    """
    response = HttpResponse(_FAVICON_SVG, content_type="image/svg+xml; charset=utf-8")
    response["Cache-Control"] = "public, max-age=86400"
    return response


@require_GET
def serve_frontend_asset(request: HttpRequest, filename: str) -> FileResponse:
    """
    [역할]
    - `Frontend` 디렉터리의 `style.css`와 `app.js`를 스트리밍 `FileResponse`로 고속 서빙합니다.
    - 화이트리스트(`ALLOWED_FRONTEND_ASSETS`) 검증과 Python 3.9+ 표준 `Path.is_relative_to()` 검증을
      동시에 수행하여 상위 폴더 접근(`../`) 같은 경로 조작 공격을 완벽히 차단합니다.
    [연결 출발지] `Backend/config/urls.py`의 `/style.css`, `/app.js` 경로
    [연결 목적지] `Frontend/style.css`, `Frontend/app.js` 실제 파일
    """
    content_type = ALLOWED_FRONTEND_ASSETS.get(filename)
    if not content_type:
        raise Http404("허용되지 않은 정적 리소스입니다.")

    frontend_root = Path(settings.FRONTEND_DIR).resolve()
    file_path = (frontend_root / filename).resolve()
    if not file_path.is_relative_to(frontend_root) or not file_path.is_file():
        raise Http404(f"{filename} 파일을 찾을 수 없습니다.")

    return FileResponse(file_path.open("rb"), content_type=content_type)


def _record_search_log(keyword: str, search_type: str = "unified") -> None:
    """
    [역할]
    - 사용자가 검색한 키워드 통계를 `SearchLog` 테이블에 원자적(`F("count") + 1`)으로 누적 기록합니다.
    - `F()` 표현식을 사용하면 여러 사용자가 동시에 같은 단어를 검색해도DB 수준에서 안전하게 숫자가 올라갑니다.
    [연결 출발지] `api_unified_search()`, `api_grain_search()`, `api_permission_search()`
    [연결 목적지] `Backend/drugs/models.py`의 `SearchLog` 모델 (`Backend/db.sqlite3`)
    """
    kw = _clean_str(keyword, max_len=50)
    if not kw:
        return
    obj, created = SearchLog.objects.get_or_create(
        keyword=kw,
        defaults={"search_type": search_type, "count": 1},
    )
    if not created:
        SearchLog.objects.filter(pk=obj.pk).update(count=F("count") + 1, search_type=search_type)


@require_GET
def api_status(request: HttpRequest) -> JsonResponse:
    """
    [역할]
    - Django 백엔드 서버 구동 상태, SQLite 낱알 캐시 건수, 인기 검색어 상위 8개, 내 약통 보관 개수,
      그리고 식약처 3대 OpenAPI 인증키 설정 완료 여부를 JSON으로 반환합니다.
    [연결 출발지]
    - `Backend/drugs/urls.py`의 `path("api/status/", views.api_status)`
    - 프론트엔드 `Frontend/app.js`의 `checkBackendStatus()` 함수가 페이지 로드 직후 호출합니다.
    [연결 목적지]
    - `Backend/drugs/models.py`의 `PillCache`, `SearchLog`, `SavedDrug` 모델
    - `Backend/drugs/services.py`의 `seed_initial_pill_cache()` (DB가 비어있을 때 초기 데이터 적재)
    """
    pill_count = PillCache.objects.count()
    if pill_count == 0:
        seed_initial_pill_cache()
        pill_count = PillCache.objects.count()

    popular_logs = list(
        SearchLog.objects.values("keyword", "count", "search_type").order_by(
            "-count", "-last_searched_at"
        )[:8]
    )
    pillbox_count = SavedDrug.objects.count()

    return JsonResponse(
        {
            "status": "ok",
            "backend": "Django 6.1 (SQLite3 + MFDS 3 OpenAPIs)",
            "apiKeysConfigured": all(bool(v) for v in settings.MFDS_API_KEYS.values()),
            "cachedPillsCount": pill_count,
            "pillboxCount": pillbox_count,
            "popularKeywords": popular_logs,
            "endpoints": {
                "grain": settings.MFDS_ENDPOINTS["GRAIN_BASE"],
                "permission": settings.MFDS_ENDPOINTS["PRMSN_BASE"],
                "easy": settings.MFDS_ENDPOINTS["EASY_BASE"],
            },
        }
    )


@require_GET
def api_unified_search(request: HttpRequest) -> JsonResponse:
    """
    [역할]
    - [탭 1: 통합 스마트 검색] 검색어(`q`) 및/또는 다중 낱알 외형 조건(`shapes`, `colors`, `forms`,
      `lineFront`, `lineBack`, `print`, `printExact`)을 결합하여 3대 OpenAPI 통합 결과를 반환합니다.
    [연결 출발지]
    - `Backend/drugs/urls.py`의 `path("api/unified-search/", views.api_unified_search)`
    - 프론트엔드 `Frontend/app.js`의 `runUnifiedSearch()` 내 `fetch("/api/unified-search/?...")`
    [연결 목적지]
    - `Backend/drugs/services.py`의 `parse_filter_values()`, `unified_drug_search()`
    - `Backend/drugs/models.py`의 `SearchLog` (`_record_search_log` 경유)
    [수정 가이드]
    - 기본 조회 건수를 60건에서 100건으로 늘리고 싶다면 아래 `default=60`을 `default=100`으로 수정하세요.
    """
    keyword = _clean_str(request.GET.get("q"), max_len=100)
    raw_field = _clean_str(request.GET.get("field", "itemName"), max_len=30)
    search_field = raw_field if raw_field in _ALLOWED_UNIFIED_FIELDS else "itemName"
    page_no = _parse_positive_int(request.GET.get("page"), default=1, max_val=1000)
    num_of_rows = _parse_positive_int(request.GET.get("rows"), default=60, max_val=100)

    shapes = parse_filter_values(request.GET.get("shapes") or request.GET.get("shape"))
    colors = parse_filter_values(request.GET.get("colors") or request.GET.get("color"))
    forms = parse_filter_values(request.GET.get("forms") or request.GET.get("form"))
    line_fronts = parse_filter_values(request.GET.get("lineFront"))
    line_backs = parse_filter_values(request.GET.get("lineBack"))
    print_text = _clean_str(request.GET.get("print"), max_len=50)
    print_exact = request.GET.get("printExact", "").strip().lower() in {"1", "true", "yes"}

    has_appearance_filter = bool(
        shapes or colors or forms or line_fronts or line_backs or print_text
    )

    if not keyword and not has_appearance_filter:
        return JsonResponse(
            {"error": "검색어를 입력하거나 알약 외형 조건을 선택해 주세요."}, status=400
        )

    if keyword:
        _record_search_log(keyword, "unified")
    elif print_text:
        _record_search_log(f"각인:{print_text}", "grain")

    items, counts = unified_drug_search(
        keyword=keyword,
        search_field=search_field,
        page_no=page_no,
        num_of_rows=num_of_rows,
        shapes=shapes,
        colors=colors,
        forms=forms,
        line_fronts=line_fronts,
        line_backs=line_backs,
        print_text=print_text,
        print_exact=print_exact,
    )
    return JsonResponse(
        {
            "keyword": keyword,
            "field": search_field,
            "counts": counts,
            "items": items,
        }
    )


@require_GET
def api_grain_search(request: HttpRequest) -> JsonResponse:
    """
    [역할]
    - 스마트 낱알 식별 단독 조회 엔드포인트 (모양·색상·제형·분할선·각인문자·키워드 복합 필터)입니다.
    [연결 출발지] `Backend/drugs/urls.py`의 `path("api/grain-search/", views.api_grain_search)`
    [연결 목적지] `Backend/drugs/services.py`의 `search_pills_by_appearance()` 및 `models.py`의 `PillCache`
    """
    shape = _clean_str(request.GET.get("shapes") or request.GET.get("shape"), max_len=200)
    color = _clean_str(request.GET.get("colors") or request.GET.get("color"), max_len=200)
    form_name = _clean_str(request.GET.get("forms") or request.GET.get("form"), max_len=200)
    line = _clean_str(request.GET.get("line"), max_len=100)
    line_front = _clean_str(request.GET.get("lineFront"), max_len=100)
    line_back = _clean_str(request.GET.get("lineBack"), max_len=100)
    print_text = _clean_str(request.GET.get("print"), max_len=50)
    print_exact = request.GET.get("printExact", "").strip().lower() in {"1", "true", "yes"}
    keyword = _clean_str(request.GET.get("q"), max_len=100)

    if keyword:
        _record_search_log(keyword, "grain")
    elif print_text:
        _record_search_log(f"각인:{print_text}", "grain")

    items, total_matched = search_pills_by_appearance(
        shape=shape,
        color=color,
        form_name=form_name,
        line=line,
        line_front=line_front,
        line_back=line_back,
        print_text=print_text,
        print_exact=print_exact,
        keyword=keyword,
    )
    return JsonResponse(
        {
            "totalMatched": total_matched,
            "cachedTotal": PillCache.objects.count(),
            "items": items,
        }
    )


@require_GET
def api_permission_search(request: HttpRequest) -> JsonResponse:
    """
    [역할]
    - [탭 2: 허가·성분 전문조회] 식약처 의약품 제품 허가정보(`DrugPrdtPrmsnInfoService08`)를 조회하여
      주성분명, 전문/일반 구분, 품목허가일, 보험코드(EDI) 목록을 반환합니다.
    [연결 출발지]
    - `Backend/drugs/urls.py`의 `path("api/permission-search/", views.api_permission_search)`
    - 프론트엔드 `Frontend/app.js`의 `runPermissionSearch()` 함수
    [연결 목적지]
    - `Backend/drugs/services.py`의 `fetch_prmsn_list()`
    """
    keyword = _clean_str(request.GET.get("q"), max_len=100)
    raw_field = _clean_str(request.GET.get("field", "item_name"), max_len=30)
    search_field = raw_field if raw_field in _ALLOWED_PRMSN_FIELDS else "item_name"
    spclty_pblc = _clean_str(request.GET.get("spclty"), max_len=30)
    page_no = _parse_positive_int(request.GET.get("page"), default=1, max_val=1000)

    if spclty_pblc == "전체":
        spclty_pblc = ""

    if keyword:
        _record_search_log(keyword, "prmsn")

    raw_items, total_count = fetch_prmsn_list(
        keyword=keyword,
        search_field=search_field,
        spclty_pblc=spclty_pblc,
        page_no=page_no,
        num_of_rows=60,
    )

    items = [
        {
            "itemSeq": r.get("ITEM_SEQ") or "",
            "itemName": r.get("ITEM_NAME") or "",
            "itemEngName": r.get("ITEM_ENG_NAME") or "",
            "entpName": r.get("ENTP_NAME") or "",
            "entpEngName": r.get("ENTP_ENG_NAME") or "",
            "itemPermitDate": r.get("ITEM_PERMIT_DATE") or "",
            "induty": r.get("INDUTY") or "",
            "etcOtcName": r.get("SPCLTY_PBLC") or "",
            "className": r.get("PRDUCT_TYPE") or "",
            "itemIngrName": clean_ingredient_text(r.get("ITEM_INGR_NAME")),
            "itemIngrCnt": r.get("ITEM_INGR_CNT") or "",
            "itemImage": r.get("BIG_PRDT_IMG_URL") or "",
            "ediCode": r.get("EDI_CODE") or "",
            "bizrno": r.get("BIZRNO") or "",
            "cancelName": r.get("CANCEL_NAME") or "정상",
            "sources": ["허가정보"],
        }
        for r in raw_items
    ]

    return JsonResponse(
        {
            "totalCount": total_count,
            "items": items,
        }
    )


@require_GET
def api_drug_detail(request: HttpRequest) -> JsonResponse:
    """
    [역할]
    - 사용자가 특정 의약품 카드를 클릭했을 때 로컬 SQLite 캐시(`PillCache`)와
      식약처 3대 OpenAPI(e약은요 + 낱알식별 + 제품허가 목록/상세)를 실시간 병렬 교차 조회하여
      누락 없는 통합 상세 정보를 반환합니다.
    [연결 출발지]
    - `Backend/drugs/urls.py`의 `path("api/drug-detail/", views.api_drug_detail)`
    - 프론트엔드 `Frontend/app.js`의 `openDetailModal()` 함수 내 `fetch("/api/drug-detail/?...")`
    [연결 목적지]
    - `Backend/drugs/services.py`의 `enrich_single_drug_detail()`
    """
    item_seq = _clean_str(request.GET.get("itemSeq"), max_len=32)
    item_name = _clean_str(request.GET.get("itemName"), max_len=255)
    if not item_seq and not item_name:
        return JsonResponse({"error": "itemSeq 또는 itemName이 필요합니다."}, status=400)

    detail = enrich_single_drug_detail(item_seq=item_seq, item_name=item_name)
    return JsonResponse(detail)


def _build_safety_report(saved_qs: QuerySet[SavedDrug]) -> dict[str, Any]:
    """
    [역할]
    - '내 약통(`SavedDrug`)'에 보관된 의약품들의 주성분(`ingr_name`)을 파싱하여,
      2개 이상의 약에 동일한 주성분이 포함되어 있는지(과량 복용 위험) 분석 리포트를 생성합니다.
    [연결 출발지] 아래 `api_pillbox()` 함수 내부(GET, POST, DELETE 응답 시)에서 호출됩니다.
    [연결 목적지] `Backend/drugs/models.py`의 `SavedDrug` 쿼리셋을 읽어 분석 결과를
      프론트엔드 `Frontend/app.js`의 `loadPillbox()` (`safetyReportBox`)로 전달합니다.
    [수정 가이드]
    - 만약 3개 이상 중복될 때만 경고를 띄우고 싶다면:
      아래 `if len(v["drugs"]) >= 2` 조건을 `>= 3`으로 수정하세요.
    """
    saved_list = list(saved_qs)
    ingr_map: dict[str, dict[str, Any]] = {}
    warnings: list[dict[str, str]] = []

    for d in saved_list:
        raw_ingr = clean_ingredient_text(d.ingr_name)
        parts = [
            p.strip()
            for p in raw_ingr.replace("|", "/").replace(",", "/").replace(";", "/").split("/")
            if p.strip()
        ]
        for ingr in parts:
            key = ingr.lower()
            ingr_map.setdefault(key, {"name": ingr, "drugs": []})
            if d.item_name not in ingr_map[key]["drugs"]:
                ingr_map[key]["drugs"].append(d.item_name)

        if d.warn_text:
            warnings.append(
                {
                    "itemName": d.item_name,
                    "warnSummary": d.warn_text[:220] + ("..." if len(d.warn_text) > 220 else ""),
                }
            )

    duplicates = [
        {"ingredient": v["name"], "drugs": v["drugs"]}
        for v in ingr_map.values()
        if len(v["drugs"]) >= 2
    ]

    return {
        "totalSaved": len(saved_list),
        "duplicateIngredients": duplicates,
        "hasDuplicateRisk": len(duplicates) > 0,
        "warnings": warnings,
    }


@csrf_exempt
@require_http_methods(["GET", "POST", "DELETE"])
def api_pillbox(request: HttpRequest) -> JsonResponse:
    """
    [역할]
    - [탭 3: 내 약통] 복약 수첩 조회(`GET`), 의약품 추가·수정(`POST`), 삭제(`DELETE`) 및
      주성분 중복 안전 리포트를 처리하는 RESTful 엔드포인트입니다.
    [연결 출발지]
    - `Backend/drugs/urls.py`의 `path("api/pillbox/", views.api_pillbox)`
    - 프론트엔드 `Frontend/app.js`의 `loadPillbox()` (GET), `addToPillbox()` (POST), `removeFromPillbox()` (DELETE)
    [연결 목적지]
    - `Backend/drugs/models.py`의 `SavedDrug` 모델 (`Backend/db.sqlite3`)
    - 주성분 정보가 비어 있을 경우 `Backend/drugs/services.py`의 `enrich_single_drug_detail()`을 호출해 자동 보강
    """
    if request.method == "GET":
        qs = SavedDrug.objects.all()
        items = [
            {
                "id": d.id,
                "itemSeq": d.item_seq,
                "itemName": d.item_name,
                "entpName": d.entp_name,
                "itemImage": d.item_image,
                "etcOtcName": d.etc_otc_name,
                "className": d.class_name,
                "itemIngrName": d.ingr_name,
                "efcyQesitm": d.efcy_text,
                "useMethodQesitm": d.use_method_text,
                "atpnQesitm": d.warn_text,
                "dosageTime": d.dosage_time,
                "memo": d.memo,
                "createdAt": timezone.localtime(d.created_at).strftime("%Y-%m-%d %H:%M")
                if d.created_at
                else "",
            }
            for d in qs
        ]
        return JsonResponse(
            {
                "items": items,
                "safetyReport": _build_safety_report(qs),
            }
        )

    if request.method == "POST":
        if len(request.body) > _MAX_JSON_BODY_BYTES:
            return JsonResponse({"error": "요청 본문 크기가 허용 한도를 초과했습니다."}, status=413)

        try:
            body = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "잘못된 JSON 요청 형식입니다."}, status=400)

        if not isinstance(body, dict):
            return JsonResponse({"error": "JSON 객체(Object) 형식이어야 합니다."}, status=400)

        item_seq = _clean_str(body.get("itemSeq"), max_len=32)
        item_name = _clean_str(body.get("itemName"), max_len=255)
        if not item_name:
            return JsonResponse({"error": "품목명이 필요합니다."}, status=400)

        ingr_name = clean_ingredient_text(body.get("itemIngrName"))
        efcy_text = _clean_str(body.get("efcyQesitm"), max_len=5000)
        warn_text = _clean_str(
            body.get("atpnWarnQesitm") or body.get("intrcQesitm") or body.get("atpnQesitm"),
            max_len=5000,
        )

        # 주성분명이 비어 있으면 식약처 상세 API 교차 조회를 통해 자동으로 주성분·효능·주의사항을 채웁니다.
        if not ingr_name:
            enriched = enrich_single_drug_detail(item_seq=item_seq, item_name=item_name)
            ingr_name = ingr_name or clean_ingredient_text(enriched.get("itemIngrName"))
            efcy_text = efcy_text or _clean_str(enriched.get("efcyQesitm"), max_len=5000)
            warn_text = (
                warn_text
                or _clean_str(enriched.get("atpnWarnQesitm"), max_len=5000)
                or _clean_str(enriched.get("intrcQesitm"), max_len=5000)
                or _clean_str(enriched.get("atpnQesitm"), max_len=5000)
            )

        lookup_seq = (item_seq or item_name)[:32]
        defaults: dict[str, Any] = {
            "item_name": item_name,
            "entp_name": _clean_str(body.get("entpName"), max_len=150),
            "item_image": _sanitize_http_url(body.get("itemImage"), max_len=500),
            "etc_otc_name": _clean_str(body.get("etcOtcName"), max_len=50),
            "class_name": _clean_str(body.get("className"), max_len=120),
            "ingr_name": ingr_name,
            "efcy_text": efcy_text,
            "use_method_text": _clean_str(body.get("useMethodQesitm"), max_len=5000),
            "warn_text": warn_text,
            "dosage_time": _clean_str(body.get("dosageTime") or "아침·저녁 식후 30분", max_len=100),
            "memo": _clean_str(body.get("memo"), max_len=255),
        }

        existing = SavedDrug.objects.filter(item_seq=lookup_seq).first()
        if existing:
            for field_name, val in defaults.items():
                setattr(existing, field_name, val)
            existing.save()
            obj, created = existing, False
        else:
            obj = SavedDrug.objects.create(item_seq=lookup_seq, **defaults)
            created = True

        qs = SavedDrug.objects.all()
        return JsonResponse(
            {
                "message": "내 약통에 저장되었습니다." if created else "내 약통 정보가 업데이트되었습니다.",
                "id": obj.id,
                "pillboxCount": qs.count(),
                "safetyReport": _build_safety_report(qs),
            }
        )

    # DELETE 요청 처리
    drug_id = _clean_str(request.GET.get("id"), max_len=20)
    item_seq = _clean_str(request.GET.get("itemSeq"), max_len=32)
    if drug_id and drug_id.isdigit():
        SavedDrug.objects.filter(id=int(drug_id)).delete()
    elif item_seq:
        SavedDrug.objects.filter(item_seq=item_seq).delete()

    qs = SavedDrug.objects.all()
    return JsonResponse(
        {
            "message": "삭제되었습니다.",
            "pillboxCount": qs.count(),
            "safetyReport": _build_safety_report(qs),
        }
    )
