"""
식약처 3대 공공데이터(OpenAPI) 연동, 응답 정규화, 고속 병렬 병합 및 SQLite 캐싱 서비스 모듈.
- API 1: 의약품 낱알식별 정보 (MdcinGrnIdntfcInfoService03)
- API 2: 의약품 제품 허가정보 (DrugPrdtPrmsnInfoService08)
- API 3: 의약품개요정보 e약은요 (DrbEasyDrugInfoService)
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import PillCache

logger = logging.getLogger(__name__)

# 정규표현식 사전 컴파일 (반복 문자열 정제 시 CPU 오버헤드 절감)
_TAG_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"[ \t]+")
_NEWLINE_RE = re.compile(r"\n{3,}")
_PAREN_SPLIT_RE = re.compile(r"[\(\[]")

# HTTP 커넥션 풀 타임아웃 (연결 타임아웃, 읽기 타임아웃)
DEFAULT_TIMEOUT: tuple[float, float] = (3.5, 8.0)
DETAIL_TIMEOUT: tuple[float, float] = (3.0, 4.5)
CACHE_TTL_SECONDS: int = 600

# bulk_create upsert 대상 컬럼 목록
_PILL_CACHE_UPDATE_FIELDS: list[str] = [
    "item_name",
    "entp_name",
    "chart",
    "item_image",
    "print_front",
    "print_back",
    "drug_shape",
    "color_class1",
    "color_class2",
    "line_front",
    "line_back",
    "leng_long",
    "leng_short",
    "thick",
    "class_no",
    "class_name",
    "etc_otc_name",
    "form_code_name",
    "item_eng_name",
    "edi_code",
    "updated_at",
]

_STANDARD_SHAPES: frozenset[str] = frozenset(
    {
        "원형",
        "타원형",
        "장방형",
        "반원형",
        "삼각형",
        "사각형",
        "마름모형",
        "오각형",
        "육각형",
        "팔각형",
    }
)


def parse_filter_values(raw: str | list[str] | None) -> list[str]:
    """쉼표 구분 문자열 또는 리스트에서 '전체'와 공백을 제외한 유효 필터 값 목록을 반환합니다."""
    if not raw:
        return []
    parts = raw.split(",") if isinstance(raw, str) else list(raw)
    return [p.strip() for p in parts if p and p.strip() and p.strip() != "전체"]


def _match_line_side(raw_line: str, selected: list[str]) -> bool:
    """분할선(앞 또는 뒤) 값이 선택된 조건 목록 중 하나라도 일치하는지 판별합니다."""
    val = (raw_line or "").strip()
    for opt in selected:
        if opt == "없음" and val in ("", "없음"):
            return True
        if opt == "+" and "+" in val:
            return True
        if opt == "-" and "-" in val:
            return True
        if opt == "기타" and val not in ("", "없음") and "+" not in val and "-" not in val:
            return True
    return False


def _match_form_option(form_code_name: str, chart: str, selected: list[str]) -> bool:
    """제형명 및 성상 설명이 선택된 제형 조건 중 하나라도 일치하는지 정밀 판별합니다."""
    fc = (form_code_name or "").strip()
    ch = (chart or "").strip()
    if not fc and not ch:
        return False

    for opt in selected:
        if opt == "정제":
            if ("정" in fc and "캡슐" not in fc and "필름제" not in fc and "붕해필름" not in fc) or (
                not fc and "정" in ch and "캡슐" not in ch
            ):
                return True
        elif opt == "경질캡슐":
            if "경질" in fc or "경질" in ch:
                return True
        elif opt == "연질캡슐":
            if "연질" in fc or "연질" in ch:
                return True
        elif opt == "구강붕해필름":
            if (
                "구강붕해" in fc
                or "붕해필름" in fc
                or "필름제" in fc
                or "구강붕해" in ch
                or "필름제" in ch
            ):
                return True
        elif opt in fc or opt in ch:
            return True
    return False


def matches_appearance_filters(
    rec: dict[str, Any],
    *,
    shapes: list[str] | None = None,
    colors: list[str] | None = None,
    forms: list[str] | None = None,
    line_fronts: list[str] | None = None,
    line_backs: list[str] | None = None,
    print_text: str = "",
    print_exact: bool = False,
) -> bool:
    """통합 의약품 레코드가 지정된 낱알 외형 필터 조건(AND 조합, 항목 내 OR 조합)에 부합하는지 검사합니다."""
    shapes = shapes or []
    colors = colors or []
    forms = forms or []
    line_fronts = line_fronts or []
    line_backs = line_backs or []
    pt = (print_text or "").strip()

    if not (shapes or colors or forms or line_fronts or line_backs or pt):
        return True

    has_grain_data = (
        "낱알식별" in rec.get("sources", [])
        or bool(rec.get("drugShape"))
        or bool(rec.get("colorClass1"))
        or bool(rec.get("formCodeName"))
    )
    if not has_grain_data:
        return False

    if shapes:
        drug_shape = (rec.get("drugShape") or "").strip()
        if not drug_shape:
            return False
        shape_matched = any(
            (drug_shape == "기타" or drug_shape not in _STANDARD_SHAPES)
            if s == "기타"
            else drug_shape == s
            for s in shapes
        )
        if not shape_matched:
            return False

    if colors:
        c1 = (rec.get("colorClass1") or "").strip()
        c2 = (rec.get("colorClass2") or "").strip()
        combined_color = f"{c1} {c2}".strip()
        if not combined_color or not any(c in combined_color for c in colors):
            return False

    if forms:
        if not _match_form_option(rec.get("formCodeName", ""), rec.get("chart", ""), forms):
            return False

    if line_fronts:
        if not _match_line_side(rec.get("lineFront", ""), line_fronts):
            return False

    if line_backs:
        if not _match_line_side(rec.get("lineBack", ""), line_backs):
            return False

    if pt:
        pt_low = pt.lower()
        pf = (rec.get("printFront") or "").strip().lower()
        pb = (rec.get("printBack") or "").strip().lower()
        if print_exact:
            if pf != pt_low and pb != pt_low:
                return False
        else:
            if pt_low not in pf and pt_low not in pb:
                return False

    return True


def _create_http_session() -> requests.Session:
    """멀티스레드 병렬 호출에 최적화된 커넥션 풀 기반 requests.Session 객체를 생성합니다."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) eDrugCare-Django/2.0",
            "Accept": "application/json, application/xml, text/xml, */*",
        }
    )
    retry_strategy = Retry(
        total=1,
        connect=1,
        read=0,
        status=1,
        backoff_factor=0.2,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    )
    adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


