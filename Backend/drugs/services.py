"""
[역할] 식약처 3대 공공데이터 병렬 호출, XML/JSON/CDATA 파싱, 데이터 병합 및 SQLite(PillCache) 인덱싱 서비스 계층
[경로] Backend/drugs/views.py -> Backend/drugs/services.py -> 식약처 OpenAPI 3종 & Backend/drugs/models.py (PillCache)
[수정] 외부 API 응답 대기 한도를 조정하려면 DEFAULT_TIMEOUT / DETAIL_TIMEOUT 상수를 변경하세요.
"""
from __future__ import annotations

import atexit
import hashlib
import html
import json
import logging
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Final
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import PillCache

logger = logging.getLogger(__name__)

_CDATA_RE: Final[re.Pattern[str]] = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)
_ARTICLE_TITLE_RE: Final[re.Pattern[str]] = re.compile(
    r'<(?:SECTION|ARTICLE)\b[^>]*?\btitle="([^"]+)"[^>]*?>', re.IGNORECASE
)
_TAG_RE: Final[re.Pattern[str]] = re.compile(r"<[^>]*>")
_INGR_CODE_RE: Final[re.Pattern[str]] = re.compile(r"\[[A-Za-z0-9_\-]+\]")
_WS_RE: Final[re.Pattern[str]] = re.compile(r"[ \t]+")
_ALL_WS_RE: Final[re.Pattern[str]] = re.compile(r"\s+")
_NEWLINE_RE: Final[re.Pattern[str]] = re.compile(r"\n{3,}")
_PAREN_SPLIT_RE: Final[re.Pattern[str]] = re.compile(r"[\(\[]")
_INGR_SPLIT_RE: Final[re.Pattern[str]] = re.compile(r"[|/,;]+")

DEFAULT_TIMEOUT: Final[tuple[float, float]] = (3.5, 8.0)
DETAIL_TIMEOUT: Final[tuple[float, float]] = (3.0, 5.5)
CACHE_TTL_SECONDS: Final[int] = 600

