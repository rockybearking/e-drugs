"""
================================================================================
[파일명] Backend/drugs/tests.py
[역할] 알약이가 (e-Drug Care) 백엔드 및 프론트엔드 정합성 자동화 단위 테스트(Unit Test) 모듈
================================================================================

[백엔드 아키텍처 호출 흐름 (출발지 ➔ 현재 파일 ➔ 목적지)]
1. 출발지 (From):
   - 터미널에서 `python Backend/manage.py test` 명령 실행 시 Django 테스트 러너가 호출
2. 현재 파일 (drugs/tests.py)이 검증하는 목적지 파일들 (To):
   - [목적지 1] `Backend/config/settings.py`: `.env` 및 폴백 인증키(`MFDS_API_KEYS`), 엔드포인트 설정 검증
   - [목적지 2] `Backend/config/urls.py` & `Backend/drugs/urls.py`: `/`, `/style.css`, `/app.js`, `/favicon.ico`, `/api/...` 라우팅 검증
   - [목적지 3] `Backend/drugs/views.py`: 통합 검색, 내 약통 CRUD, 비정상 JSON 방어, 악성 URL(`javascript:`) 차단 검증
   - [목적지 4] `Backend/drugs/services.py`: `_parse_api_response()`, `parse_mfds_doc_xml()`, `clean_ingredient_text()`, `save_grain_items_to_cache()` 검증
   - [목적지 5] `Frontend/index.html` & `Frontend/app.js`: 홈 화면 알약(`💊`) 외 모든 그림형 아이콘(`📌`, `⚠️` 등) 제거 여부 검증

[현재 구현된 테스트 서비스]
- 테스트 실행 시 실제 운영 DB(`Backend/db.sqlite3`)를 건드리지 않고, 격리된 임시 인메모리 SQLite DB를
  자동 생성하여 테스트 후 깔끔하게 삭제합니다.
================================================================================
"""
from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from .models import PillCache, SavedDrug
from .services import (
    _parse_api_response,
    clean_ingredient_text,
    parse_mfds_doc_xml,
    save_grain_items_to_cache,
)