SESSION: requests.Session = _create_http_session()


def _make_cache_key(prefix: str, **kwargs: Any) -> str:
    """요청 파라미터 조합으로부터 안전한 고정 길이 캐시 키를 생성합니다."""
    serialized = json.dumps(kwargs, sort_keys=True, ensure_ascii=False)
    digest = hashlib.blake2b(serialized.encode("utf-8"), digest_size=12).hexdigest()
    return f"edrugs:{prefix}:{digest}"


def strip_html(text: Any) -> str:
    """OpenAPI 응답 내 HTML 태그(<p>, <br> 등)와 특수 공백(&nbsp;)을 깔끔한 평문으로 정제합니다."""
    if not text:
        return ""
    cleaned = _TAG_RE.sub(" ", str(text))
    cleaned = cleaned.replace("&nbsp;", " ").replace("\xa0", " ")
    cleaned = _WS_RE.sub(" ", cleaned)
    cleaned = _NEWLINE_RE.sub("\n\n", cleaned)
    return cleaned.strip()


def normalize_name(name: Any) -> str:
    """괄호 안 수출명·성분명을 제거하고 공백을 없앤 기본 품목명 정규화 문자열을 반환합니다."""
    if not name:
        return ""
    base = _PAREN_SPLIT_RE.split(str(name), maxsplit=1)[0]
    return re.sub(r"\s+", "", base).strip()


def extract_search_stem(name: Any) -> str:
    """품목명에서 괄호 부가정보를 제거한 검색용 핵심 품목명을 반환합니다."""
    if not name:
        return ""
    return _PAREN_SPLIT_RE.split(str(name), maxsplit=1)[0].strip()


def _parse_api_response(resp_text: str) -> tuple[list[dict[str, Any]], int]:
    """공공데이터포털 JSON 또는 XML 응답을 안전하게 파싱하여 (items_list, total_count)를 반환합니다."""
    if not resp_text:
        return [], 0
    text = resp_text.strip()

    if text.startswith(("{", "[")):
        try:
            data = json.loads(text)
            header = data.get("header") or data.get("response", {}).get("header") or {}
            result_code = str(header.get("resultCode") or "00").strip()
            if result_code not in {"00", "0", ""}:
                if result_code != "03":  # 03: NODATA_ERROR (정상적인 검색 결과 없음)
                    logger.warning(
                        "MFDS OpenAPI non-zero resultCode=%s msg=%s",
                        result_code,
                        header.get("resultMsg"),
                    )
                return [], 0

            body = data.get("body") or data.get("response", {}).get("body") or {}
            total_count = int(body.get("totalCount") or 0)
            raw_items = body.get("items")
            if not raw_items:
                return [], total_count

            if isinstance(raw_items, dict):
                if "item" in raw_items:
                    sub = raw_items.get("item")
                    if not sub:
                        return [], total_count
                    raw_items = sub if isinstance(sub, list) else [sub]
                else:
                    raw_items = [raw_items]
            elif not isinstance(raw_items, list):
                return [], total_count

            valid_items = [row for row in raw_items if isinstance(row, dict)]
            return valid_items, total_count
        except (ValueError, TypeError) as exc:
            logger.debug("JSON 응답 파싱 실패: %s", exc)
            return [], 0

    if text.startswith("<"):
        try:
            root = ET.fromstring(text)
            reason_code = root.findtext(".//returnReasonCode") or root.findtext(".//resultCode") or "00"
            if reason_code.strip() not in {"00", "0", ""}:
                if reason_code.strip() != "03":
                    logger.warning("MFDS XML error code=%s", reason_code.strip())
                return [], 0

            total_text = root.findtext(".//totalCount")
            total_count = int(total_text) if (total_text and total_text.isdigit()) else 0
            items: list[dict[str, Any]] = []
            for item_el in root.findall(".//item"):
                row: dict[str, Any] = {}
                for child in item_el:
                    row[child.tag] = child.text or ""
                if row:
                    items.append(row)
            return items, total_count
        except ET.ParseError as exc:
            logger.debug("XML 응답 파싱 실패: %s", exc)
            return [], 0

    return [], 0


def _pick_matching_items(
    items: list[dict[str, Any]],
    item_seq: str = "",
    item_name: str = "",
    seq_keys: tuple[str, ...] = ("ITEM_SEQ", "itemSeq"),
    name_keys: tuple[str, ...] = ("ITEM_NAME", "itemName"),
) -> list[dict[str, Any]]:
    """품목기준코드(item_seq) 또는 정규화된 품목명이 일치하는 항목을 우선 선별합니다."""
    if not items:
        return []
    if item_seq:
        exact_seq = [
            it for it in items if any(str(it.get(k) or "").strip() == item_seq for k in seq_keys)
        ]
        if exact_seq:
            return exact_seq

    target_norm = normalize_name(item_name)
    if target_norm:
        exact_name = [
            it
            for it in items
            if any(normalize_name(it.get(k)) == target_norm for k in name_keys)
        ]
        if exact_name:
            return exact_name
        partial_name = [
            it
            for it in items
            if any(target_norm in normalize_name(it.get(k)) for k in name_keys)
        ]
        if partial_name:
            return partial_name

    # item_seq만 주어졌는데 응답 항목의 코드가 전혀 다르면 잘못된 무필터 전체조회 결과이므로 버림
    if item_seq and not item_name:
        return []
    return items


