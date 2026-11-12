"""
[역할] 백엔드 설정·보안 헤더(CSP/CSRF)·OpenAPI 파서·외형 검색·내 약통 전체 CRUD 자동화 단위 테스트
[경로] `python Backend/manage.py test` -> Backend/drugs/tests.py -> config/*, drugs/* 검증
[수정] 신규 API 엔드포인트 추가 시 EDrugsBackendTests 클래스에 test_* 메서드를 추가하세요.
"""
from __future__ import annotations

import json
import re
from unittest.mock import patch

from django.conf import settings
from django.test import Client, TestCase

from .models import PillCache, SavedDrug, SearchLog
from .services import (
    _parse_api_response,
    clean_ingredient_text,
    extract_ingredient_tokens,
    parse_mfds_doc_xml,
    save_grain_items_to_cache,
)


class EDrugsBackendTests(TestCase):
    """
    [역할] 격리된 인메모리 SQLite DB에서 보안·파서·검색·CRUD 정합성을 검증합니다.
    [경로] Django TestRunner -> EDrugsBackendTests -> settings, middleware, services, views
    [수정] 외부 네트워크 호출 없이 검증할 수 있도록 로컬 PillCache 시드 데이터를 활용하세요.
    """

    def test_env_and_endpoints_configured(self) -> None:
        """
        [역할] 환경변수 및 식약처 3대 OpenAPI 키·엔드포인트 로드 및 이중 인코딩 방지를 검증합니다.
        [경로] tests.py -> Backend/config/settings.py (MFDS_API_KEYS, MFDS_ENDPOINTS)
        [수정] 연동 API 추가 시 해당 키가 비어 있지 않은지 assertTrue를 추가하세요.
        """
        self.assertTrue(settings.SECRET_KEY)
        self.assertTrue(settings.MFDS_API_KEYS["GRAIN"])
        self.assertTrue(settings.MFDS_API_KEYS["PERMISSION"])
        self.assertTrue(settings.MFDS_API_KEYS["EASY"])
        self.assertNotIn("%2F", settings.MFDS_API_KEYS["EASY"])
        self.assertIn("DrbEasyDrugInfoService", settings.MFDS_ENDPOINTS["EASY_BASE"])

    def test_security_headers_csp_nonce_and_static_assets(self) -> None:
        """
        [역할] 메인 템플릿의 CSP 논스 일치, 보안 헤더, CSRF 쿠키 발급 및 정적 자산 서빙을 검증합니다.
        [경로] tests.py -> SecurityHeadersMiddleware & views.py (index, serve_frontend_asset)
        [수정] 허용 정적 파일을 늘린 경우 해당 경로의 200 응답 검증을 추가하세요.
        """
        resp_index = self.client.get("/")
        self.assertEqual(resp_index.status_code, 200)
        self.assertIn("csrftoken", resp_index.cookies)
        self.assertIn("Permissions-Policy", resp_index)
        self.assertIn("Cross-Origin-Opener-Policy", resp_index)

        csp_header = resp_index["Content-Security-Policy"]
        nonce_match = re.search(r"'nonce-([^']+)'", csp_header)
        self.assertIsNotNone(nonce_match)
        nonce_val = nonce_match.group(1) if nonce_match else ""
        html_body = resp_index.content.decode("utf-8")
        self.assertIn(f'<script nonce="{nonce_val}" src="app.js" defer></script>', html_body)

        for asset_path in ("/style.css", "/app.js"):
            resp_asset = self.client.get(asset_path)
            self.assertEqual(resp_asset.status_code, 200)
            resp_asset.close()

        resp_fav = self.client.get("/favicon.ico")
        self.assertEqual(resp_fav.status_code, 200)
        self.assertIn("image/svg+xml", resp_fav["Content-Type"])

    def test_parse_mfds_doc_xml_and_ingredient_normalization(self) -> None:
        """
        [역할] 식약처 XML(CDATA·ARTICLE 속성) 파서와 주성분 정규화 토큰 추출기를 검증합니다.
        [경로] tests.py -> Backend/drugs/services.py (parse_mfds_doc_xml, extract_ingredient_tokens)
        [수정] 주성분 구분자 규칙 변경 시 extract_ingredient_tokens 케이스를 보강하세요.
        """
        ee_xml = (
            '<DOC title="효능효과" type="EE"><SECTION title=""><ARTICLE title="">'
            '<PARAGRAPH tagName="p"><![CDATA[기능성소화불량으로 인한 소화기증상(속쓰림, 구역, 구토)]]></PARAGRAPH>'
            "</ARTICLE></SECTION></DOC>"
        )
        ud_xml = (
            '<DOC title="용법용량" type="UD"><SECTION title="">'
            '<ARTICLE title="성인 : 1일 15 mg을 3회로 나누어 식전 또는 식후에 경구투여한다." />'
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

        tokens_a = dict(extract_ingredient_tokens("[M001]Acetaminophen"))
        tokens_b = dict(extract_ingredient_tokens("Acetaminophen(아세트아미노펜) / Caffeine"))
        self.assertIn("acetaminophen", tokens_a)
        self.assertIn("acetaminophen", tokens_b)

    def test_parse_api_response_formats(self) -> None:
        """
        [역할] 공공데이터포털의 단일 객체·빈 배열 JSON 및 XML 응답 파싱 안정성을 검증합니다.
        [경로] tests.py -> Backend/drugs/services.py (_parse_api_response)
        [수정] 응답 포맷 예외 추가 시 아래 입력 샘플을 확장하세요.
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
        self.assertEqual(items[0]["ITEM_SEQ"], "100")

        empty_wrapped = json.dumps(
            {"header": {"resultCode": "00"}, "body": {"totalCount": 0, "items": {"item": []}}}
        )
        items_empty, total_empty = _parse_api_response(empty_wrapped)
        self.assertEqual(total_empty, 0)
        self.assertEqual(items_empty, [])

        xml_sample = (
            "<response><body><totalCount>1</totalCount>"
            "<items><item><ITEM_SEQ>200</ITEM_SEQ><ITEM_NAME>엑스엠엘정</ITEM_NAME></item></items>"
            "</body></response>"
        )
        xml_items, xml_total = _parse_api_response(xml_sample)
        self.assertEqual(xml_total, 1)
        self.assertEqual(xml_items[0]["ITEM_NAME"], "엑스엠엘정")

    def test_pillbox_full_crud_security_and_csrf_protection(self) -> None:
        """
        [역할] 내 약통 Create·Read·Update(PATCH)·Delete, 중복 성분 감지, 악성 URL 차단 및 CSRF 방어를 검증합니다.
        [경로] tests.py -> Backend/drugs/views.py (api_pillbox) & SavedDrug
        [수정] 약통 필드 추가 시 PATCH 검증 항목을 함께 업데이트하세요.
        """
        # 1) 비정상 JSON 배열(400) 및 과대 본문(413) 방어
        bad_resp = self.client.post(
            "/api/pillbox/", data=json.dumps(["invalid"]), content_type="application/json"
        )
        self.assertEqual(bad_resp.status_code, 400)

        oversized_resp = self.client.post(
            "/api/pillbox/",
            data="x" * 70_000,
            content_type="application/json",
        )
        self.assertEqual(oversized_resp.status_code, 413)

        # 2) CREATE (POST) + javascript: 스킴 무해화 검증
        create_resp = self.client.post(
            "/api/pillbox/",
            data=json.dumps(
                {
                    "itemSeq": "1001",
                    "itemName": "타이레놀정500밀리그램",
                    "itemIngrName": "[M001]Acetaminophen",
                    "itemImage": "javascript:alert(1)",
                    "dosageTime": "아침 식후 30분",
                    "memo": "초기 메모",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_resp.status_code, 200)
        created_id = create_resp.json()["id"]
        saved_obj = SavedDrug.objects.get(id=created_id)
        self.assertEqual(saved_obj.item_image, "")
        self.assertEqual(saved_obj.memo, "초기 메모")

        # 3) 두 번째 약 추가 후 READ (GET) 시 괄호 병기 주성분 중복 감지 검증
        SavedDrug.objects.create(
            item_seq="1002",
            item_name="판콜에이내복액",
            ingr_name="Acetaminophen(아세트아미노펜) / Caffeine",
            warn_text="매일 세잔 이상 정기적으로 술을 마시는 사람이 복용할 경우 간손상이 유발될 수 있습니다.",
        )
        read_resp = self.client.get("/api/pillbox/")
        self.assertEqual(read_resp.status_code, 200)
        read_data = read_resp.json()
        self.assertTrue(read_data["safetyReport"]["hasDuplicateRisk"])
        self.assertEqual(len(read_data["safetyReport"]["duplicateIngredients"]), 1)
        self.assertEqual(len(read_data["safetyReport"]["warnings"]), 1)

        # 4) UPDATE (PATCH) 복용 시간 및 개인 메모 수정 검증
        patch_resp = self.client.patch(
            "/api/pillbox/",
            data=json.dumps(
                {
                    "id": created_id,
                    "dosageTime": "취침 전 1회",
                    "memo": "두통 심할 때만 복용",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(patch_resp.status_code, 200)
        saved_obj.refresh_from_db()
        self.assertEqual(saved_obj.dosage_time, "취침 전 1회")
        self.assertEqual(saved_obj.memo, "두통 심할 때만 복용")

        not_found_patch = self.client.patch(
            "/api/pillbox/",
            data=json.dumps({"id": 999999, "dosageTime": "아침"}),
            content_type="application/json",
        )
        self.assertEqual(not_found_patch.status_code, 404)

        # 5) DELETE 삭제 및 누락 파라미터 400 검증
        missing_del = self.client.delete("/api/pillbox/")
        self.assertEqual(missing_del.status_code, 400)

        del_resp = self.client.delete(f"/api/pillbox/?id={created_id}")
        self.assertEqual(del_resp.status_code, 200)
        self.assertFalse(SavedDrug.objects.filter(id=created_id).exists())

        # 6) 실제 CSRF 검증 활성화 클라이언트에서 토큰 누락 시 403 차단 및 정상 토큰 200 통과 검증
        csrf_client = Client(enforce_csrf_checks=True)
        index_for_csrf = csrf_client.get("/")
        csrf_token = index_for_csrf.cookies["csrftoken"].value

        blocked_post = csrf_client.post(
            "/api/pillbox/",
            data=json.dumps({"itemSeq": "3001", "itemName": "무토큰정"}),
            content_type="application/json",
        )
        self.assertEqual(blocked_post.status_code, 403)

        allowed_post = csrf_client.post(
            "/api/pillbox/",
            data=json.dumps({"itemSeq": "3001", "itemName": "정상토큰정"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(allowed_post.status_code, 200)

    def test_unified_search_sql_pushdown_and_multi_filters(self) -> None:
        """
        [역할] 낱알 외형 캐시 일괄 Upsert, SQL 푸시다운 다중 필터, 각인 정확 일치 및 검색 로그 누적을 검증합니다.
        [경로] tests.py -> views.api_unified_search() -> services.search_pills_by_appearance()
        [수정] 새로운 외형 조건 파라미터 추가 시 아래 시드 데이터와 쿼리 케이스를 보강하세요.
        """
        upserted = save_grain_items_to_cache(
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
                {
                    "ITEM_SEQ": "20004",
                    "ITEM_NAME": "특수십각형정",
                    "DRUG_SHAPE": "십각형",
                    "COLOR_CLASS1": "파랑",
                    "FORM_CODE_NAME": "나정",
                    "PRINT_FRONT": "DEC",
                    "LINE_FRONT": "+",
                },
            ]
        )
        self.assertEqual(upserted, 4)
        self.assertEqual(PillCache.objects.count(), 4)

        self.assertEqual(self.client.get("/api/unified-search/").status_code, 400)
        self.assertEqual(self.client.get("/api/permission-search/?spclty=전체").status_code, 400)

        # 모양 '원형' 단독 검색 ('타원형' 혼입 방지 및 집계 키 정합성)
        resp_circle = self.client.get("/api/unified-search/?shapes=원형")
        circle_json = resp_circle.json()
        circle_names = {it["itemName"] for it in circle_json["items"]}
        self.assertEqual(circle_names, {"원형노랑정", "원형하양캡슐"})
        self.assertEqual(circle_json["counts"]["grainTotal"], 2)
        self.assertEqual(circle_json["counts"]["mergedCount"], 2)

        # 모양 '기타' 검색 -> 표준 10종 외 모양('십각형') 반환 검증
        resp_other_shape = self.client.get("/api/unified-search/?shapes=기타")
        other_names = {it["itemName"] for it in resp_other_shape.json()["items"]}
        self.assertEqual(other_names, {"특수십각형정"})

        # 모양 '원형' + 제형 '정제' -> 캡슐('경질캡슐제, 과립제정제') 제외 검증
        resp_tablet = self.client.get("/api/unified-search/?shapes=원형&forms=정제")
        tablet_names = [it["itemName"] for it in resp_tablet.json()["items"]]
        self.assertEqual(tablet_names, ["원형노랑정"])

        # 각인 정확 일치(printExact=1) 및 SearchLog 원자적 누적 검증
        self.client.get("/api/unified-search/?print=TY&printExact=1")
        resp_exact = self.client.get("/api/unified-search/?print=TY&printExact=1")
        exact_names = [it["itemName"] for it in resp_exact.json()["items"]]
        self.assertEqual(exact_names, ["원형노랑정"])
        self.assertEqual(SearchLog.objects.get(keyword="각인:TY").count, 2)

    def test_detail_modal_tabs_non_shrinking_and_enrichment_fields(self) -> None:
        """
        [역할] 장문 복약안내 모달의 탭 바 CSS 축소 방지(flex-shrink: 0), ARIA 탭 역할, 상세 병합 필드를 검증합니다.
        [경로] tests.py -> Frontend/style.css, Frontend/app.js, services.enrich_single_drug_detail()
        [수정] 모달 탭 구조 변경 시 role="tablist" 및 flex-shrink 검증 조건을 함께 갱신하세요.
        """
        resp_css = self.client.get("/style.css")
        css_text = b"".join(resp_css.streaming_content).decode("utf-8")
        resp_css.close()

        resp_js = self.client.get("/app.js")
        js_text = b"".join(resp_js.streaming_content).decode("utf-8")
        resp_js.close()

        self.assertIn(".dialog-scroll-body > *", css_text)
        self.assertIn("flex-shrink: 0;", css_text)
        self.assertIn('role: "tablist"', js_text)
        self.assertIn('role: "tabpanel"', js_text)

        PillCache.objects.create(
            item_seq="201111087",
            item_name="메디키넷리타드캡슐40mg(메틸페니데이트염산염)",
            entp_name="명인제약(주)",
            color_class1="보라",
            color_class2="회색",
            etc_otc_name="전문의약품",
        )

        mock_prmsn = (
            [
                {
                    "ITEM_SEQ": "201111087",
                    "ITEM_NAME": "메디키넷리타드캡슐40mg(메틸페니데이트염산염)",
                    "ITEM_INGR_NAME": "메틸페니데이트염산염",
                    "ITEM_INGR_CNT": "1",
                    "ITEM_PERMIT_DATE": "20111216",
                    "INDUTY": "의약품",
                    "BIZRNO": "1234567890",
                    "CANCEL_NAME": "정상",
                }
            ],
            1,
        )
        mock_dtl = (
            [
                {
                    "ITEM_SEQ": "201111087",
                    "ITEM_NAME": "메디키넷리타드캡슐40mg(메틸페니데이트염산염)",
                    "STORAGE_METHOD": "기밀용기, 25℃ 이하 보관",
                    "VALID_TERM": "제조일로부터 36개월",
                    "PACK_UNIT": "30캡슐/병",
                    "EE_DOC_DATA": '<DOC title="효능효과"><SECTION title=""><ARTICLE title="ADHD 치료" /></SECTION></DOC>',
                }
            ],
            1,
        )

        with (
            patch("drugs.services.fetch_easy_drugs", return_value=([], 0)),
            patch("drugs.services.fetch_prmsn_list", return_value=mock_prmsn),
            patch("drugs.services.fetch_prmsn_detail", return_value=mock_dtl),
        ):
            resp = self.client.get("/api/drug-detail/?itemSeq=201111087")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["itemIngrCnt"], "1")
            self.assertEqual(data["storageMethod"], "기밀용기, 25℃ 이하 보관")
            self.assertEqual(data["validTerm"], "제조일로부터 36개월")
            self.assertEqual(data["packUnit"], "30캡슐/병")
            self.assertEqual(data["cancelName"], "정상")
            self.assertIn("ADHD 치료", data["efcyQesitm"])
