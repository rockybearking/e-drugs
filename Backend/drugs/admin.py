"""
================================================================================
[파일명] Backend/drugs/admin.py
[역할] Django 기본 관리자 페이지(`http://127.0.0.1:8000/admin/`)에 DB 모델을 등록하고 화면 구성을 정의하는 모듈
================================================================================

[백엔드 아키텍처 호출 흐름 (출발지 ➔ 현재 파일 ➔ 목적지)]
1. 출발지 (From):
   - 브라우저에서 `/admin/` 접속 ➔ `Backend/config/urls.py`의 `path("admin/", admin.site.urls)`가 호출됨
2. 현재 파일 (drugs/admin.py)이 가리키는 목적지 (To):
   - `from .models import PillCache, SavedDrug, SearchLog`를 통해 `Backend/drugs/models.py`의
     3개 모델 클래스를 가져와 관리자 대시보드에 표(Table) 형태로 노출합니다.

[현재 구현된 서비스]
- `PillCacheAdmin`: 낱알식별 캐시 데이터의 목록 컬럼(`list_display`), 검색창(`search_fields`), 우측 필터(`list_filter`) 제공
- `SavedDrugAdmin`: 내 약통 보관 의약품 조회·검색·삭제 관리
- `SearchLogAdmin`: 인기 검색어 로그 확인 및 검색 유형별 필터링

[향후 확장(구현) 가능한 서비스 가이드]
- 관리자 페이지에서 선택한 여러 약품을 한 번에 CSV/Excel로 다운로드하는 기능을 추가하고 싶다면,
  `ModelAdmin` 내부에 `actions = ["export_as_csv"]` 메서드를 정의하여 손쉽게 추가할 수 있습니다.
- 관리자 계정 생성 방법: 터미널에서 `python Backend/manage.py createsuperuser`를 실행하세요.
================================================================================
"""
from __future__ import annotations

from django.contrib import admin

from .models import PillCache, SavedDrug, SearchLog


@admin.register(PillCache)
class PillCacheAdmin(admin.ModelAdmin):
    """
    [역할] `Backend/drugs/models.py`의 `PillCache` 모델을 관리자 화면에 표시하는 설정입니다.
    [수정 가이드]
    - 관리자 목록 표에 '제형코드명(`form_code_name`)' 컬럼을 추가로 보여주고 싶다면:
      아래 `list_display` 튜플에 `"form_code_name"`을 추가하세요.
    """

    list_display = (
        "item_seq",
        "item_name",
        "entp_name",
        "drug_shape",
        "color_class1",
        "print_front",
        "print_back",
        "etc_otc_name",
    )
    search_fields = ("item_name", "entp_name", "print_front", "print_back", "item_seq")
    list_filter = ("drug_shape", "color_class1", "etc_otc_name")


@admin.register(SavedDrug)
class SavedDrugAdmin(admin.ModelAdmin):
    """
    [역할] `Backend/drugs/models.py`의 `SavedDrug` (내 약통) 모델을 관리자 화면에 표시하는 설정입니다.
    """

    list_display = ("item_name", "entp_name", "etc_otc_name", "dosage_time", "created_at")
    search_fields = ("item_name", "entp_name", "ingr_name")


@admin.register(SearchLog)
class SearchLogAdmin(admin.ModelAdmin):
    """
    [역할] `Backend/drugs/models.py`의 `SearchLog` (검색 통계) 모델을 관리자 화면에 표시하는 설정입니다.
    """

    list_display = ("keyword", "search_type", "count", "last_searched_at")
    list_filter = ("search_type",)
