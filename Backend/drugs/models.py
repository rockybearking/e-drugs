"""
[역할] SQLite 데이터베이스(Backend/db.sqlite3) ORM 테이블 스키마 정의 (PillCache, SavedDrug, SearchLog)
[경로] Backend/drugs/services.py · views.py · admin.py -> Backend/drugs/models.py -> Backend/db.sqlite3
[수정] 필드 추가·변경 후에는 반드시 `python Backend/manage.py makemigrations && python Backend/manage.py migrate`를 실행하세요.
"""
from __future__ import annotations

from django.db import models


class PillCache(models.Model):
    """
    [역할] 식약처 낱알식별 외형 데이터 로컬 캐시 및 고속 복합 조건 검색용 테이블
    [경로] services.py (save_grain_items_to_cache / search_pills_by_appearance) <-> drugs_pillcache 테이블
    [수정] 캐싱 컬럼을 추가하려면 필드 선언 후 services.py의 _PILL_CACHE_UPDATE_FIELDS에도 컬럼명을 추가하세요.
    """

    item_seq = models.CharField("품목기준코드", max_length=32, unique=True, db_index=True)
    item_name = models.CharField("품목명", max_length=255, db_index=True)
    entp_name = models.CharField("업체명", max_length=150, blank=True, default="")
    chart = models.TextField("성상(외형설명)", blank=True, default="")
    item_image = models.URLField("낱알 이미지 URL", max_length=500, blank=True, default="")
    print_front = models.CharField("표시(앞)", max_length=100, blank=True, default="", db_index=True)
    print_back = models.CharField("표시(뒤)", max_length=100, blank=True, default="", db_index=True)
    drug_shape = models.CharField("의약품 모양", max_length=50, blank=True, default="", db_index=True)
    color_class1 = models.CharField("색상(앞)", max_length=50, blank=True, default="", db_index=True)
    color_class2 = models.CharField("색상(뒤)", max_length=50, blank=True, default="")
    line_front = models.CharField("분할선(앞)", max_length=50, blank=True, default="")
    line_back = models.CharField("분할선(뒤)", max_length=50, blank=True, default="")
    leng_long = models.CharField("크기(장축 mm)", max_length=30, blank=True, default="")
    leng_short = models.CharField("크기(단축 mm)", max_length=30, blank=True, default="")
    thick = models.CharField("크기(두께 mm)", max_length=30, blank=True, default="")
    class_no = models.CharField("분류번호", max_length=30, blank=True, default="")
    class_name = models.CharField("약효분류명", max_length=120, blank=True, default="")
    etc_otc_name = models.CharField("전문/일반구분", max_length=50, blank=True, default="")
    form_code_name = models.CharField("제형코드명", max_length=80, blank=True, default="", db_index=True)
    item_eng_name = models.CharField("영문품목명", max_length=255, blank=True, default="")
    edi_code = models.CharField("보험코드(EDI)", max_length=50, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "낱알식별 캐시 데이터"
        verbose_name_plural = "낱알식별 캐시 데이터 목록"
        ordering = ["item_name"]

    def __str__(self) -> str:
        return f"[{self.item_seq}] {self.item_name} ({self.drug_shape}/{self.color_class1})"


class SavedDrug(models.Model):
    """
    [역할] '내 약통' 보관 의약품 CRUD 및 주성분 중복 점검용 테이블
    [경로] Frontend/app.js -> views.py (api_pillbox / _build_safety_report) <-> drugs_saveddrug 테이블
    [수정] 기본 복용 시간대 문구를 바꾸려면 dosage_time의 default 값을 수정하세요.
    """

    item_seq = models.CharField("품목기준코드", max_length=32, db_index=True)
    item_name = models.CharField("품목명", max_length=255)
    entp_name = models.CharField("업체명", max_length=150, blank=True, default="")
    item_image = models.URLField("의약품 이미지", max_length=500, blank=True, default="")
    etc_otc_name = models.CharField("전문/일반 구분", max_length=50, blank=True, default="")
    class_name = models.CharField("약효분류", max_length=120, blank=True, default="")
    ingr_name = models.TextField("주성분명", blank=True, default="")
    efcy_text = models.TextField("효능·효과 요약", blank=True, default="")
    use_method_text = models.TextField("복용법 요약", blank=True, default="")
    warn_text = models.TextField("주의사항 및 상호작용", blank=True, default="")
    dosage_time = models.CharField(
        "복용 시간대", max_length=100, blank=True, default="아침, 저녁 식후 30분"
    )
    memo = models.CharField("복용 메모", max_length=255, blank=True, default="")
    created_at = models.DateTimeField("등록일시", auto_now_add=True)

    class Meta:
        verbose_name = "내 약통 보관 의약품"
        verbose_name_plural = "내 약통 보관 의약품 목록"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.item_name} ({self.dosage_time})"


class SearchLog(models.Model):
    """
    [역할] 검색 키워드 및 누적 조회 횟수 집계 테이블
    [경로] views.py (_record_search_log / api_status) <-> drugs_searchlog 테이블
    [수정] 정렬 기준을 최근 검색순 우선으로 바꾸려면 Meta.ordering 첫 항목을 "-last_searched_at"으로 변경하세요.
    """

    keyword = models.CharField("검색 키워드", max_length=100, db_index=True)
    search_type = models.CharField("검색 유형", max_length=30, default="unified")
    count = models.PositiveIntegerField("검색 횟수", default=1)
    last_searched_at = models.DateTimeField("최근 검색일시", auto_now=True)

    class Meta:
        verbose_name = "검색 로그"
        verbose_name_plural = "검색 로그 목록"
        ordering = ["-count", "-last_searched_at"]

    def __str__(self) -> str:
        return f"{self.keyword} ({self.count}회)"
