"""
의약품 검색·식별·허가조회 및 '내 약통' CRUD HTTP API 뷰 컨트롤러 모듈.
Frontend 폴더의 정적 리소스(index.html, style.css, app.js) 서빙과 JSON REST 엔드포인트를 담당합니다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models import F, QuerySet
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .models import PillCache, SavedDrug, SearchLog
from .services import (
    enrich_single_drug_detail,
    fetch_prmsn_list,
    parse_filter_values,
    search_pills_by_appearance,
    seed_initial_pill_cache,
    unified_drug_search,
)

# 루트 경로에서 서빙을 허용할 Frontend 정적 파일 화이트리스트 (경로 조작 취약점 원천 차단)
ALLOWED_FRONTEND_ASSETS: dict[str, str] = {
    "style.css": "text/css; charset=utf-8",
    "app.js": "application/javascript; charset=utf-8",
}


def _parse_positive_int(raw_val: str | None, default: int = 1, max_val: int = 100) -> int:
    """쿼리 파라미터 문자열을 안전한 양의 정수(1 ~ max_val)로 변환합니다."""
    if not raw_val:
        return default
    try:
        parsed = int(raw_val)
    except (ValueError, TypeError):
        return default
    return max(1, min(parsed, max_val))


@require_GET
def index(request: HttpRequest) -> HttpResponse:
    """메인 반응형 웹 애플리케이션(Frontend/index.html) 렌더링"""
    return render(request, "index.html")


@require_GET
def serve_frontend_asset(request: HttpRequest, filename: str) -> FileResponse:
    """Frontend 디렉터리의 style.css, app.js를 스트리밍 FileResponse로 고속 서빙합니다."""
    content_type = ALLOWED_FRONTEND_ASSETS.get(filename)
    if not content_type:
        raise Http404("허용되지 않은 정적 리소스입니다.")

    file_path = Path(settings.FRONTEND_DIR) / filename
    if not file_path.is_file():
        raise Http404(f"{filename} 파일을 찾을 수 없습니다.")

    return FileResponse(file_path.open("rb"), content_type=content_type)


def _record_search_log(keyword: str, search_type: str = "unified") -> None:
    """검색 키워드 통계를 SearchLog 테이블에 원자적(F 표현식)으로 누적 기록합니다."""
    kw = (keyword or "").strip()
    if not kw or len(kw) > 50:
        return
    obj, created = SearchLog.objects.get_or_create(
        keyword=kw,
        defaults={"search_type": search_type, "count": 1},
    )
    if not created:
        SearchLog.objects.filter(pk=obj.pk).update(count=F("count") + 1, search_type=search_type)


@require_GET
def api_status(request: HttpRequest) -> JsonResponse:
    """Django 백엔드 구동 상태, SQLite 낱알 캐시 건수, 인기 검색어, 내 약통 개수를 반환합니다."""
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
    """[탭 1] 통합 의약품 검색 (검색어 및/또는 다중 낱알 외형 조건 결합 조회)"""
    keyword = request.GET.get("q", "").strip()
    search_field = request.GET.get("field", "itemName").strip()
    page_no = _parse_positive_int(request.GET.get("page"), default=1, max_val=1000)
    num_of_rows = _parse_positive_int(request.GET.get("rows"), default=60, max_val=100)

    shapes = parse_filter_values(request.GET.get("shapes") or request.GET.get("shape"))
    colors = parse_filter_values(request.GET.get("colors") or request.GET.get("color"))
    forms = parse_filter_values(request.GET.get("forms") or request.GET.get("form"))
    line_fronts = parse_filter_values(request.GET.get("lineFront"))
    line_backs = parse_filter_values(request.GET.get("lineBack"))
    print_text = request.GET.get("print", "").strip()
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
    """스마트 낱알 식별 조회 (모양·색상·제형·분할선·각인문자·키워드 복합 필터)"""
    shape = (request.GET.get("shapes") or request.GET.get("shape") or "").strip()
    color = (request.GET.get("colors") or request.GET.get("color") or "").strip()
    form_name = (request.GET.get("forms") or request.GET.get("form") or "").strip()
    line = request.GET.get("line", "").strip()
    line_front = request.GET.get("lineFront", "").strip()
    line_back = request.GET.get("lineBack", "").strip()
    print_text = request.GET.get("print", "").strip()
    print_exact = request.GET.get("printExact", "").strip().lower() in {"1", "true", "yes"}
    keyword = request.GET.get("q", "").strip()

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
    """[탭 3] 식약처 의약품 제품 허가정보 전문 조회"""
    keyword = request.GET.get("q", "").strip()
    search_field = request.GET.get("field", "item_name").strip()
    spclty_pblc = request.GET.get("spclty", "").strip()
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
            "itemIngrName": r.get("ITEM_INGR_NAME") or "",
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
    """의약품 카드 클릭 시 3대 OpenAPI 상세 정보를 실시간 교차 조회"""
    item_seq = request.GET.get("itemSeq", "").strip()
    item_name = request.GET.get("itemName", "").strip()
    if not item_seq and not item_name:
        return JsonResponse({"error": "itemSeq 또는 itemName이 필요합니다."}, status=400)

    detail = enrich_single_drug_detail(item_seq=item_seq, item_name=item_name)
    return JsonResponse(detail)


def _build_safety_report(saved_qs: QuerySet[SavedDrug]) -> dict[str, Any]:
    """내 약통에 담긴 의약품들의 주성분(ingr_name) 중복 여부 및 병용·주의사항 요약 리포트를 생성합니다."""
    saved_list = list(saved_qs)
    ingr_map: dict[str, dict[str, Any]] = {}
    warnings: list[dict[str, str]] = []

    for d in saved_list:
        raw_ingr = d.ingr_name or ""
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
    """[탭 4] 내 약통(복약 수첩) 조회(GET) / 추가·수정(POST) / 삭제(DELETE) 및 주성분 중복 안전 분석 API"""
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
        try:
            body = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "잘못된 JSON 요청 형식입니다."}, status=400)

        item_seq = str(body.get("itemSeq") or "").strip()
        item_name = str(body.get("itemName") or "").strip()
        if not item_name:
            return JsonResponse({"error": "품목명이 필요합니다."}, status=400)

        ingr_name = str(body.get("itemIngrName") or "").strip()
        efcy_text = str(body.get("efcyQesitm") or "").strip()
        warn_text = str(
            body.get("atpnWarnQesitm") or body.get("intrcQesitm") or body.get("atpnQesitm") or ""
        ).strip()

        if not ingr_name:
            enriched = enrich_single_drug_detail(item_seq=item_seq, item_name=item_name)
            ingr_name = ingr_name or enriched.get("itemIngrName", "")
            efcy_text = efcy_text or enriched.get("efcyQesitm", "")
            warn_text = (
                warn_text
                or enriched.get("atpnWarnQesitm")
                or enriched.get("intrcQesitm")
                or enriched.get("atpnQesitm", "")
            )

        lookup_seq = item_seq or item_name
        defaults = {
            "item_name": item_name,
            "entp_name": str(body.get("entpName") or "").strip(),
            "item_image": str(body.get("itemImage") or "").strip(),
            "etc_otc_name": str(body.get("etcOtcName") or "").strip(),
            "class_name": str(body.get("className") or "").strip(),
            "ingr_name": ingr_name,
            "efcy_text": efcy_text,
            "use_method_text": str(body.get("useMethodQesitm") or "").strip(),
            "warn_text": warn_text,
            "dosage_time": str(body.get("dosageTime") or "아침·저녁 식후 30분").strip(),
            "memo": str(body.get("memo") or "").strip(),
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
    drug_id = request.GET.get("id", "").strip()
    item_seq = request.GET.get("itemSeq", "").strip()
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
