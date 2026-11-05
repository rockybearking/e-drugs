"""
================================================================================
[파일명] Backend/drugs/models.py
[역할] 데이터베이스(`Backend/db.sqlite3`) 테이블 스키마를 파이썬 클래스로 정의하는 ORM 모델 모듈
================================================================================

[백엔드 초보자를 위한 ORM(Object-Relational Mapping) 개념 및 연결 구조]
- SQL 쿼리(`CREATE TABLE ...`, `SELECT * FROM ...`)를 직접 작성하지 않아도,
  이 파일에 파이썬 클래스(`models.Model` 상속)를 작성하면 Django가 자동으로 데이터베이스 테이블과 연결해 줍니다.
- **이 파일을 가리키는 출발지 / 참조하는 목적지 파일들**:
  1. [참조 1] `Backend/drugs/migrations/0001_initial.py`:
     이 파일의 클래스 정의를 바탕으로 실제 `Backend/db.sqlite3`에 테이블을 생성하는 설계도입니다.
  2. [참조 2] `Backend/drugs/services.py`:
     - `save_grain_items_to_cache()`, `unified_drug_search()`, `enrich_single_drug_detail()`,
       `search_pills_by_appearance()` 함수가 `PillCache` 모델을 import하여 데이터를 저장·조회합니다.
  3. [참조 3] `Backend/drugs/views.py`:
     - `api_status()`가 `PillCache`, `SavedDrug`, `SearchLog` 개수를 조회합니다.
     - `_record_search_log()`가 `SearchLog` 테이블에 검색 횟수를 누적합니다.
     - `api_pillbox()`가 `SavedDrug` 테이블에서 '내 약통' 데이터를 조회(GET)·추가(POST)·삭제(DELETE)합니다.
  4. [참조 4] `Backend/drugs/admin.py`:
     - `PillCache`, `SavedDrug`, `SearchLog` 3개 모델을 `/admin/` 관리자 화면에 등록합니다.

[현재 구현된 서비스 (테이블 3종)]
1. `PillCache` (실제 DB 테이블명: `drugs_pillcache`):
   - 식약처 의약품 낱알식별 API 데이터를 로컬 SQLite에 캐싱하고 인덱싱하여,
     약 이름을 몰라도 모양·색상·제형·분할선·각인만으로 0.01초 내에 외형 식별이 가능하도록 지원합니다.
2. `SavedDrug` (실제 DB 테이블명: `drugs_saveddrug`):
   - 사용자가 '내 약통'에 담은 복용 의약품 목록과 복용 시간대, 주성분명(`ingr_name`), 주의사항을 저장하여
     주성분 중복 복용 위험을 분석합니다.
3. `SearchLog` (실제 DB 테이블명: `drugs_searchlog`):
   - 사용자가 검색한 키워드와 검색 횟수를 누적 기록하여 인기 검색어 통계를 제공합니다.

[향후 확장(구현) 가능한 서비스 가이드]
- **회원별 약통 분리**: `SavedDrug` 모델에 `user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)`
  필드를 추가하면 로그인한 사용자마다 각자의 약통을 독립적으로 관리할 수 있습니다.
- **복약 알림 이력 모델(`DosageAlarmLog`) 추가**: 아침/점심/저녁 복약 체크 여부를 날짜별로 기록하는 테이블을 추가할 수 있습니다.

[중요! 모델을 수정했을 때 반드시 실행해야 하는 명령어]
- 이 파일에서 필드를 추가하거나 `max_length` 등을 수정한 뒤에는 터미널에서 아래 두 명령어를 순서대로 실행해야
  `Backend/db.sqlite3`에 실제 반영됩니다:
  1) `python Backend/manage.py makemigrations` (변경 설계도 파일 생성)
  2) `python Backend/manage.py migrate` (실제 SQLite DB 테이블에 적용)
================================================================================
"""
from __future__ import annotations

from django.db import models


class PillCache(models.Model):
    """
    [역할]
    - 식약처 의약품 낱알식별 정보(`MdcinGrnIdntfcInfoService03`)의 로컬 캐시 및 고속 외형 검색 테이블입니다.
    - 공공데이터포털 API는 모양/색상/분할선 단독 필터링을 서버단에서 직접 지원하지 않거나 느리기 때문에,
      수집된 낱알 정보를 SQLite 인덱스(`db_index=True`)가 걸린 이 테이블에 저장해 고속 필터링합니다.

    [연결 파일 (어디서 사용되는가)]
    - `Backend/drugs/services.py`의 `save_grain_items_to_cache()`에서 `PillCache.objects.bulk_create()`로 저장
    - `Backend/drugs/services.py`의 `search_pills_by_appearance()`, `unified_drug_search()`,
      `enrich_single_drug_detail()`에서 조회
    - `Backend/drugs/views.py`의 `api_status()`, `api_grain_search()`에서 전체 캐시 건수(`count()`) 확인

    [수정 가이드]
    - 예를 들어 알약의 '마약류 구분코드(`narcotic_kind`)' 컬럼을 추가로 저장하고 싶다면:
      1) 아래 필드에 `narcotic_kind = models.CharField("마약류구분", max_length=50, blank=True, default="")` 추가
      2) `Backend/drugs/services.py`의 `_PILL_CACHE_UPDATE_FIELDS`와 `save_grain_items_to_cache()`에 매핑 추가
      3) `python Backend/manage.py makemigrations && python Backend/manage.py migrate` 실행
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
    [역할]
    - 사용자 맞춤형 '내 약통 (복약 수첩)' 저장 테이블입니다.
    - 사용자가 복용 중인 의약품을 등록하면 주성분명(`ingr_name`)과 복용 시간대(`dosage_time`)를 보관하여,
      여러 약 사이에 동일한 주성분이 중복되는지 자동 점검하는 데 사용됩니다.

    [연결 파일 (어디서 사용되는가)]
    - `Backend/drugs/views.py`의 `api_pillbox()` 뷰 함수에서 조회(GET), 생성/수정(POST), 삭제(DELETE) 수행
    - `Backend/drugs/views.py`의 `_build_safety_report()`에서 `ingr_name` 필드를 분석하여 중복 위험 리포트 생성
    - 프론트엔드 `Frontend/app.js`의 `loadPillbox()`, `addToPillbox()`, `removeFromPillbox()`와 1:1 연동

    [수정 가이드]
    - 기본 복용 시간대 문구를 바꾸고 싶다면 `dosage_time` 필드의 `default="아침, 저녁 식후 30분"` 값을 변경하세요.
    - 정렬 순서를 최신 등록순(`-created_at`)에서 가나다 품목명순으로 바꾸고 싶다면:
      `class Meta:` 내부의 `ordering = ["item_name"]`으로 변경하세요.
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
    [역할]
    - 사용자가 검색창에 입력한 키워드(`keyword`)와 검색 횟수(`count`)를 누적 집계하는 통계 테이블입니다.

    [연결 파일 (어디서 사용되는가)]
    - `Backend/drugs/views.py`의 `_record_search_log()`에서 검색 발생 시마다 `count`를 1씩 증가
    - `Backend/drugs/views.py`의 `api_status()`에서 상위 8개 인기 검색어를 조회하여 반환
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