class EDrugsBackendTests(TestCase):
    """환경변수 로드, 정적 파일 서빙, OpenAPI XML/JSON 파서, 보안 검증 및 내 약통 안전 분석 테스트"""

    def test_env_and_endpoints_configured(self) -> None:
        """
        [검증 목적지] `Backend/config/settings.py` :: `MFDS_API_KEYS`, `MFDS_ENDPOINTS`
        [역할] `.env` 또는 폴백 인증키가 정상 로드되어 `serviceKey=` 빈 값(401 에러)이나
               이중 인코딩(`%2F`) 문제가 발생하지 않는지 검증합니다.
        """
        self.assertTrue(settings.SECRET_KEY)
        self.assertTrue(settings.MFDS_API_KEYS["GRAIN"])
        self.assertTrue(settings.MFDS_API_KEYS["PERMISSION"])
        self.assertTrue(settings.MFDS_API_KEYS["EASY"])
        self.assertNotIn("%2F", settings.MFDS_API_KEYS["EASY"])
        self.assertIn("DrbEasyDrugInfoService", settings.MFDS_ENDPOINTS["EASY_BASE"])

    def test_index_and_frontend_assets_and_favicon(self) -> None:
        """
        [검증 목적지] `Backend/config/urls.py` ➔ `Backend/drugs/views.py` (`index`, `serve_frontend_asset`, `serve_favicon`)
        [역할] `/`, `/style.css`, `/app.js`, `/favicon.ico` 요청이 모두 404 없이 200 OK로 응답하는지 검증합니다.
        """
        resp_index = self.client.get("/")
        self.assertEqual(resp_index.status_code, 200)

        resp_css = self.client.get("/style.css")
        self.assertEqual(resp_css.status_code, 200)
        resp_css.close()

        resp_js = self.client.get("/app.js")
        self.assertEqual(resp_js.status_code, 200)
        resp_js.close()

        resp_fav = self.client.get("/favicon.ico")
        self.assertEqual(resp_fav.status_code, 200)
        self.assertIn("image/svg+xml", resp_fav["Content-Type"])

    def test_emoji_policy_compliance(self) -> None:
        """
        [검증 목적지] `Frontend/index.html`, `Frontend/app.js`
        [역할] 홈 화면으로 나가는 메인 헤더의 알약 기호(`💊`) 1개만 유지되고,
               글자 맨 앞의 그림형 아이콘(`📌`, `⚠️`, `🔍`, `📋`, `🧰`, `🚨`, `🩺`, `📦` 등)이 모두 제거되었는지 검증합니다.
        """
        frontend_dir = Path(settings.FRONTEND_DIR)
        index_html = (frontend_dir / "index.html").read_text(encoding="utf-8")
        app_js = (frontend_dir / "app.js").read_text(encoding="utf-8")

        # 메인 로고의 알약 기호(💊)는 정확히 1개 유지되어야 함
        self.assertIn('<span class="brand-icon">💊</span>', index_html)
        self.assertEqual(index_html.count("💊"), 1)
        self.assertEqual(app_js.count("💊"), 0)

        forbidden_icons = (
            "📌",
            "⚠️",
            "🔍",
            "📋",
            "🧰",
            "🕒",
            "📖",
            "🔎",
            "🧪",
            "🚨",
            "🩺",
            "📦",
            "🏷️",
            "💡",
            "✅",
        )
        for icon in forbidden_icons:
            self.assertNotIn(icon, index_html, f"index.html 에 제거 대상 아이콘 {icon} 이 남아 있습니다.")
            self.assertNotIn(icon, app_js, f"app.js 에 제거 대상 아이콘 {icon} 이 남아 있습니다.")

    def test_parse_mfds_doc_xml_and_cdata_preservation(self) -> None:
        """
        [검증 목적지] `Backend/drugs/services.py` :: `parse_mfds_doc_xml()`, `clean_ingredient_text()`
        [역할] 전문의약품(예: 가모시드정5밀리그램) 허가상세 API의 XML 문서(`EE_DOC_DATA`, `UD_DOC_DATA`)에서
               `<![CDATA[...]]>` 본문과 `<ARTICLE title="..."/>` 속성이 손실 없이 추출되는지 검증합니다.
        """
        ee_xml = (
            '<DOC title="효능효과" type="EE"><SECTION title=""><ARTICLE title="">'
            '<PARAGRAPH tagName="p"><![CDATA[기능성소화불량으로 인한 소화기증상(속쓰림, 구역, 구토)]]></PARAGRAPH>'
            "</ARTICLE></SECTION></DOC>"
        )
        ud_xml = (
            '<DOC title="용법용량" type="UD"><SECTION title="">'
            '<ARTICLE title="성인 : 모사프리드시트르산염무수물로서 1일 15 mg을 3회로 나누어 식전 또는 식후에 경구투여한다." />'
            "</SECTION></DOC>"
        )
        self.assertEqual(
            parse_mfds_doc_xml(ee_xml),
            "기능성소화불량으로 인한 소화기증상(속쓰림, 구역, 구토)",
        )
        self.assertIn("1일 15 mg을 3회로 나누어", parse_mfds_doc_xml(ud_xml))
        self.assertEqual(
            clean_ingredient_text("[M234050]모사프리드시트르산염수화물"),
            "모사프리드시트르산염수화물",
        )

    def test_parse_api_response_edge_cases(self) -> None:
        """
        [검증 목적지] `Backend/drugs/services.py` :: `_parse_api_response()`
        [역할] JSON 응답의 다양한 `items` 형태(list, dict.item, 빈 값)를 안전하게 파싱하는지 검증합니다.
        """
        wrapped = json.dumps(
            {
                "header": {"resultCode": "00"},
                "body": {
                    "totalCount": 1,
                    "items": {"item": {"ITEM_SEQ": "100", "ITEM_NAME": "테스트정"}},
                },
            }
        )
        items, total = _parse_api_response(wrapped)
        self.assertEqual(total, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["ITEM_SEQ"], "100")

        empty_wrapped = json.dumps(
            {"header": {"resultCode": "00"}, "body": {"totalCount": 0, "items": {"item": []}}}
        )
        items2, total2 = _parse_api_response(empty_wrapped)
        self.assertEqual(total2, 0)
        self.assertEqual(items2, [])

    def test_bulk_cache_and_pillbox_security_and_duplicate_check(self) -> None:
        """
        [검증 목적지] `Backend/drugs/services.py` :: `save_grain_items_to_cache()` 및 `Backend/drugs/views.py` :: `api_pillbox()`
        [역할] PillCache 고속 일괄 Upsert, 내 약통 주성분 중복 감지, 그리고 악성 URL(`javascript:`) 및
               비정상 JSON 배열 요청에 대한 보안 방어 로직을 검증합니다.
        """
        count = save_grain_items_to_cache(
            [
                {
                    "ITEM_SEQ": "99901",
                    "ITEM_NAME": "테스트알약A",
                    "DRUG_SHAPE": "원형",
                    "COLOR_CLASS1": "하양",
                },
                {
                    "ITEM_SEQ": "99901",
                    "ITEM_NAME": "테스트알약A_수정",
                    "DRUG_SHAPE": "원형",
                    "COLOR_CLASS1": "노랑",
                },
            ]
        )
        self.assertEqual(count, 1)
        self.assertEqual(PillCache.objects.get(item_seq="99901").color_class1, "노랑")

        # 비정상 JSON 배열([]) 전송 시 500 에러가 아닌 400 Bad Request 반환 검증
        bad_resp = self.client.post(
            "/api/pillbox/", data=json.dumps(["invalid"]), content_type="application/json"
        )
        self.assertEqual(bad_resp.status_code, 400)

        # 악성 javascript: 이미지 URL 전송 시 빈 문자열로 무해화되는지 검증
        xss_resp = self.client.post(
            "/api/pillbox/",
            data=json.dumps(
                {
                    "itemSeq": "1001",
                    "itemName": "타이레놀정",
                    "itemIngrName": "[M001]Acetaminophen",
                    "itemImage": "javascript:alert(1)",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(xss_resp.status_code, 200)
        self.assertEqual(SavedDrug.objects.get(item_seq="1001").item_image, "")

        SavedDrug.objects.create(
            item_seq="1002", item_name="판콜에이", ingr_name="Acetaminophen / Caffeine"
        )

        resp = self.client.get("/api/pillbox/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["safetyReport"]["hasDuplicateRisk"])
        self.assertEqual(len(data["safetyReport"]["duplicateIngredients"]), 1)

    def test_unified_search_appearance_only_and_multi_filter(self) -> None:
        """
        [검증 목적지] `Backend/drugs/views.py` :: `api_unified_search()` ➔ `Backend/drugs/services.py` :: `unified_drug_search()`
        [역할] 검색어 없이 낱알 외형 조건(단일·복합·다중선택)만으로 통합 검색이 정확히 동작하는지 검증합니다.
        """
        save_grain_items_to_cache(
            [
                {
                    "ITEM_SEQ": "20001",
                    "ITEM_NAME": "원형노랑정",
                    "DRUG_SHAPE": "원형",
                    "COLOR_CLASS1": "노랑",
                    "FORM_CODE_NAME": "필름코팅정",
                    "PRINT_FRONT": "TY",
                    "LINE_FRONT": "-",
                },
                {
                    "ITEM_SEQ": "20002",
                    "ITEM_NAME": "타원형노랑정",
                    "DRUG_SHAPE": "타원형",
                    "COLOR_CLASS1": "노랑",
                    "FORM_CODE_NAME": "필름코팅정",
                    "PRINT_FRONT": "TY500",
                    "LINE_FRONT": "",
                },
                {
                    "ITEM_SEQ": "20003",
                    "ITEM_NAME": "원형하양캡슐",
                    "DRUG_SHAPE": "원형",
                    "COLOR_CLASS1": "하양",
                    "FORM_CODE_NAME": "경질캡슐제, 과립제정제",
                    "PRINT_FRONT": "HC",
                    "LINE_FRONT": "",
                },
            ]
        )

        # 1) 검색어·외형 조건 모두 없으면 400 반환
        resp_empty = self.client.get("/api/unified-search/")
        self.assertEqual(resp_empty.status_code, 400)

        # 2) 검색어 없이 모양 '원형'만 선택 -> '타원형'이 섞이지 않고 정확히 원형 2건만 반환
        resp_circle = self.client.get("/api/unified-search/?shapes=원형")
        self.assertEqual(resp_circle.status_code, 200)
        circle_names = {it["itemName"] for it in resp_circle.json()["items"]}
        self.assertIn("원형노랑정", circle_names)
        self.assertIn("원형하양캡슐", circle_names)
        self.assertNotIn("타원형노랑정", circle_names)

        # 3) 모양 '원형' + 색상 '노랑' 복합 선택 -> 교집합인 '원형노랑정'만 반환
        resp_combo = self.client.get("/api/unified-search/?shapes=원형&colors=노랑")
        self.assertEqual(resp_combo.status_code, 200)
        combo_names = [it["itemName"] for it in resp_combo.json()["items"]]
        self.assertIn("원형노랑정", combo_names)
        self.assertNotIn("타원형노랑정", combo_names)
        self.assertNotIn("원형하양캡슐", combo_names)

        # 4) 제형 '정제' 선택 -> '경질캡슐제, 과립제정제'는 제외되고 정제만 반환
        resp_tablet = self.client.get("/api/unified-search/?shapes=원형&forms=정제")
        self.assertEqual(resp_tablet.status_code, 200)
        tablet_names = [it["itemName"] for it in resp_tablet.json()["items"]]
        self.assertIn("원형노랑정", tablet_names)
        self.assertNotIn("원형하양캡슐", tablet_names)

        # 5) 식별문자 정확 일치(printExact=1) 검증
        resp_exact = self.client.get("/api/unified-search/?print=TY&printExact=1")
        self.assertEqual(resp_exact.status_code, 200)
        exact_names = [it["itemName"] for it in resp_exact.json()["items"]]
        self.assertIn("원형노랑정", exact_names)
        self.assertNotIn("타원형노랑정", exact_names)