_PILL_CACHE_UPDATE_FIELDS: Final[list[str]] = [
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

_PILL_VALUES_FIELDS: Final[tuple[str, ...]] = (
    "item_seq",
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
    "class_name",
    "etc_otc_name",
    "form_code_name",
    "item_eng_name",
    "edi_code",
)

_STANDARD_SHAPES: Final[frozenset[str]] = frozenset(
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


def _create_http_session() -> requests.Session:
    """
    [역할] 커넥션 풀(HTTPAdapter)과 재시도 정책이 적용된 공용 requests.Session을 생성합니다.
    [경로] 모듈 초기화 -> SESSION -> fetch_easy_drugs / fetch_grain_drugs / fetch_prmsn_*
    [수정] 동시 연결 풀 크기를 늘리려면 pool_maxsize 값을 조정하세요.
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) eDrugCare-Django/3.0",
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
    adapter = HTTPAdapter(pool_connections=12, pool_maxsize=24, max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


SESSION: Final[requests.Session] = _create_http_session()
_API_EXECUTOR: Final[ThreadPoolExecutor] = ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="mfds-api"
)
atexit.register(_API_EXECUTOR.shutdown, wait=False)


def sanitize_http_url(raw_url: Any, max_len: int = 500) -> str:
    """
    [역할] 외부 이미지 URL에서 javascript:/data: 등 위험 스킴을 차단하고 http/https 주소만 반환합니다.
    [경로] OpenAPI 응답 및 클라이언트 입력 -> sanitize_http_url() -> DB 저장 및 JSON 응답
    [수정] https만 허용하려면 허용 스킴 집합을 {"https"}로 좁히세요 (단, 일부 식약처 이미지는 http 사용).
    """
    if raw_url is None:
        return ""
    candidate = str(raw_url).strip()[:max_len]
    if not candidate:
        return ""
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return ""
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return ""
    return candidate


def parse_filter_values(raw: str | list[str] | None) -> list[str]:
    """
    [역할] 쉼표 구분 문자열 또는 리스트에서 공백과 '전체'를 제외한 유효 필터 목록을 추출합니다.
    [경로] views.py (api_unified_search) -> parse_filter_values() -> unified_drug_search()
    [수정] 구분자를 추가하려면 split 전에 치환식을 추가하세요.
    """
    if not raw:
        return []
    parts = raw.split(",") if isinstance(raw, str) else list(raw)
    return [p.strip() for p in parts if p and p.strip() and p.strip() != "전체"]


def _match_line_side(raw_line: str, selected: list[str]) -> bool:
    """
    [역할] 알약 앞/뒤 분할선 값이 선택 조건(없음, +, -, 기타) 중 하나와 일치하는지 검사합니다.
    [경로] matches_appearance_filters() -> _match_line_side() -> bool 반환
    [수정] 새로운 분할선 기호 옵션을 추가할 경우 match 분기를 확장하세요.
    """
    val = (raw_line or "").strip()
    for opt in selected:
        match opt:
            case "없음" if val in ("", "없음"):
                return True
            case "+" if "+" in val:
                return True
            case "-" if "-" in val:
                return True
            case "기타" if val not in ("", "없음") and "+" not in val and "-" not in val:
                return True
    return False


def _match_form_option(form_code_name: str, chart: str, selected: list[str]) -> bool:
    """
    [역할] 제형명(form_code_name)과 성상(chart)을 대조하여 정제·경질캡슐·연질캡슐·구강붕해필름 여부를 판별합니다.
    [경로] matches_appearance_filters() -> _match_form_option() -> bool 반환
    [수정] 츄어블정·서방정 등 세부 제형 필터를 추가하려면 case 분기를 추가하세요.
    """
    fc = (form_code_name or "").strip()
    ch = (chart or "").strip()
    if not fc and not ch:
        return False

    for opt in selected:
        match opt:
            case "정제":
                if (
                    "정" in fc
                    and "캡슐" not in fc
                    and "필름제" not in fc
                    and "붕해필름" not in fc
                ) or (not fc and "정" in ch and "캡슐" not in ch):
                    return True
            case "경질캡슐":
                if "경질" in fc or "경질" in ch:
                    return True
            case "연질캡슐":
                if "연질" in fc or "연질" in ch:
                    return True
            case "구강붕해필름":
                if any(k in fc or k in ch for k in ("구강붕해", "붕해필름", "필름제")):
                    return True
            case _ if opt in fc or opt in ch:
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
    """
    [역할] 단일 의약품 사전이 다중 외형 조건(카테고리 간 AND, 카테고리 내 OR)에 부합하는지 검증합니다.
    [경로] unified_drug_search() / search_pills_by_appearance() -> matches_appearance_filters()
    [수정] 크기(mm) 범위 조건을 추가하려면 lengLong/lengShort 비교 절을 덧붙이세요.
    """
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

    if forms and not _match_form_option(rec.get("formCodeName", ""), rec.get("chart", ""), forms):
        return False

    if line_fronts and not _match_line_side(rec.get("lineFront", ""), line_fronts):
        return False

    if line_backs and not _match_line_side(rec.get("lineBack", ""), line_backs):
        return False

    if pt:
        pt_low = pt.lower()
        pf = (rec.get("printFront") or "").strip().lower()
        pb = (rec.get("printBack") or "").strip().lower()
        if print_exact:
            if pf != pt_low and pb != pt_low:
                return False
        elif pt_low not in pf and pt_low not in pb:
            return False

    return True


def _make_cache_key(prefix: str, **kwargs: Any) -> str:
    """
    [역할] 검색 파라미터 조합을 BLAKE2b 해시로 직렬화하여 고정 길이 캐시 키를 생성합니다.
    [경로] fetch_* / enrich_single_drug_detail -> _make_cache_key() -> django.core.cache
    [수정] 캐시 네임스페이스를 초기화하려면 반환 문자열의 버전을 "edrugs:v2:"로 올리세요.
    """
    serialized = json.dumps(kwargs, sort_keys=True, ensure_ascii=False)
    digest = hashlib.blake2b(serialized.encode("utf-8"), digest_size=12).hexdigest()
    return f"edrugs:{prefix}:{digest}"


def clean_ingredient_text(raw_ingr: Any) -> str:
    """
    [역할] 주성분 문자열에서 식약처 성분코드 대괄호([M234050] 등)와 중복 공백을 제거합니다.
    [경로] views.py · services.py -> clean_ingredient_text() -> 정규화된 성분 문자열 반환
    [수정] 추가 제거 패턴이 필요하면 _INGR_CODE_RE 정규식을 조정하세요.
    """
    if not raw_ingr:
        return ""
    cleaned = _INGR_CODE_RE.sub("", str(raw_ingr))
    cleaned = _WS_RE.sub(" ", cleaned)
    return cleaned.strip(" |,;/")


def extract_ingredient_tokens(raw_ingr: Any) -> list[tuple[str, str]]:
    """
    [역할] 복합 주성분 문자열을 개별 성분 단위로 분리해 (비교용 정규화 키, 표시명) 목록으로 반환합니다.
    [경로] views.py (_build_safety_report) -> extract_ingredient_tokens() -> 중복 성분 탐지
    [수정] 성분 구분 기호를 추가하려면 상단 _INGR_SPLIT_RE 패턴을 수정하세요.
    """
    cleaned = clean_ingredient_text(raw_ingr)
    if not cleaned:
        return []
    tokens: list[tuple[str, str]] = []
    for raw_part in _INGR_SPLIT_RE.split(cleaned):
        display = raw_part.strip()
        if not display:
            continue
        base_stem = _PAREN_SPLIT_RE.split(display, maxsplit=1)[0].strip() or display
        canonical_key = _ALL_WS_RE.sub("", base_stem).lower()
        if canonical_key:
            tokens.append((canonical_key, display))
    return tokens


def strip_html(text: Any) -> str:
    """
    [역할] CDATA 본문과 ARTICLE 제목을 먼저 보존한 뒤 HTML 태그와 엔티티를 평문으로 정제합니다.
    [경로] OpenAPI 텍스트 필드 -> strip_html() -> parse_mfds_doc_xml / 검색·상세 응답
    [수정] 줄바꿈 압축 강도를 바꾸려면 _NEWLINE_RE 정규식을 조정하세요.
    """
    if not text:
        return ""
    raw = str(text)
    raw = _CDATA_RE.sub(r"\1", raw)
    raw = _ARTICLE_TITLE_RE.sub(r"\n\1\n", raw)
    cleaned = _TAG_RE.sub(" ", raw)
    cleaned = html.unescape(cleaned).replace("\xa0", " ")
    cleaned = "\n".join(_WS_RE.sub(" ", line).strip() for line in cleaned.splitlines())
    return _NEWLINE_RE.sub("\n\n", cleaned).strip()


def parse_mfds_doc_xml(doc_xml: Any, max_len: int = 1500) -> str:
    """
    [역할] 식약처 허가상세 XML(EE/UD/NB_DOC_DATA)에서 SECTION·ARTICLE 속성과 PARAGRAPH 본문을 O(N)으로 중복 없이 추출합니다.
    [경로] enrich_single_drug_detail() -> parse_mfds_doc_xml() -> 전문의약품 효능·용법·주의사항 평문 반환
    [수정] 본문 최대 길이를 늘리려면 호출부의 max_len 인자를 조정하세요.
    """
    if not doc_xml:
        return ""
    raw_text = str(doc_xml).strip()
    if not raw_text:
        return ""

    if "<DOC" in raw_text or "<ARTICLE" in raw_text or "<PARAGRAPH" in raw_text:
        try:
            root = ET.fromstring(raw_text)
            doc_title = (root.attrib.get("title") or "").strip()
            lines: list[str] = []
            seen: set[str] = set()
            for elem in root.iter():
                if elem.tag in {"SECTION", "ARTICLE"}:
                    title_val = strip_html(elem.attrib.get("title") or "")
                    if title_val and title_val != doc_title and title_val not in seen:
                        seen.add(title_val)
                        lines.append(title_val)
                elif elem.tag == "PARAGRAPH":
                    para_text = strip_html("".join(elem.itertext()))
                    if para_text and para_text not in seen:
                        seen.add(para_text)
                        lines.append(para_text)
            if lines:
                return "\n".join(lines)[:max_len].strip()
        except ET.ParseError:
            pass

    return strip_html(raw_text)[:max_len].strip()


def normalize_name(name: Any) -> str:
    """
    [역할] 품목명에서 괄호 부가정보와 공백을 제거한 비교용 정규화 이름을 반환합니다.
    [경로] _pick_matching_items() / unified_drug_search() -> normalize_name()
    [수정] 영문 대소문자까지 통일하려면 반환값 끝에 .lower()를 추가하세요.
    """
    if not name:
        return ""
    base = _PAREN_SPLIT_RE.split(str(name), maxsplit=1)[0]
    return _ALL_WS_RE.sub("", base).strip()


def extract_search_stem(name: Any) -> str:
    """
    [역할] 식약처 API 검색 정확도를 높이기 위해 품목명에서 괄호 이전의 핵심 이름만 추출합니다.
    [경로] fetch_easy_drugs / fetch_grain_drugs / fetch_prmsn_* -> extract_search_stem()
    [수정] 괄호 포함 원문 검색이 필요하면 str(name).strip()을 그대로 반환하도록 변경하세요.
    """
    if not name:
        return ""
    return _PAREN_SPLIT_RE.split(str(name), maxsplit=1)[0].strip()


def _parse_api_response(resp_text: str) -> tuple[list[dict[str, Any]], int]:
    """
    [역할] 공공데이터포털의 비정형 JSON/XML 응답을 일관된 (items 리스트, total_count) 튜플로 변환합니다.
    [경로] fetch_easy_drugs / fetch_grain_drugs / fetch_prmsn_* -> _parse_api_response()
    [수정] 신규 응답 래퍼 구조가 추가되면 raw_items 분기 조건을 확장하세요.
    """
    if not resp_text:
        return [], 0
    text = resp_text.strip()

    if text.startswith(("{", "[")):
        try:
            data = json.loads(text)
            header = data.get("header") or data.get("response", {}).get("header") or {}
            result_code = str(header.get("resultCode") or "00").strip()
            if result_code not in {"00", "0", ""}:
                if result_code != "03":
                    logger.warning(
                        "MFDS OpenAPI error code=%s msg=%s",
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

            return [row for row in raw_items if isinstance(row, dict)], total_count
        except (ValueError, TypeError) as exc:
            logger.debug("JSON 파싱 실패: %s", exc)
            return [], 0

    if text.startswith("<"):
        try:
            root = ET.fromstring(text)
            reason_code = (
                root.findtext(".//returnReasonCode") or root.findtext(".//resultCode") or "00"
            ).strip()
            if reason_code not in {"00", "0", ""}:
                if reason_code != "03":
                    logger.warning("MFDS XML error code=%s", reason_code)
                return [], 0

            total_text = root.findtext(".//totalCount")
            total_count = int(total_text) if (total_text and total_text.isdigit()) else 0
            items = [
                {child.tag: (child.text or "") for child in item_el}
                for item_el in root.findall(".//item")
            ]
            return [row for row in items if row], total_count
        except ET.ParseError as exc:
            logger.debug("XML 파싱 실패: %s", exc)
            return [], 0

    return [], 0


def _pick_matching_items(
    items: list[dict[str, Any]],
    item_seq: str = "",
    item_name: str = "",
    seq_keys: tuple[str, ...] = ("ITEM_SEQ", "itemSeq"),
    name_keys: tuple[str, ...] = ("ITEM_NAME", "itemName"),
) -> list[dict[str, Any]]:
    """
    [역할] 다건의 API 응답 중 요청한 품목기준코드(item_seq) 또는 품목명(item_name)과 일치하는 레코드를 선별합니다.
    [경로] fetch_prmsn_detail() / enrich_single_drug_detail() -> _pick_matching_items()
    [수정] 코드 완전 일치만 허용하려면 partial_name 분기를 제거하세요.
    """
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
            it for it in items if any(normalize_name(it.get(k)) == target_norm for k in name_keys)
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
    [역할] 식약처 의약품개요정보(e약은요) API를 호출해 효능·복용법·주의사항·보관법을 조회합니다.
    [경로] unified_drug_search / enrich_single_drug_detail -> fetch_easy_drugs -> settings.MFDS_ENDPOINTS["EASY_LIST"]
    [수정] 요청 파라미터 매핑을 변경하려면 아래 params 조건 분기를 수정하세요.
    """
    service_key = settings.MFDS_API_KEYS.get("EASY", "")
    if not service_key:
        return [], 0

    cache_key = _make_cache_key(
        "easy", kw=keyword, sf=search_field, seq=item_seq, p=page_no, r=num_of_rows
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    params: dict[str, Any] = {
        "serviceKey": service_key,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "type": "json",
    }
    if item_seq:
        params["itemSeq"] = item_seq
    elif keyword:
        if search_field == "efcy":
            params["efcyQesitm"] = keyword
        elif search_field == "entp":
            params["entpName"] = keyword
        else:
            params["itemName"] = extract_search_stem(keyword) or keyword

    try:
        resp = SESSION.get(
            settings.MFDS_ENDPOINTS["EASY_LIST"], params=params, timeout=DEFAULT_TIMEOUT
        )
        resp.raise_for_status()
        result = _parse_api_response(resp.text)
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
    [역할] 식약처 의약품 낱알식별 API를 호출해 실물 사진·모양·색상·각인·분할선·크기 정보를 조회합니다.
    [경로] unified_drug_search / enrich_single_drug_detail / seed_initial_pill_cache -> fetch_grain_drugs -> GRAIN_LIST
    [수정] 워커 스레드 내부 호출 시 DB 잠금을 피하려면 save_cache=False로 호출 후 메인 스레드에서 일괄 저장하세요.
    """
    service_key = settings.MFDS_API_KEYS.get("GRAIN", "")
    if not service_key:
        return [], 0

    cache_key = _make_cache_key(
        "grain", kw=keyword, sf=search_field, seq=item_seq, p=page_no, r=num_of_rows
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    params: dict[str, Any] = {
        "serviceKey": service_key,
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

    try:
        resp = SESSION.get(
            settings.MFDS_ENDPOINTS["GRAIN_LIST"], params=params, timeout=DEFAULT_TIMEOUT
        )
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
    [역할] 식약처 의약품 제품 허가목록 API를 호출해 전문/일반 구분, 주성분명, 허가일, EDI 코드를 조회합니다.
    [경로] views.py (api_permission_search) / unified_drug_search / enrich_single_drug_detail -> PRMSN_LIST
    [수정] 업종(induty) 등 추가 검색 필터를 지원하려면 params 사전에 쿼리 키를 추가하세요.
    """
    service_key = settings.MFDS_API_KEYS.get("PERMISSION", "")
    if not service_key:
        return [], 0

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

    params: dict[str, Any] = {
        "serviceKey": service_key,
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
        resp = SESSION.get(
            settings.MFDS_ENDPOINTS["PRMSN_LIST"], params=params, timeout=DEFAULT_TIMEOUT
        )
        resp.raise_for_status()
        result = _parse_api_response(resp.text)
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
    [역할] 식약처 제품 허가상세 API를 호출해 원료분량·저장방법·유효기간 및 전문의약품 XML 첨부문서를 조회합니다.
    [경로] enrich_single_drug_detail() -> fetch_prmsn_detail() -> settings.MFDS_ENDPOINTS["PRMSN_DETAIL"]
    [수정] 상세 응답 지연을 줄이려면 DETAIL_TIMEOUT 읽기 시간을 조정하세요.
    """
    if not item_seq and not item_name:
        return [], 0

    service_key = settings.MFDS_API_KEYS.get("PERMISSION", "")
    if not service_key:
        return [], 0

    cache_key = _make_cache_key("prmsn_dtl", seq=item_seq, nm=item_name, p=page_no, r=num_of_rows)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    params: dict[str, Any] = {
        "serviceKey": service_key,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "type": "json",
    }
    if item_seq:
        params["item_seq"] = item_seq
    elif item_name:
        params["item_name"] = extract_search_stem(item_name) or item_name

    try:
        resp = SESSION.get(
            settings.MFDS_ENDPOINTS["PRMSN_DETAIL"], params=params, timeout=DETAIL_TIMEOUT
        )
        resp.raise_for_status()
        items, total = _parse_api_response(resp.text)
        matched = _pick_matching_items(items, item_seq=item_seq, item_name=item_name)
        result = (matched, total)
        cache.set(cache_key, result, CACHE_TTL_SECONDS)
        return result
    except requests.RequestException as exc:
        logger.debug("제품허가 상세 API 타임아웃/생략: %s", exc)
        return [], 0


def save_grain_items_to_cache(items: list[dict[str, Any]]) -> int:
    """
    [역할] 낱알식별 API 응답 목록을 SQLite PillCache 테이블에 단일 bulk_create Upsert 쿼리로 고속 저장합니다.
    [경로] fetch_grain_drugs / unified_drug_search / enrich_single_drug_detail -> PillCache (Backend/db.sqlite3)
    [수정] 저장 필드를 늘리려면 models.py의 PillCache와 상단 _PILL_CACHE_UPDATE_FIELDS를 함께 수정하세요.
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
            item_seq=seq[:32],
            item_name=str(raw.get("ITEM_NAME") or "").strip()[:255],
            entp_name=str(raw.get("ENTP_NAME") or "").strip()[:150],
            chart=str(raw.get("CHART") or "").strip(),
            item_image=sanitize_http_url(raw.get("ITEM_IMAGE"), max_len=500),
            print_front=str(raw.get("PRINT_FRONT") or "").strip()[:100],
            print_back=str(raw.get("PRINT_BACK") or "").strip()[:100],
            drug_shape=str(raw.get("DRUG_SHAPE") or "").strip()[:50],
            color_class1=str(raw.get("COLOR_CLASS1") or "").strip()[:50],
            color_class2=str(raw.get("COLOR_CLASS2") or "").strip()[:50],
            line_front=str(raw.get("LINE_FRONT") or "").strip()[:50],
            line_back=str(raw.get("LINE_BACK") or "").strip()[:50],
            leng_long=str(raw.get("LENG_LONG") or "").strip()[:30],
            leng_short=str(raw.get("LENG_SHORT") or "").strip()[:30],
            thick=str(raw.get("THICK") or "").strip()[:30],
            class_no=str(raw.get("CLASS_NO") or "").strip()[:30],
            class_name=str(raw.get("CLASS_NAME") or "").strip()[:120],
            etc_otc_name=str(raw.get("ETC_OTC_NAME") or "").strip()[:50],
            form_code_name=str(raw.get("FORM_CODE_NAME") or "").strip()[:80],
            item_eng_name=str(raw.get("ITEM_ENG_NAME") or "").strip()[:255],
            edi_code=str(raw.get("EDI_CODE") or "").strip()[:50],
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
        logger.warning("PillCache 일괄 저장 실패: %s", exc)
        return 0


def search_pills_by_appearance(
    *,
    shapes: list[str] | None = None,
    colors: list[str] | None = None,
    forms: list[str] | None = None,
    line_fronts: list[str] | None = None,
    line_backs: list[str] | None = None,
    print_text: str = "",
    print_exact: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """
    [역할] SQLite 인덱스로 1차 WHERE 조건을 푸시다운한 뒤 복합 낱알 외형 조건에 일치하는 약품을 반환합니다.
    [경로] unified_drug_search() -> search_pills_by_appearance() -> PillCache (Backend/db.sqlite3)
    [수정] 최대 반환 건수(기본 500건)를 조정하려면 return 슬라이스 상한을 변경하세요.
    """
    if not PillCache.objects.exists():
        seed_initial_pill_cache()

    shapes = shapes or []
    colors = colors or []
    forms = forms or []
    line_fronts = line_fronts or []
    line_backs = line_backs or []
    pt = (print_text or "").strip()

    qs = PillCache.objects.all()

    # SQL 인덱스 푸시다운: 모양·색상·각인 조건을 SQLite 레벨에서 먼저 걸러 파이썬 순회량을 최소화
    if shapes:
        if "기타" not in shapes:
            qs = qs.filter(drug_shape__in=shapes)
        else:
            std_selected = [s for s in shapes if s != "기타"]
            other_q = ~Q(drug_shape__in=_STANDARD_SHAPES) & ~Q(drug_shape="")
            qs = qs.filter(Q(drug_shape__in=std_selected) | other_q) if std_selected else qs.filter(other_q)

    if colors:
        color_q = Q()
        for c in colors:
            color_q |= Q(color_class1__icontains=c) | Q(color_class2__icontains=c)
        qs = qs.filter(color_q)

    if pt:
        if print_exact:
            qs = qs.filter(Q(print_front__iexact=pt) | Q(print_back__iexact=pt))
        else:
            qs = qs.filter(Q(print_front__icontains=pt) | Q(print_back__icontains=pt))

    matched_items: list[dict[str, Any]] = []
    for row in qs.values(*_PILL_VALUES_FIELDS).iterator(chunk_size=500):
        rec = {
            "itemSeq": row["item_seq"],
            "itemName": row["item_name"],
            "entpName": row["entp_name"],
            "chart": row["chart"],
            "itemImage": sanitize_http_url(row["item_image"]),
            "printFront": row["print_front"],
            "printBack": row["print_back"],
            "drugShape": row["drug_shape"],
            "colorClass1": row["color_class1"],
            "colorClass2": row["color_class2"],
            "lineFront": row["line_front"],
            "lineBack": row["line_back"],
            "lengLong": row["leng_long"],
            "lengShort": row["leng_short"],
            "thick": row["thick"],
            "className": row["class_name"],
            "etcOtcName": row["etc_otc_name"],
            "formCodeName": row["form_code_name"],
            "itemEngName": row["item_eng_name"],
            "ediCode": row["edi_code"],
            "sources": ["낱알식별"],
        }
        if matches_appearance_filters(
            rec,
            shapes=shapes,
            colors=colors,
            forms=forms,
            line_fronts=line_fronts,
            line_backs=line_backs,
            print_text=pt,
            print_exact=print_exact,
        ):
            matched_items.append(rec)

    matched_items.sort(key=lambda x: (0 if x["itemImage"] else 1, x["itemName"]))
    return matched_items[:500], len(matched_items)


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
    [역할] 식약처 3대 OpenAPI와 SQLite PillCache를 병렬 조회하여 품목코드·이름 기준으로 중복 없이 통합 병합합니다.
    [경로] views.py (api_unified_search) -> unified_drug_search() -> fetch_* 3종 & PillCache
    [수정] 결과 정렬 우선순위를 바꾸려면 하단 results.sort의 key 람다식을 수정하세요.
    """
    shapes = shapes or []
    colors = colors or []
    forms = forms or []
    line_fronts = line_fronts or []
    line_backs = line_backs or []
    pt = (print_text or "").strip()
    has_appearance_filter = bool(shapes or colors or forms or line_fronts or line_backs or pt)
    kw = (keyword or "").strip()

    if not kw and has_appearance_filter:
        items, total_matched = search_pills_by_appearance(
            shapes=shapes,
            colors=colors,
            forms=forms,
            line_fronts=line_fronts,
            line_backs=line_backs,
            print_text=pt,
            print_exact=print_exact,
        )
        return items, {
            "easyTotal": 0,
            "grainTotal": total_matched,
            "prmsnTotal": 0,
            "mergedCount": len(items),
        }

    fut_easy = _API_EXECUTOR.submit(fetch_easy_drugs, kw, search_field, "", page_no, num_of_rows)
    if search_field == "efcy":
        fut_grain = None
        fut_prmsn = None
    else:
        grain_field = "entp" if search_field == "entp" else "item_name"
        fut_grain = _API_EXECUTOR.submit(
            fetch_grain_drugs, kw, grain_field, "", page_no, num_of_rows, save_cache=False
        )
        fut_prmsn = _API_EXECUTOR.submit(
            fetch_prmsn_list, kw, grain_field, "", "", page_no, num_of_rows
        )

    easy_items, easy_total = fut_easy.result()
    grain_items, grain_total = fut_grain.result() if fut_grain else ([], 0)
    prmsn_items, prmsn_total = fut_prmsn.result() if fut_prmsn else ([], 0)

    if search_field == "efcy" and easy_items:
        first_name = normalize_name(easy_items[0].get("itemName", ""))[:6]
        if first_name:
            f_g = _API_EXECUTOR.submit(
                fetch_grain_drugs, first_name, "item_name", "", 1, 10, save_cache=False
            )
            f_p = _API_EXECUTOR.submit(fetch_prmsn_list, first_name, "item_name", "", "", 1, 10)
            grain_items, _ = f_g.result()
            prmsn_items, _ = f_p.result()

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
                "efcyQesitm": "",
                "useMethodQesitm": "",
                "atpnWarnQesitm": "",
                "atpnQesitm": "",
                "intrcQesitm": "",
                "seQesitm": "",
                "depositMethodQesitm": "",
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
                "validTerm": "",
                "storageMethod": "",
                "barCode": "",
                "sources": [],
            }
        return merged_map[seq_str]

    for item in easy_items:
        rec = get_or_create_record(item.get("itemSeq"), item.get("itemName"), item.get("entpName"))
        if "e약은요" not in rec["sources"]:
            rec["sources"].append("e약은요")
        rec["itemImage"] = rec["itemImage"] or sanitize_http_url(item.get("itemImage"))
        rec["efcyQesitm"] = strip_html(item.get("efcyQesitm"))
        rec["useMethodQesitm"] = strip_html(item.get("useMethodQesitm"))
        rec["atpnWarnQesitm"] = strip_html(item.get("atpnWarnQesitm"))
        rec["atpnQesitm"] = strip_html(item.get("atpnQesitm"))
        rec["intrcQesitm"] = strip_html(item.get("intrcQesitm"))
        rec["seQesitm"] = strip_html(item.get("seQesitm"))
        rec["depositMethodQesitm"] = strip_html(item.get("depositMethodQesitm"))

    for item in grain_items:
        rec = get_or_create_record(
            item.get("ITEM_SEQ"), item.get("ITEM_NAME"), item.get("ENTP_NAME")
        )
        if "낱알식별" not in rec["sources"]:
            rec["sources"].append("낱알식별")
        rec["itemImage"] = rec["itemImage"] or sanitize_http_url(item.get("ITEM_IMAGE"))
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

    for item in prmsn_items:
        rec = get_or_create_record(
            item.get("ITEM_SEQ"), item.get("ITEM_NAME"), item.get("ENTP_NAME")
        )
        if "허가정보" not in rec["sources"]:
            rec["sources"].append("허가정보")
        rec["itemImage"] = rec["itemImage"] or sanitize_http_url(item.get("BIG_PRDT_IMG_URL"))
        rec["itemEngName"] = item.get("ITEM_ENG_NAME") or rec["itemEngName"]
        rec["etcOtcName"] = item.get("SPCLTY_PBLC") or rec["etcOtcName"]
        rec["className"] = item.get("PRDUCT_TYPE") or rec["className"]
        rec["itemIngrName"] = clean_ingredient_text(item.get("ITEM_INGR_NAME")) or rec["itemIngrName"]
        rec["itemPermitDate"] = item.get("ITEM_PERMIT_DATE") or rec["itemPermitDate"]
        rec["ediCode"] = item.get("EDI_CODE") or rec["ediCode"]

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
        for row in PillCache.objects.filter(local_filter).values(*_PILL_VALUES_FIELDS)[:100]:
            rec = get_or_create_record(row["item_seq"], row["item_name"], row["entp_name"])
            if "낱알식별" not in rec["sources"]:
                rec["sources"].append("낱알식별")
            rec["itemImage"] = rec["itemImage"] or sanitize_http_url(row["item_image"])
            rec["chart"] = rec["chart"] or row["chart"]
            rec["drugShape"] = rec["drugShape"] or row["drug_shape"]
            rec["colorClass1"] = rec["colorClass1"] or row["color_class1"]
            rec["colorClass2"] = rec["colorClass2"] or row["color_class2"]
            rec["printFront"] = rec["printFront"] or row["print_front"]
            rec["printBack"] = rec["printBack"] or row["print_back"]
            rec["lineFront"] = rec["lineFront"] or row["line_front"]
            rec["lineBack"] = rec["lineBack"] or row["line_back"]
            rec["lengLong"] = rec["lengLong"] or row["leng_long"]
            rec["lengShort"] = rec["lengShort"] or row["leng_short"]
            rec["thick"] = rec["thick"] or row["thick"]
            rec["formCodeName"] = rec["formCodeName"] or row["form_code_name"]
            rec["etcOtcName"] = rec["etcOtcName"] or row["etc_otc_name"]
            rec["className"] = rec["className"] or row["class_name"]
            rec["itemEngName"] = rec["itemEngName"] or row["item_eng_name"]
            rec["ediCode"] = rec["ediCode"] or row["edi_code"]

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
    [역할] 단일 의약품의 SQLite 캐시와 3대 OpenAPI(허가상세 XML 포함)를 병렬 교차 조회해 통합 상세 사전을 반환합니다.
    [경로] views.py (api_drug_detail / api_pillbox) -> enrich_single_drug_detail() -> PillCache & fetch_* 4종
    [수정] 허가상세 XML 추출 글자 수를 조정하려면 하단 parse_mfds_doc_xml의 max_len을 변경하세요.
    """
    cache_key = _make_cache_key("drug_detail", seq=item_seq, nm=item_name)
    cached_detail = cache.get(cache_key)
    if cached_detail is not None:
        return cached_detail

    cached_pill: PillCache | None = None
    if item_seq:
        cached_pill = PillCache.objects.filter(item_seq=item_seq).first()
    if not cached_pill and item_name:
        cached_pill = PillCache.objects.filter(item_name=item_name).first()

    effective_name = item_name or (cached_pill.item_name if cached_pill else "")
    effective_seq = item_seq or (cached_pill.item_seq if cached_pill else "")

    f_easy = _API_EXECUTOR.submit(fetch_easy_drugs, effective_name, "itemName", effective_seq, 1, 5)
    f_grain = (
        None
        if cached_pill is not None
        else _API_EXECUTOR.submit(
            fetch_grain_drugs, effective_name, "item_name", effective_seq, 1, 10, save_cache=False
        )
    )
    f_prmsn = (
        _API_EXECUTOR.submit(fetch_prmsn_list, effective_name, "item_name", effective_seq, "", 1, 10)
        if effective_name
        else None
    )
    f_dtl = _API_EXECUTOR.submit(fetch_prmsn_detail, effective_seq, effective_name, 1, 3)

    raw_easy, _ = f_easy.result()
    raw_grain, _ = f_grain.result() if f_grain else ([], 0)
    raw_prmsn, _ = f_prmsn.result() if f_prmsn else ([], 0)
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
        "itemIngrCnt": "",
        "materialName": "",
        "itemPermitDate": "",
        "validTerm": "",
        "storageMethod": "",
        "packUnit": "",
        "barCode": "",
        "atcCode": "",
        "ediCode": "",
        "induty": "",
        "bizrno": "",
        "cancelName": "",
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
        "sources": [],
    }

    if easy_items:
        e = easy_items[0]
        detail["sources"].append("e약은요")
        detail["itemSeq"] = detail["itemSeq"] or e.get("itemSeq") or ""
        detail["itemName"] = detail["itemName"] or e.get("itemName") or ""
        detail["entpName"] = detail["entpName"] or e.get("entpName") or ""
        detail["itemImage"] = detail["itemImage"] or sanitize_http_url(e.get("itemImage"))
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
        detail["itemImage"] = detail["itemImage"] or sanitize_http_url(cached_pill.item_image)
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
        detail["itemImage"] = detail["itemImage"] or sanitize_http_url(g.get("ITEM_IMAGE"))
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
        detail["itemImage"] = detail["itemImage"] or sanitize_http_url(p.get("BIG_PRDT_IMG_URL"))
        detail["etcOtcName"] = detail["etcOtcName"] or p.get("SPCLTY_PBLC") or ""
        detail["className"] = detail["className"] or p.get("PRDUCT_TYPE") or ""
        detail["itemIngrName"] = detail["itemIngrName"] or clean_ingredient_text(
            p.get("ITEM_INGR_NAME")
        )
        detail["itemIngrCnt"] = detail["itemIngrCnt"] or str(p.get("ITEM_INGR_CNT") or "")
        detail["itemPermitDate"] = detail["itemPermitDate"] or p.get("ITEM_PERMIT_DATE") or ""
        detail["ediCode"] = detail["ediCode"] or p.get("EDI_CODE") or ""
        detail["induty"] = detail["induty"] or p.get("INDUTY") or ""
        detail["bizrno"] = detail["bizrno"] or p.get("BIZRNO") or ""
        detail["cancelName"] = detail["cancelName"] or p.get("CANCEL_NAME") or ""

    if dtl_items:
        d = dtl_items[0]
        if "허가정보" not in detail["sources"]:
            detail["sources"].append("허가정보")
        detail["itemSeq"] = detail["itemSeq"] or d.get("ITEM_SEQ") or ""
        detail["itemName"] = detail["itemName"] or d.get("ITEM_NAME") or ""
        detail["entpName"] = detail["entpName"] or d.get("ENTP_NAME") or ""
        detail["itemEngName"] = detail["itemEngName"] or d.get("ITEM_ENG_NAME") or ""
        detail["itemPermitDate"] = detail["itemPermitDate"] or d.get("ITEM_PERMIT_DATE") or ""
        detail["ediCode"] = detail["ediCode"] or d.get("EDI_CODE") or ""
        detail["etcOtcName"] = detail["etcOtcName"] or d.get("ETC_OTC_CODE") or ""
        detail["cancelName"] = detail["cancelName"] or d.get("CANCEL_NAME") or ""
        detail["chart"] = detail["chart"] or d.get("CHART") or ""
        detail["barCode"] = d.get("BAR_CODE") or ""
        detail["materialName"] = d.get("MATERIAL_NAME") or ""
        detail["storageMethod"] = d.get("STORAGE_METHOD") or ""
        detail["validTerm"] = d.get("VALID_TERM") or ""
        detail["packUnit"] = d.get("PACK_UNIT") or ""
        detail["itemIngrName"] = (
            detail["itemIngrName"]
            or clean_ingredient_text(d.get("MAIN_ITEM_INGR"))
            or clean_ingredient_text(d.get("INGR_NAME"))
        )
        detail["atcCode"] = d.get("ATC_CODE") or ""

        if not detail["efcyQesitm"] and d.get("EE_DOC_DATA"):
            detail["efcyQesitm"] = parse_mfds_doc_xml(d.get("EE_DOC_DATA"), max_len=1200)
        if not detail["useMethodQesitm"] and d.get("UD_DOC_DATA"):
            detail["useMethodQesitm"] = parse_mfds_doc_xml(d.get("UD_DOC_DATA"), max_len=1200)
        if not detail["atpnQesitm"] and d.get("NB_DOC_DATA"):
            detail["atpnQesitm"] = parse_mfds_doc_xml(d.get("NB_DOC_DATA"), max_len=1500)

    cache.set(cache_key, detail, CACHE_TTL_SECONDS)
    return detail


def seed_initial_pill_cache() -> int:
    """
    [역할] PillCache가 비어 있을 때 다빈도 상비약·처방약 약 1,100여 건을 병렬 수집하여 SQLite에 적재합니다.
    [경로] views.py (api_status) / search_pills_by_appearance() -> seed_initial_pill_cache() -> PillCache
    [수정] 초기 적재 약품을 추가하려면 popular_keywords 튜플에 키워드를 추가하세요.
    """
    popular_keywords: tuple[str, ...] = (
        "타이레놀",
        "게보린",
        "아스피린",
        "베아제",
        "탁센",
        "이지엔",
        "노바스크",
        "리피토",
    )
    futures = [
        _API_EXECUTOR.submit(fetch_grain_drugs, "", "item_name", "", page, 100, save_cache=False)
        for page in range(1, 11)
    ] + [
        _API_EXECUTOR.submit(fetch_grain_drugs, kw, "item_name", "", 1, 30, save_cache=False)
        for kw in popular_keywords
    ]

    collected_items: list[dict[str, Any]] = []
    for fut in futures:
        items, _ = fut.result()
        if items:
            collected_items.extend(items)

    return save_grain_items_to_cache(collected_items)
