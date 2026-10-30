"""알약이가 (e-Drug Care) 백엔드 핵심 기능 자동화 테스트 모듈."""
from __future__ import annotations

import json
from django.conf import settings
from django.test import TestCase
from .models import PillCache, SavedDrug
from .services import _parse_api_response, save_grain_items_to_cache


class EDrugsBackendTests(TestCase):
    """환경변수 로드, 정적 파일 서빙, OpenAPI 파서 및 내 약통 안전 분석 검증"""

    def test_env_and_endpoints_configured(self) -> None:
        """통합 .env에서 식약처 3대 OpenAPI 엔드포인트와 키가 정상 로드되는지 검증"""
        self.assertTrue(settings.SECRET_KEY)
        self.assertTrue(settings.MFDS_API_KEYS["GRAIN"])
        self.assertTrue(settings.MFDS_API_KEYS["PERMISSION"])
        self.assertTrue(settings.MFDS_API_KEYS["EASY"])
        self.assertNotIn("%2F", settings.MFDS_API_KEYS["EASY"])
        self.assertIn("DrbEasyDrugInfoService", settings.MFDS_ENDPOINTS["EASY_BASE"])

    def test_index_and_frontend_assets(self) -> None:
        """Frontend/index.html, style.css, app.js가 Django를 통해 정상 서빙되는지 검증"""
        resp_index = self.client.get("/")
        self.assertEqual(resp_index.status_code, 200)

        resp_css = self.client.get("/style.css")
        self.assertEqual(resp_css.status_code, 200)
        resp_css.close()

        resp_js = self.client.get("/app.js")
        self.assertEqual(resp_js.status_code, 200)
        resp_js.close()

    def test_parse_api_response_edge_cases(self) -> None:
        """JSON 응답의 다양한 items 형태(list, dict.item, 빈 값)를 안전하게 파싱하는지 검증"""
        wrapped = json.dumps(
            {
                "header": {"resultCode": "00"},
                "body": {"totalCount": 1, "items": {"item": {"ITEM_SEQ": "100", "ITEM_NAME": "테스트정"}}},
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

    def test_bulk_cache_and_pillbox_duplicate_check(self) -> None:
        """PillCache 고속 일괄 Upsert 및 내 약통 주성분 중복 감지 로직 검증"""
        count = save_grain_items_to_cache(
            [
                {"ITEM_SEQ": "99901", "ITEM_NAME": "테스트알약A", "DRUG_SHAPE": "원형", "COLOR_CLASS1": "하양"},
                {"ITEM_SEQ": "99901", "ITEM_NAME": "테스트알약A_수정", "DRUG_SHAPE": "원형", "COLOR_CLASS1": "노랑"},
            ]
        )
        self.assertEqual(count, 1)
        self.assertEqual(PillCache.objects.get(item_seq="99901").color_class1, "노랑")

        SavedDrug.objects.create(item_seq="1001", item_name="타이레놀정", ingr_name="Acetaminophen")
        SavedDrug.objects.create(item_seq="1002", item_name="판콜에이", ingr_name="Acetaminophen / Caffeine")

        resp = self.client.get("/api/pillbox/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["safetyReport"]["hasDuplicateRisk"])
        self.assertEqual(len(data["safetyReport"]["duplicateIngredients"]), 1)

    def test_unified_search_appearance_only_and_multi_filter(self) -> None:
        """검색어 없이 낱알 외형 조건(단일·복합·다중선택)만으로 통합 검색이 정확히 동작하는지 검증"""
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
