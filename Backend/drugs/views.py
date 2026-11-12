"""
[역할] 프론트엔드 템플릿·정적 자산 서빙 및 의약품 검색·상세·내 약통(CRUD) REST JSON 컨트롤러
[경로] Backend/config/urls.py & drugs/urls.py -> Backend/drugs/views.py -> services.py & models.py
[수정] 페이지당 API 기본 조회 건수를 바꾸려면 api_unified_search / api_permission_search의 num_of_rows를 조정하세요.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from django.conf import settings
from django.db import IntegrityError
from django.db.models import F
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods

from .models import PillCache, SavedDrug, SearchLog
from .services import (
    clean_ingredient_text,
    enrich_single_drug_detail,
    extract_ingredient_tokens,
    fetch_prmsn_list,
    parse_filter_values,
    sanitize_http_url,
    seed_initial_pill_cache,
    unified_drug_search,
)

ALLOWED_FRONTEND_ASSETS: Final[dict[str, str]] = {
    "style.css": "text/css; charset=utf-8",
    "app.js": "application/javascript; charset=utf-8",
}

_ALLOWED_UNIFIED_FIELDS: Final[frozenset[str]] = frozenset({"itemName", "efcy", "entp"})
_ALLOWED_PRMSN_FIELDS: Final[frozenset[str]] = frozenset({"item_name", "entp"})
_MAX_JSON_BODY_BYTES: Final[int] = 65_536

_FAVICON_SVG: Final[str] = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="10" fill="#132A24"/>'
    '<rect x="10" y="10" width="44" height="44" rx="4" fill="none" stroke="#D8D2C5" stroke-width="2"/>'
    '<path d="M22 32h20M32 22v20" stroke="#F4F1EA" stroke-width="4.5" stroke-linecap="square"/>'
    '<circle cx="46" cy="18" r="4" fill="#C2593F"/>'
    "</svg>"
)


def _parse_positive_int(raw_val: str | None, default: int = 1, max_val: int = 100) -> int:
    """
    [역할] 쿼리 파라미터 문자열을 1 ~ max_val 범위의 양의 정수로 안전하게 변환합니다.
    [경로] api_unified_search / api_permission_search -> _parse_positive_int()
    [수정] 상한을 늘리려면 호출부의 max_val 인자를 변경하세요.
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
    [역할] 입력값을 문자열로 변환하고 공백 제거 후 최대 길이(max_len)로 제한합니다.
    [경로] 모든 API 뷰 -> _clean_str() -> 검증된 문자열 반환
    [수정] 길이 제한 변경 시 호출부의 max_len 인자를 수정하세요.
    """
    if raw_val is None:
        return ""
    return str(raw_val).strip()[:max_len]


def _parse_json_dict(request: HttpRequest) -> tuple[dict[str, Any] | None, JsonResponse | None]:
    """
    [역할] POST/PATCH 요청 본문의 크기 제한(64KB), UTF-8 디코딩, JSON 객체(dict) 여부를 검증합니다.
    [경로] api_pillbox() -> _parse_json_dict() -> (body_dict, error_response)
    [수정] 허용 본문 크기를 바꾸려면 상단 _MAX_JSON_BODY_BYTES 값을 변경하세요.
    """
    if len(request.body) > _MAX_JSON_BODY_BYTES:
        return None, JsonResponse({"error": "요청 본문 크기가 허용 한도를 초과했습니다."}, status=413)
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, JsonResponse({"error": "잘못된 JSON 요청 형식입니다."}, status=400)
    if not isinstance(body, dict):
        return None, JsonResponse({"error": "JSON 객체(Object) 형식이어야 합니다."}, status=400)
    return body, None


@require_GET
@ensure_csrf_cookie
def index(request: HttpRequest) -> HttpResponse:
    """
    [역할] CSRF 쿠키와 CSP 논스를 포함하여 메인 화면(Frontend/index.html)을 렌더링합니다.
    [경로] GET / -> Backend/drugs/urls.py -> index() -> Frontend/index.html
    [수정] 템플릿에 초기 서버 변수를 추가 전달하려면 render의 세 번째 context 사전에 키를 추가하세요.
    """
    return render(
        request,
        "index.html",
        {"csp_nonce": getattr(request, "csp_nonce", "")},
    )


@require_GET
def serve_favicon(request: HttpRequest) -> HttpResponse:
    """
    [역할] /favicon.ico 요청에 경량 SVG 아이콘을 반환해 불필요한 404 로그를 방지합니다.
    [경로] GET /favicon.ico -> Backend/config/urls.py -> serve_favicon()
    [수정] 아이콘 디자인을 바꾸려면 상단 _FAVICON_SVG 문자열을 수정하세요.
    """
    response = HttpResponse(_FAVICON_SVG, content_type="image/svg+xml; charset=utf-8")
    response["Cache-Control"] = "public, max-age=86400"
    return response


@require_GET
def serve_frontend_asset(request: HttpRequest, filename: str) -> FileResponse:
    """
    [역할] 화이트리스트와 Path.is_relative_to 이중 검증으로 경로 조작을 차단하고 style.css / app.js를 서빙합니다.
    [경로] GET /style.css, /app.js -> Backend/config/urls.py -> serve_frontend_asset() -> Frontend/*
    [수정] 새 정적 파일 허용 시 ALLOWED_FRONTEND_ASSETS와 config/urls.py에 함께 추가하세요.
    """
    content_type = ALLOWED_FRONTEND_ASSETS.get(filename)
    if not content_type:
        raise Http404("허용되지 않은 정적 리소스입니다.")

    frontend_root = Path(settings.FRONTEND_DIR).resolve()
    file_path = (frontend_root / filename).resolve()
    if not file_path.is_relative_to(frontend_root) or not file_path.is_file():
        raise Http404(f"{filename} 파일을 찾을 수 없습니다.")

    response = FileResponse(file_path.open("rb"), content_type=content_type)
    response["Cache-Control"] = "no-cache" if settings.DEBUG else "public, max-age=3600"
    return response


def _record_search_log(keyword: str, search_type: str = "unified") -> None:
    """
    [역할] 검색 키워드 조회수를 단일 UPDATE 우선 방식으로 SearchLog 테이블에 원자적 누적합니다.
    [경로] api_unified_search / api_permission_search -> _record_search_log() -> SearchLog
    [수정] 집계 제외 단어를 두려면 if not kw 조건 뒤에 불용어 필터를 추가하세요.
    """
    kw = _clean_str(keyword, max_len=50)
    if not kw:
        return
    updated = SearchLog.objects.filter(keyword=kw).update(
        count=F("count") + 1,
        search_type=search_type,
        last_searched_at=timezone.now(),
    )
    if not updated:
        try:
            SearchLog.objects.create(keyword=kw, search_type=search_type, count=1)
        except IntegrityError:
            SearchLog.objects.filter(keyword=kw).update(count=F("count") + 1)


@require_GET
def api_status(request: HttpRequest) -> JsonResponse:
    """
    [역할] 백엔드 상태, SQLite 낱알 캐시 적재 건수, 내 약통 보관 건수를 반환합니다.
    [경로] Frontend/app.js (syncPillboxStatus) -> GET /api/status/ -> PillCache, SavedDrug
    [수정] 상태 응답에 추가 지표가 필요하면 아래 JsonResponse 사전에 키를 추가하세요.
    """
    pill_count = PillCache.objects.count()
    if pill_count == 0:
        seed_initial_pill_cache()
        pill_count = PillCache.objects.count()

    return JsonResponse(
        {
            "status": "ok",
            "backend": "Django 6.1 · SQLite WAL",
            "apiKeysConfigured": all(bool(v) for v in settings.MFDS_API_KEYS.values()),
            "cachedPillsCount": pill_count,
            "pillboxCount": SavedDrug.objects.count(),
        }
    )


@require_GET
def api_unified_search(request: HttpRequest) -> JsonResponse:
    """
    [역할] 검색어 및 다중 낱알 외형 조건을 결합하여 식약처 3대 공공데이터 통합 검색 결과를 반환합니다.
    [경로] Frontend/app.js (runUnifiedSearch) -> GET /api/unified-search/ -> services.unified_drug_search()
    [수정] 기본 조회 행 수를 조정하려면 num_of_rows의 default=60 값을 변경하세요.
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
def api_permission_search(request: HttpRequest) -> JsonResponse:
    """
    [역할] 식약처 의약품 제품 허가정보(전문의약품·일반의약품, 주성분, 허가일, EDI) 목록을 조회합니다.
    [경로] Frontend/app.js (runPermissionSearch) -> GET /api/permission-search/ -> services.fetch_prmsn_list()
    [수정] 업체명 검색 옵션을 프론트엔드에서 넘기면 field=entp 파라미터로 자동 분기됩니다.
    """
    keyword = _clean_str(request.GET.get("q"), max_len=100)
    raw_field = _clean_str(request.GET.get("field", "item_name"), max_len=30)
    search_field = raw_field if raw_field in _ALLOWED_PRMSN_FIELDS else "item_name"
    spclty_pblc = _clean_str(request.GET.get("spclty"), max_len=30)
    page_no = _parse_positive_int(request.GET.get("page"), default=1, max_val=1000)

    if spclty_pblc == "전체":
        spclty_pblc = ""

    if not keyword and not spclty_pblc:
        return JsonResponse(
            {"error": "품목명·업체명을 입력하거나 전문/일반 구분을 선택해 주세요."}, status=400
        )

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
            "itemImage": sanitize_http_url(r.get("BIG_PRDT_IMG_URL")),
            "ediCode": r.get("EDI_CODE") or "",
            "bizrno": r.get("BIZRNO") or "",
            "cancelName": r.get("CANCEL_NAME") or "정상",
            "sources": ["허가정보"],
        }
        for r in raw_items
    ]
    return JsonResponse({"totalCount": total_count, "items": items})


@require_GET
def api_drug_detail(request: HttpRequest) -> JsonResponse:
    """
    [역할] 단일 의약품의 복약안내·낱알외형·허가상세 정보를 실시간 병렬 교차 조회해 반환합니다.
    [경로] Frontend/app.js (openDetailModal) -> GET /api/drug-detail/ -> services.enrich_single_drug_detail()
    [수정] 응답 필드를 추가하려면 services.py의 enrich_single_drug_detail() 사전을 수정하세요.
    """
    item_seq = _clean_str(request.GET.get("itemSeq"), max_len=32)
    item_name = _clean_str(request.GET.get("itemName"), max_len=255)
    if not item_seq and not item_name:
        return JsonResponse({"error": "itemSeq 또는 itemName이 필요합니다."}, status=400)

    return JsonResponse(enrich_single_drug_detail(item_seq=item_seq, item_name=item_name))


def _serialize_saved_drug(drug: SavedDrug) -> dict[str, Any]:
    """
    [역할] SavedDrug ORM 객체를 프론트엔드 JSON 응답 구조로 직렬화합니다.
    [경로] api_pillbox() -> _serialize_saved_drug() -> Frontend/app.js
    [수정] 노출 날짜 포맷을 바꾸려면 strftime 패턴을 변경하세요.
    """
    return {
        "id": drug.id,
        "itemSeq": drug.item_seq,
        "itemName": drug.item_name,
        "entpName": drug.entp_name,
        "itemImage": sanitize_http_url(drug.item_image),
        "etcOtcName": drug.etc_otc_name,
        "className": drug.class_name,
        "itemIngrName": drug.ingr_name,
        "efcyQesitm": drug.efcy_text,
        "useMethodQesitm": drug.use_method_text,
        "atpnQesitm": drug.warn_text,
        "dosageTime": drug.dosage_time,
        "memo": drug.memo,
        "createdAt": timezone.localtime(drug.created_at).strftime("%Y-%m-%d %H:%M")
        if drug.created_at
        else "",
    }


def _build_safety_report(saved_list: Sequence[SavedDrug]) -> dict[str, Any]:
    """
    [역할] 메모리에 적재된 SavedDrug 목록에서 주성분 중복 위험(2개 이상 약품 공유)과 주의사항 요약을 생성합니다.
    [경로] api_pillbox() -> _build_safety_report() -> Frontend/app.js (safetyReportBox)
    [수정] 중복 경고 임계치를 3개 이상으로 바꾸려면 `len(v["drugs"]) >= 2`를 `>= 3`으로 변경하세요.
    """
    ingr_map: dict[str, dict[str, Any]] = {}
    warnings: list[dict[str, str]] = []

    for d in saved_list:
        for canonical_key, display_name in extract_ingredient_tokens(d.ingr_name):
            entry = ingr_map.setdefault(canonical_key, {"name": display_name, "drugs": []})
            if d.item_name not in entry["drugs"]:
                entry["drugs"].append(d.item_name)

        if d.warn_text:
            warnings.append(
                {
                    "itemName": d.item_name,
                    "warnSummary": d.warn_text[:200] + ("..." if len(d.warn_text) > 200 else ""),
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
        "hasDuplicateRisk": bool(duplicates),
        "warnings": warnings,
    }


@require_http_methods(["GET", "POST", "PATCH", "DELETE"])
def api_pillbox(request: HttpRequest) -> JsonResponse:
    """
    [역할] 내 약통 전체 CRUD(조회 GET, 등록 POST, 복용시간·메모 수정 PATCH, 삭제 DELETE) 및 안전 리포트 반환
    [경로] Frontend/app.js -> /api/pillbox/ (CSRF 검증 포함) -> SavedDrug (Backend/db.sqlite3)
    [수정] 기본 복용 시간대를 바꾸려면 POST 분기의 dosage_time 기본 문자열을 수정하세요.
    """
    if request.method == "GET":
        saved_list = list(SavedDrug.objects.all())
        return JsonResponse(
            {
                "items": [_serialize_saved_drug(d) for d in saved_list],
                "safetyReport": _build_safety_report(saved_list),
            }
        )

    if request.method == "POST":
        body, err = _parse_json_dict(request)
        if err is not None or body is None:
            return err  # type: ignore[return-value]

        item_seq = _clean_str(body.get("itemSeq"), max_len=32)
        item_name = _clean_str(body.get("itemName"), max_len=255)
        if not item_name:
            return JsonResponse({"error": "품목명이 필요합니다."}, status=400)

        ingr_name = clean_ingredient_text(body.get("itemIngrName"))
        efcy_text = _clean_str(body.get("efcyQesitm"), max_len=5000)
        use_method_text = _clean_str(body.get("useMethodQesitm"), max_len=5000)
        warn_text = _clean_str(
            body.get("atpnWarnQesitm") or body.get("intrcQesitm") or body.get("atpnQesitm"),
            max_len=5000,
        )

        if not ingr_name:
            enriched = enrich_single_drug_detail(item_seq=item_seq, item_name=item_name)
            ingr_name = ingr_name or clean_ingredient_text(enriched.get("itemIngrName"))
            efcy_text = efcy_text or _clean_str(enriched.get("efcyQesitm"), max_len=5000)
            use_method_text = use_method_text or _clean_str(
                enriched.get("useMethodQesitm"), max_len=5000
            )
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
            "item_image": sanitize_http_url(body.get("itemImage"), max_len=500),
            "etc_otc_name": _clean_str(body.get("etcOtcName"), max_len=50),
            "class_name": _clean_str(body.get("className"), max_len=120),
            "ingr_name": ingr_name,
            "efcy_text": efcy_text,
            "use_method_text": use_method_text,
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

        saved_list = list(SavedDrug.objects.all())
        return JsonResponse(
            {
                "message": "내 약통에 등록되었습니다." if created else "내 약통 정보가 갱신되었습니다.",
                "id": obj.id,
                "item": _serialize_saved_drug(obj),
                "pillboxCount": len(saved_list),
                "safetyReport": _build_safety_report(saved_list),
            }
        )

    if request.method == "PATCH":
        body, err = _parse_json_dict(request)
        if err is not None or body is None:
            return err  # type: ignore[return-value]

        raw_id = body.get("id")
        item_seq = _clean_str(body.get("itemSeq"), max_len=32)
        target: SavedDrug | None = None
        if raw_id is not None and str(raw_id).isdigit():
            target = SavedDrug.objects.filter(id=int(raw_id)).first()
        elif item_seq:
            target = SavedDrug.objects.filter(item_seq=item_seq).first()

        if target is None:
            return JsonResponse({"error": "수정할 약통 항목을 찾을 수 없습니다."}, status=404)

        if "dosageTime" in body:
            target.dosage_time = _clean_str(
                body.get("dosageTime") or "아침·저녁 식후 30분", max_len=100
            )
        if "memo" in body:
            target.memo = _clean_str(body.get("memo"), max_len=255)
        target.save(update_fields=["dosage_time", "memo"])

        saved_list = list(SavedDrug.objects.all())
        return JsonResponse(
            {
                "message": "복용 정보가 수정되었습니다.",
                "item": _serialize_saved_drug(target),
                "pillboxCount": len(saved_list),
                "safetyReport": _build_safety_report(saved_list),
            }
        )

    # DELETE 요청 처리
    drug_id = _clean_str(request.GET.get("id"), max_len=20)
    item_seq = _clean_str(request.GET.get("itemSeq"), max_len=32)
    if drug_id and drug_id.isdigit():
        SavedDrug.objects.filter(id=int(drug_id)).delete()
    elif item_seq:
        SavedDrug.objects.filter(item_seq=item_seq).delete()
    else:
        return JsonResponse({"error": "삭제할 대상 id 또는 itemSeq가 필요합니다."}, status=400)

    saved_list = list(SavedDrug.objects.all())
    return JsonResponse(
        {
            "message": "삭제되었습니다.",
            "pillboxCount": len(saved_list),
            "safetyReport": _build_safety_report(saved_list),
        }
    )