def fetch_easy_drugs(
    keyword: str = "",
    search_field: str = "itemName",
    item_seq: str = "",
    page_no: int = 1,
    num_of_rows: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """
    [API 3] 식품의약품안전처_의약품개요정보(e약은요) 조회
    EndPoint: DrbEasyDrugInfoService/getDrbEasyDrugList
    """
    cache_key = _make_cache_key(
        "easy", kw=keyword, sf=search_field, seq=item_seq, p=page_no, r=num_of_rows
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = settings.MFDS_ENDPOINTS["EASY_LIST"]
    params: dict[str, Any] = {
        "serviceKey": settings.MFDS_API_KEYS["EASY"],
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "type": "json",
    }
    if item_seq:
        params["itemSeq"] = item_seq
    elif keyword:
        stem = extract_search_stem(keyword) if search_field == "itemName" else keyword
        if search_field == "efcy":
            params["efcyQesitm"] = keyword
        elif search_field == "entp":
            params["entpName"] = keyword
        else:
            params["itemName"] = stem or keyword

    try:
        resp = SESSION.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        items, total = _parse_api_response(resp.text)
        result = (items, total)
        cache.set(cache_key, result, CACHE_TTL_SECONDS)
        return result
    except requests.RequestException as exc:
        logger.warning("e약은요 API 호출 지연/실패: %s", exc)
        return [], 0


def fetch_grain_drugs(
    keyword: str = "",
    search_field: str = "item_name",
    item_seq: str = "",
    page_no: int = 1,
    num_of_rows: int = 30,
    *,
    save_cache: bool = True,
) -> tuple[list[dict[str, Any]], int]:
    """
    [API 1] 식품의약품안전처_의약품 낱알식별 정보 조회
    EndPoint: MdcinGrnIdntfcInfoService03/getMdcinGrnIdntfcInfoList03
    """
    cache_key = _make_cache_key(
        "grain", kw=keyword, sf=search_field, seq=item_seq, p=page_no, r=num_of_rows
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = settings.MFDS_ENDPOINTS["GRAIN_LIST"]
    params: dict[str, Any] = {
        "serviceKey": settings.MFDS_API_KEYS["GRAIN"],
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "type": "json",
    }
    # 낱알식별 API는 item_name 인덱스가 훨씬 빠르므로 품목명이 있으면 우선 활용합니다.
    if keyword:
        if search_field == "entp":
            params["entp_name"] = keyword
        else:
            params["item_name"] = extract_search_stem(keyword) or keyword
    elif item_seq:
        params["item_seq"] = item_seq

    try:
        resp = SESSION.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        items, total = _parse_api_response(resp.text)
        if items and save_cache:
            save_grain_items_to_cache(items)
        result = (items, total)
        cache.set(cache_key, result, CACHE_TTL_SECONDS)
        return result
    except requests.RequestException as exc:
        logger.warning("낱알식별 API 호출 지연/실패: %s", exc)
        return [], 0


def fetch_prmsn_list(
    keyword: str = "",
    search_field: str = "item_name",
    item_seq: str = "",
    spclty_pblc: str = "",
    page_no: int = 1,
    num_of_rows: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """
    [API 2-1] 식품의약품안전처_의약품 제품 허가정보 (목록 조회)
    EndPoint: DrugPrdtPrmsnInfoService08/getDrugPrdtPrmsnInq08
    """
    cache_key = _make_cache_key(
        "prmsn_list",
        kw=keyword,
        sf=search_field,
        seq=item_seq,
        sp=spclty_pblc,
        p=page_no,
        r=num_of_rows,
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = settings.MFDS_ENDPOINTS["PRMSN_LIST"]
    params: dict[str, Any] = {
        "serviceKey": settings.MFDS_API_KEYS["PERMISSION"],
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "type": "json",
    }
    if keyword:
        if search_field == "entp":
            params["entp_name"] = keyword
        else:
            params["item_name"] = extract_search_stem(keyword) or keyword
    elif item_seq:
        params["item_seq"] = item_seq

    if spclty_pblc:
        params["spclty_pblc"] = spclty_pblc

    try:
        resp = SESSION.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        items, total = _parse_api_response(resp.text)
        result = (items, total)
        cache.set(cache_key, result, CACHE_TTL_SECONDS)
        return result
    except requests.RequestException as exc:
        logger.warning("제품허가 목록 API 호출 지연/실패: %s", exc)
        return [], 0


def fetch_prmsn_detail(
    item_seq: str = "",
    item_name: str = "",
    page_no: int = 1,
    num_of_rows: int = 3,
) -> tuple[list[dict[str, Any]], int]:
    """
    [API 2-2] 식품의약품안전처_의약품 제품 허가정보 (상세 조회)
    EndPoint: DrugPrdtPrmsnInfoService08/getDrugPrdtPrmsnDtlInq08
    """
    if not item_seq and not item_name:
        return [], 0

    cache_key = _make_cache_key("prmsn_dtl", seq=item_seq, nm=item_name, p=page_no, r=num_of_rows)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = settings.MFDS_ENDPOINTS["PRMSN_DETAIL"]
    params: dict[str, Any] = {
        "serviceKey": settings.MFDS_API_KEYS["PERMISSION"],
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "type": "json",
    }
    if item_name:
        params["item_name"] = extract_search_stem(item_name) or item_name
    if item_seq:
        params["item_seq"] = item_seq

    try:
        resp = SESSION.get(url, params=params, timeout=DETAIL_TIMEOUT)
        items, total = _parse_api_response(resp.text)
        matched = _pick_matching_items(items, item_seq=item_seq, item_name=item_name)
        result = (matched, total)
        cache.set(cache_key, result, CACHE_TTL_SECONDS)
        return result
    except requests.RequestException as exc:
        logger.debug("제품허가 상세 API 타임아웃/생략 (기본 허가목록 정보로 대체): %s", exc)
        return [], 0


def save_grain_items_to_cache(items: list[dict[str, Any]]) -> int:
    """
    조회된 낱알식별 API 데이터를 SQLite PillCache 테이블에 고속 일괄 Upsert(bulk_create)합니다.
    기존 건별 update_or_create 루프(N+1 쿼리) 대비 단일 트랜잭션 쿼리로 처리되어 속도와 동시성이 대폭 향상됩니다.
    """
    if not items:
        return 0

    now = timezone.now()
    dedup_records: dict[str, PillCache] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        seq = str(raw.get("ITEM_SEQ") or "").strip()
        if not seq:
            continue
        dedup_records[seq] = PillCache(
            item_seq=seq,
            item_name=str(raw.get("ITEM_NAME") or "").strip(),
            entp_name=str(raw.get("ENTP_NAME") or "").strip(),
            chart=str(raw.get("CHART") or "").strip(),
            item_image=str(raw.get("ITEM_IMAGE") or "").strip(),
            print_front=str(raw.get("PRINT_FRONT") or "").strip(),
            print_back=str(raw.get("PRINT_BACK") or "").strip(),
            drug_shape=str(raw.get("DRUG_SHAPE") or "").strip(),
            color_class1=str(raw.get("COLOR_CLASS1") or "").strip(),
            color_class2=str(raw.get("COLOR_CLASS2") or "").strip(),
            line_front=str(raw.get("LINE_FRONT") or "").strip(),
            line_back=str(raw.get("LINE_BACK") or "").strip(),
            leng_long=str(raw.get("LENG_LONG") or "").strip(),
            leng_short=str(raw.get("LENG_SHORT") or "").strip(),
            thick=str(raw.get("THICK") or "").strip(),
            class_no=str(raw.get("CLASS_NO") or "").strip(),
            class_name=str(raw.get("CLASS_NAME") or "").strip(),
            etc_otc_name=str(raw.get("ETC_OTC_NAME") or "").strip(),
            form_code_name=str(raw.get("FORM_CODE_NAME") or "").strip(),
            item_eng_name=str(raw.get("ITEM_ENG_NAME") or "").strip(),
            edi_code=str(raw.get("EDI_CODE") or "").strip(),
            updated_at=now,
        )

    if not dedup_records:
        return 0

    records_list = list(dedup_records.values())
    try:
        PillCache.objects.bulk_create(
            records_list,
            update_conflicts=True,
            unique_fields=["item_seq"],
            update_fields=_PILL_CACHE_UPDATE_FIELDS,
        )
        return len(records_list)
    except Exception as exc:
        logger.warning("PillCache 일괄 저장 중 예외 발생: %s", exc)
        return 0


def unified_drug_search(
    keyword: str = "",
    search_field: str = "itemName",
    page_no: int = 1,
    num_of_rows: int = 60,
    *,
    shapes: list[str] | None = None,
    colors: list[str] | None = None,
    forms: list[str] | None = None,
    line_fronts: list[str] | None = None,
    line_backs: list[str] | None = None,
    print_text: str = "",
    print_exact: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """
    식약처 3대 OpenAPI(e약은요 + 낱알식별 + 제품허가정보) 및 낱알 외형 필터를 결합하여
    품목기준코드(ITEM_SEQ) 및 정규화 품목명 기준으로 병합(Merge)된 통합 카드 리스트를 반환합니다.
    검색어가 없더라도 외형 조건이 지정되어 있으면 외형 일치 결과를 반환합니다.
    """
    shapes = shapes or []
    colors = colors or []
    forms = forms or []
    line_fronts = line_fronts or []
    line_backs = line_backs or []
    pt = (print_text or "").strip()
    has_appearance_filter = bool(shapes or colors or forms or line_fronts or line_backs or pt)
    kw = (keyword or "").strip()

    # 검색어 없이 낱알 외형 조건만으로 검색한 경우
    if not kw and has_appearance_filter:
        items, total_matched = search_pills_by_appearance(
            shape=",".join(shapes),
            color=",".join(colors),
            form_name=",".join(forms),
            line_front=",".join(line_fronts),
            line_back=",".join(line_backs),
            print_text=pt,
            print_exact=print_exact,
        )
        counts = {
            "easyTotal": 0,
            "grainTotal": total_matched,
            "prmsnTotal": 0,
            "mergedCount": len(items),
        }
        return items, counts

    with ThreadPoolExecutor(max_workers=3) as executor:
        fut_easy = executor.submit(fetch_easy_drugs, kw, search_field, "", page_no, num_of_rows)
        if search_field == "efcy":
            fut_grain = None
            fut_prmsn = None
        else:
            grain_field = "entp" if search_field == "entp" else "item_name"
            fut_grain = executor.submit(
                fetch_grain_drugs, kw, grain_field, "", page_no, num_of_rows, save_cache=False
            )
            fut_prmsn = executor.submit(
                fetch_prmsn_list, kw, grain_field, "", "", page_no, num_of_rows
            )

        easy_items, easy_total = fut_easy.result()
        grain_items, grain_total = fut_grain.result() if fut_grain else ([], 0)
        prmsn_items, prmsn_total = fut_prmsn.result() if fut_prmsn else ([], 0)

    # 증상(efcy) 검색인 경우 상위 품목의 대표 이름으로 외형/허가 정보를 보조 조회
    if search_field == "efcy" and easy_items:
        first_name = normalize_name(easy_items[0].get("itemName", ""))[:6]
        if first_name:
            with ThreadPoolExecutor(max_workers=2) as ex2:
                f_g = ex2.submit(fetch_grain_drugs, first_name, "item_name", "", 1, 10, save_cache=False)
                f_p = ex2.submit(fetch_prmsn_list, first_name, "item_name", "", "", 1, 10)
                grain_items, _ = f_g.result()
                prmsn_items, _ = f_p.result()

    # 워커 스레드 외부(메인 스레드)에서 안전하게 일괄 DB 인덱싱 수행
    if grain_items:
        save_grain_items_to_cache(grain_items)

    merged_map: dict[str, dict[str, Any]] = {}
    name_to_seq: dict[str, str] = {}

    def get_or_create_record(seq: Any, name: Any, entp: Any) -> dict[str, Any]:
        seq_str = str(seq or "").strip()
        norm = normalize_name(name)
        if not seq_str and norm in name_to_seq:
            seq_str = name_to_seq[norm]
        if not seq_str:
            seq_str = f"NAME_{norm}"
        if norm and seq_str and not seq_str.startswith("NAME_"):
            name_to_seq[norm] = seq_str

        if seq_str not in merged_map:
            merged_map[seq_str] = {
                "itemSeq": "" if seq_str.startswith("NAME_") else seq_str,
                "itemName": str(name or "").strip(),
                "itemEngName": "",
                "entpName": str(entp or "").strip(),
                "itemImage": "",
                "etcOtcName": "",
                "className": "",
                "itemIngrName": "",
                "itemPermitDate": "",
                "ediCode": "",
                # e약은요 (DrbEasyDrugInfoService)
                "efcyQesitm": "",
                "useMethodQesitm": "",
                "atpnWarnQesitm": "",
                "atpnQesitm": "",
                "intrcQesitm": "",
                "seQesitm": "",
                "depositMethodQesitm": "",
                # 낱알식별 (MdcinGrnIdntfcInfoService03)
                "chart": "",
                "drugShape": "",
                "colorClass1": "",
                "colorClass2": "",
                "printFront": "",
                "printBack": "",
                "lineFront": "",
                "lineBack": "",
                "lengLong": "",
                "lengShort": "",
                "thick": "",
                "formCodeName": "",
                # 허가정보 상세 (DrugPrdtPrmsnInfoService08)
                "validTerm": "",
                "storageMethod": "",
                "barCode": "",
                "sources": [],
            }
        return merged_map[seq_str]

    # 1) e약은요 병합
    for item in easy_items:
        rec = get_or_create_record(item.get("itemSeq"), item.get("itemName"), item.get("entpName"))
        if "e약은요" not in rec["sources"]:
            rec["sources"].append("e약은요")
        if item.get("itemImage") and not rec["itemImage"]:
            rec["itemImage"] = item.get("itemImage")
        rec["efcyQesitm"] = strip_html(item.get("efcyQesitm"))
        rec["useMethodQesitm"] = strip_html(item.get("useMethodQesitm"))
        rec["atpnWarnQesitm"] = strip_html(item.get("atpnWarnQesitm"))
        rec["atpnQesitm"] = strip_html(item.get("atpnQesitm"))
        rec["intrcQesitm"] = strip_html(item.get("intrcQesitm"))
        rec["seQesitm"] = strip_html(item.get("seQesitm"))
        rec["depositMethodQesitm"] = strip_html(item.get("depositMethodQesitm"))

    # 2) 낱알식별 정보 병합
    for item in grain_items:
        rec = get_or_create_record(item.get("ITEM_SEQ"), item.get("ITEM_NAME"), item.get("ENTP_NAME"))
        if "낱알식별" not in rec["sources"]:
            rec["sources"].append("낱알식별")
        if item.get("ITEM_IMAGE") and not rec["itemImage"]:
            rec["itemImage"] = item.get("ITEM_IMAGE")
        rec["chart"] = item.get("CHART") or rec["chart"]
        rec["drugShape"] = item.get("DRUG_SHAPE") or rec["drugShape"]
        rec["colorClass1"] = item.get("COLOR_CLASS1") or rec["colorClass1"]
        rec["colorClass2"] = item.get("COLOR_CLASS2") or rec["colorClass2"]
        rec["printFront"] = item.get("PRINT_FRONT") or rec["printFront"]
        rec["printBack"] = item.get("PRINT_BACK") or rec["printBack"]
        rec["lineFront"] = item.get("LINE_FRONT") or rec["lineFront"]
        rec["lineBack"] = item.get("LINE_BACK") or rec["lineBack"]
        rec["lengLong"] = item.get("LENG_LONG") or rec["lengLong"]
        rec["lengShort"] = item.get("LENG_SHORT") or rec["lengShort"]
        rec["thick"] = item.get("THICK") or rec["thick"]
        rec["formCodeName"] = item.get("FORM_CODE_NAME") or rec["formCodeName"]
        rec["className"] = item.get("CLASS_NAME") or rec["className"]
        rec["etcOtcName"] = item.get("ETC_OTC_NAME") or rec["etcOtcName"]
        rec["itemEngName"] = item.get("ITEM_ENG_NAME") or rec["itemEngName"]
        rec["ediCode"] = item.get("EDI_CODE") or rec["ediCode"]

    # 3) 제품 허가정보 병합
    for item in prmsn_items:
        rec = get_or_create_record(item.get("ITEM_SEQ"), item.get("ITEM_NAME"), item.get("ENTP_NAME"))
        if "허가정보" not in rec["sources"]:
            rec["sources"].append("허가정보")
        if item.get("BIG_PRDT_IMG_URL") and not rec["itemImage"]:
            rec["itemImage"] = item.get("BIG_PRDT_IMG_URL")
        rec["itemEngName"] = item.get("ITEM_ENG_NAME") or rec["itemEngName"]
        rec["etcOtcName"] = item.get("SPCLTY_PBLC") or rec["etcOtcName"]
        rec["className"] = item.get("PRDUCT_TYPE") or rec["className"]
        rec["itemIngrName"] = item.get("ITEM_INGR_NAME") or rec["itemIngrName"]
        rec["itemPermitDate"] = item.get("ITEM_PERMIT_DATE") or rec["itemPermitDate"]
        rec["ediCode"] = item.get("EDI_CODE") or rec["ediCode"]

    # 4) 로컬 SQLite PillCache 보강 및 공공데이터 서버 지연 시 로컬 캐시 폴백 병합
    local_filter = Q()
    seq_list = [r["itemSeq"] for r in merged_map.values() if r["itemSeq"]]
    if seq_list:
        local_filter |= Q(item_seq__in=seq_list)
    if kw:
        if search_field == "entp":
            local_filter |= Q(entp_name__icontains=kw)
        elif search_field == "efcy":
            local_filter |= Q(class_name__icontains=kw)
        else:
            local_filter |= Q(item_name__icontains=kw)

    if local_filter:
        for p in PillCache.objects.filter(local_filter)[:100]:
            rec = get_or_create_record(p.item_seq, p.item_name, p.entp_name)
            if "낱알식별" not in rec["sources"]:
                rec["sources"].append("낱알식별")
            rec["itemImage"] = rec["itemImage"] or p.item_image
            rec["chart"] = rec["chart"] or p.chart
            rec["drugShape"] = rec["drugShape"] or p.drug_shape
            rec["colorClass1"] = rec["colorClass1"] or p.color_class1
            rec["colorClass2"] = rec["colorClass2"] or p.color_class2
            rec["printFront"] = rec["printFront"] or p.print_front
            rec["printBack"] = rec["printBack"] or p.print_back
            rec["lineFront"] = rec["lineFront"] or p.line_front
            rec["lineBack"] = rec["lineBack"] or p.line_back
            rec["lengLong"] = rec["lengLong"] or p.leng_long
            rec["lengShort"] = rec["lengShort"] or p.leng_short
            rec["thick"] = rec["thick"] or p.thick
            rec["formCodeName"] = rec["formCodeName"] or p.form_code_name
            rec["etcOtcName"] = rec["etcOtcName"] or p.etc_otc_name
            rec["className"] = rec["className"] or p.class_name
            rec["itemEngName"] = rec["itemEngName"] or p.item_eng_name
            rec["ediCode"] = rec["ediCode"] or p.edi_code

    results = list(merged_map.values())
    if has_appearance_filter:
        results = [
            r
            for r in results
            if matches_appearance_filters(
                r,
                shapes=shapes,
                colors=colors,
                forms=forms,
                line_fronts=line_fronts,
                line_backs=line_backs,
                print_text=pt,
                print_exact=print_exact,
            )
        ]

    # 다중 API 매칭도 -> 이미지 보유 -> 복약안내 보유 순으로 정렬
    results.sort(
        key=lambda x: (len(x["sources"]), 1 if x["itemImage"] else 0, 1 if x["efcyQesitm"] else 0),
        reverse=True,
    )

    if has_appearance_filter:
        counts = {
            "easyTotal": sum(1 for r in results if "e약은요" in r["sources"]),
            "grainTotal": sum(1 for r in results if "낱알식별" in r["sources"]),
            "prmsnTotal": sum(1 for r in results if "허가정보" in r["sources"]),
            "mergedCount": len(results),
        }
    else:
        counts = {
            "easyTotal": easy_total,
            "grainTotal": grain_total,
            "prmsnTotal": prmsn_total,
            "mergedCount": len(results),
        }
    return results, counts


def enrich_single_drug_detail(item_seq: str = "", item_name: str = "") -> dict[str, Any]:
    """
    특정 의약품 카드 클릭 시 로컬 SQLite 캐시 및 3대 OpenAPI를 고속 교차 조회하여
    누락 없는 통합 상세 스펙을 반환합니다.
    """
    cache_key = _make_cache_key("drug_detail", seq=item_seq, nm=item_name)
    cached_detail = cache.get(cache_key)
    if cached_detail is not None:
        return cached_detail

    # 1) 로컬 SQLite PillCache 우선 확인 (이미 인덱싱된 약이면 낱알 API 네트워크 호출 생략)
    cached_pill: PillCache | None = None
    if item_seq:
        cached_pill = PillCache.objects.filter(item_seq=item_seq).first()
    if not cached_pill and item_name:
        cached_pill = PillCache.objects.filter(item_name=item_name).first()

    effective_name = item_name or (cached_pill.item_name if cached_pill else "")
    effective_seq = item_seq or (cached_pill.item_seq if cached_pill else "")

    with ThreadPoolExecutor(max_workers=4) as executor:
        f_easy = executor.submit(fetch_easy_drugs, effective_name, "itemName", effective_seq, 1, 5)
        f_grain = (
            None
            if cached_pill is not None
            else executor.submit(
                fetch_grain_drugs, effective_name, "item_name", effective_seq, 1, 10, save_cache=False
            )
        )
        f_prmsn = executor.submit(fetch_prmsn_list, effective_name, "item_name", effective_seq, "", 1, 10)
        f_dtl = executor.submit(fetch_prmsn_detail, effective_seq, effective_name, 1, 3)

        raw_easy, _ = f_easy.result()
        raw_grain, _ = f_grain.result() if f_grain else ([], 0)
        raw_prmsn, _ = f_prmsn.result()
        dtl_items, _ = f_dtl.result()

    if raw_grain:
        save_grain_items_to_cache(raw_grain)

    easy_items = _pick_matching_items(raw_easy, item_seq=effective_seq, item_name=effective_name)
    grain_items = _pick_matching_items(raw_grain, item_seq=effective_seq, item_name=effective_name)
    prmsn_items = _pick_matching_items(raw_prmsn, item_seq=effective_seq, item_name=effective_name)

    detail: dict[str, Any] = {
        "itemSeq": effective_seq,
        "itemName": effective_name,
        "itemEngName": "",
        "entpName": "",
        "itemImage": "",
        "etcOtcName": "",
        "className": "",
        "itemIngrName": "",
        "materialName": "",
        "itemPermitDate": "",
        "validTerm": "",
        "storageMethod": "",
        "packUnit": "",
        "barCode": "",
        "atcCode": "",
        "ediCode": "",
        "chart": "",
        "drugShape": "",
        "colorClass1": "",
        "colorClass2": "",
        "printFront": "",
        "printBack": "",
        "lineFront": "",
        "lineBack": "",
        "lengLong": "",
        "lengShort": "",
        "thick": "",
        "formCodeName": "",
        "efcyQesitm": "",
        "useMethodQesitm": "",
        "atpnWarnQesitm": "",
        "atpnQesitm": "",
        "intrcQesitm": "",
        "seQesitm": "",
        "depositMethodQesitm": "",
        "eeDocId": "",
        "udDocId": "",
        "nbDocId": "",
        "sources": [],
    }

    if easy_items:
        e = easy_items[0]
        detail["sources"].append("e약은요")
        detail["itemSeq"] = detail["itemSeq"] or e.get("itemSeq") or ""
        detail["itemName"] = detail["itemName"] or e.get("itemName") or ""
        detail["entpName"] = detail["entpName"] or e.get("entpName") or ""
        detail["itemImage"] = detail["itemImage"] or e.get("itemImage") or ""
        detail["efcyQesitm"] = strip_html(e.get("efcyQesitm"))
        detail["useMethodQesitm"] = strip_html(e.get("useMethodQesitm"))
        detail["atpnWarnQesitm"] = strip_html(e.get("atpnWarnQesitm"))
        detail["atpnQesitm"] = strip_html(e.get("atpnQesitm"))
        detail["intrcQesitm"] = strip_html(e.get("intrcQesitm"))
        detail["seQesitm"] = strip_html(e.get("seQesitm"))
        detail["depositMethodQesitm"] = strip_html(e.get("depositMethodQesitm"))

    if cached_pill is not None:
        if "낱알식별" not in detail["sources"]:
            detail["sources"].append("낱알식별")
        detail["itemSeq"] = detail["itemSeq"] or cached_pill.item_seq
        detail["itemName"] = detail["itemName"] or cached_pill.item_name
        detail["entpName"] = detail["entpName"] or cached_pill.entp_name
        detail["itemImage"] = detail["itemImage"] or cached_pill.item_image
        detail["chart"] = cached_pill.chart
        detail["drugShape"] = cached_pill.drug_shape
        detail["colorClass1"] = cached_pill.color_class1
        detail["colorClass2"] = cached_pill.color_class2
        detail["printFront"] = cached_pill.print_front
        detail["printBack"] = cached_pill.print_back
        detail["lineFront"] = cached_pill.line_front
        detail["lineBack"] = cached_pill.line_back
        detail["lengLong"] = cached_pill.leng_long
        detail["lengShort"] = cached_pill.leng_short
        detail["thick"] = cached_pill.thick
        detail["formCodeName"] = cached_pill.form_code_name
        detail["className"] = cached_pill.class_name or detail["className"]
        detail["etcOtcName"] = cached_pill.etc_otc_name or detail["etcOtcName"]
        detail["itemEngName"] = cached_pill.item_eng_name or detail["itemEngName"]
        detail["ediCode"] = cached_pill.edi_code or detail["ediCode"]
    elif grain_items:
        g = grain_items[0]
        detail["sources"].append("낱알식별")
        detail["itemSeq"] = detail["itemSeq"] or g.get("ITEM_SEQ") or ""
        detail["itemName"] = detail["itemName"] or g.get("ITEM_NAME") or ""
        detail["entpName"] = detail["entpName"] or g.get("ENTP_NAME") or ""
        detail["itemImage"] = detail["itemImage"] or g.get("ITEM_IMAGE") or ""
        detail["chart"] = g.get("CHART") or ""
        detail["drugShape"] = g.get("DRUG_SHAPE") or ""
        detail["colorClass1"] = g.get("COLOR_CLASS1") or ""
        detail["colorClass2"] = g.get("COLOR_CLASS2") or ""
        detail["printFront"] = g.get("PRINT_FRONT") or ""
        detail["printBack"] = g.get("PRINT_BACK") or ""
        detail["lineFront"] = g.get("LINE_FRONT") or ""
        detail["lineBack"] = g.get("LINE_BACK") or ""
        detail["lengLong"] = g.get("LENG_LONG") or ""
        detail["lengShort"] = g.get("LENG_SHORT") or ""
        detail["thick"] = g.get("THICK") or ""
        detail["formCodeName"] = g.get("FORM_CODE_NAME") or ""
        detail["className"] = g.get("CLASS_NAME") or detail["className"]
        detail["etcOtcName"] = g.get("ETC_OTC_NAME") or detail["etcOtcName"]
        detail["itemEngName"] = g.get("ITEM_ENG_NAME") or detail["itemEngName"]
        detail["ediCode"] = g.get("EDI_CODE") or detail["ediCode"]

    if prmsn_items:
        p = prmsn_items[0]
        if "허가정보" not in detail["sources"]:
            detail["sources"].append("허가정보")
        detail["itemSeq"] = detail["itemSeq"] or p.get("ITEM_SEQ") or ""
        detail["itemName"] = detail["itemName"] or p.get("ITEM_NAME") or ""
        detail["entpName"] = detail["entpName"] or p.get("ENTP_NAME") or ""
        detail["itemEngName"] = detail["itemEngName"] or p.get("ITEM_ENG_NAME") or ""
        detail["itemImage"] = detail["itemImage"] or p.get("BIG_PRDT_IMG_URL") or ""
        detail["etcOtcName"] = detail["etcOtcName"] or p.get("SPCLTY_PBLC") or ""
        detail["className"] = detail["className"] or p.get("PRDUCT_TYPE") or ""
        detail["itemIngrName"] = detail["itemIngrName"] or p.get("ITEM_INGR_NAME") or ""
        detail["itemPermitDate"] = detail["itemPermitDate"] or p.get("ITEM_PERMIT_DATE") or ""
        detail["ediCode"] = detail["ediCode"] or p.get("EDI_CODE") or ""

    if dtl_items:
        d = dtl_items[0]
        if "허가정보" not in detail["sources"]:
            detail["sources"].append("허가정보")
        detail["etcOtcName"] = detail["etcOtcName"] or d.get("ETC_OTC_CODE") or ""
        detail["chart"] = detail["chart"] or d.get("CHART") or ""
        detail["barCode"] = d.get("BAR_CODE") or ""
        detail["materialName"] = d.get("MATERIAL_NAME") or ""
        detail["storageMethod"] = d.get("STORAGE_METHOD") or ""
        detail["validTerm"] = d.get("VALID_TERM") or ""
        detail["packUnit"] = d.get("PACK_UNIT") or ""
        detail["itemIngrName"] = detail["itemIngrName"] or d.get("MAIN_ITEM_INGR") or d.get("INGR_NAME") or ""
        detail["atcCode"] = d.get("ATC_CODE") or ""
        detail["eeDocId"] = d.get("EE_DOC_ID") or ""
        detail["udDocId"] = d.get("UD_DOC_ID") or ""
        detail["nbDocId"] = d.get("NB_DOC_ID") or ""
        if not detail["efcyQesitm"] and d.get("EE_DOC_DATA"):
            detail["efcyQesitm"] = strip_html(d.get("EE_DOC_DATA"))[:1000]
        if not detail["useMethodQesitm"] and d.get("UD_DOC_DATA"):
            detail["useMethodQesitm"] = strip_html(d.get("UD_DOC_DATA"))[:1000]
        if not detail["atpnQesitm"] and d.get("NB_DOC_DATA"):
            detail["atpnQesitm"] = strip_html(d.get("NB_DOC_DATA"))[:1000]

    cache.set(cache_key, detail, CACHE_TTL_SECONDS)
    return detail


def search_pills_by_appearance(
    shape: str = "",
    color: str = "",
    form_name: str = "",
    line: str = "",
    print_text: str = "",
    keyword: str = "",
    *,
    line_front: str = "",
    line_back: str = "",
    print_exact: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """
    스마트 낱알 식별기:
    1) 캐시 데이터가 부족하면 초기 다빈도 상비약·처방약 배치 데이터를 고속 병렬 로드
    2) 키워드(품목명/제조사)가 있으면 실시간 식약처 낱알식별 API도 함께 호출하여 SQLite 캐시에 즉시 반영
    3) 다중 선택 모양·색상·제형·분할선(앞/뒤)·식별문자(포함/일치)·키워드로 정밀 필터링하여 반환
    """
    if PillCache.objects.count() == 0:
        seed_initial_pill_cache()

    kw = (keyword or "").strip()
    if kw:
        fetch_grain_drugs(keyword=kw, search_field="item_name", page_no=1, num_of_rows=60, save_cache=True)

    shapes = parse_filter_values(shape)
    colors = parse_filter_values(color)
    forms = parse_filter_values(form_name)
    line_fronts = parse_filter_values(line_front)
    line_backs = parse_filter_values(line_back)
    legacy_lines = parse_filter_values(line)

    qs = PillCache.objects.all()
    if kw:
        qs = qs.filter(
            Q(item_name__icontains=kw) | Q(entp_name__icontains=kw) | Q(class_name__icontains=kw)
        )

    matched_items: list[dict[str, Any]] = []
    for p in qs:
        rec = {
            "itemSeq": p.item_seq,
            "itemName": p.item_name,
            "entpName": p.entp_name,
            "chart": p.chart,
            "itemImage": p.item_image,
            "printFront": p.print_front,
            "printBack": p.print_back,
            "drugShape": p.drug_shape,
            "colorClass1": p.color_class1,
            "colorClass2": p.color_class2,
            "lineFront": p.line_front,
            "lineBack": p.line_back,
            "lengLong": p.leng_long,
            "lengShort": p.leng_short,
            "thick": p.thick,
            "className": p.class_name,
            "etcOtcName": p.etc_otc_name,
            "formCodeName": p.form_code_name,
            "itemEngName": p.item_eng_name,
            "ediCode": p.edi_code,
            "sources": ["낱알식별"],
        }
        if not matches_appearance_filters(
            rec,
            shapes=shapes,
            colors=colors,
            forms=forms,
            line_fronts=line_fronts,
            line_backs=line_backs,
            print_text=print_text,
            print_exact=print_exact,
        ):
            continue
        if legacy_lines and not line_fronts and not line_backs:
            if not (
                _match_line_side(p.line_front, legacy_lines)
                or _match_line_side(p.line_back, legacy_lines)
            ):
                continue
        matched_items.append(rec)

    matched_items.sort(key=lambda x: (0 if x["itemImage"] else 1, x["itemName"]))
    total_matched = len(matched_items)
    return matched_items[:500], total_matched


def seed_initial_pill_cache() -> int:
    """
    최초 실행 시 식약처 낱알식별 API에서 다빈도 상비약 및 일반/전문의약품 샘플을
    멀티스레드로 수집한 뒤 메인 스레드에서 단일 bulk_create 트랜잭션으로 SQLite에 적재합니다.
    """
    popular_keywords = ["타이레놀", "게보린", "아스피린", "베아제", "탁센", "이지엔", "노바스크", "리피토"]
    collected_items: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(fetch_grain_drugs, "", "item_name", "", page, 100, save_cache=False)
            for page in range(1, 11)
        ] + [
            executor.submit(fetch_grain_drugs, kw, "item_name", "", 1, 30, save_cache=False)
            for kw in popular_keywords
        ]
        for fut in futures:
            items, _ = fut.result()
            if items:
                collected_items.extend(items)

    return save_grain_items_to_cache(collected_items)
