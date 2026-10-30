from django.db import models


class PillCache(models.Model):
    """
    식약처 의약품 낱알식별 정보(MdcinGrnIdntfcInfoService03) 로컬 캐시 및 고속 필터링 테이블.
    공공데이터 API가 모양/색상/각인 단독 검색을 서버단에서 직접 지원하지 않는 한계를 극복하기 위해
    Django SQLite DB에 인덱싱하여 약 이름을 몰라도 외형만으로 즉시 식별할 수 있게 합니다.
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

    def __str__(self):
        return f"[{self.item_seq}] {self.item_name} ({self.drug_shape}/{self.color_class1})"


class SavedDrug(models.Model):
    """
    사용자 맞춤형 '내 약통 (복약 수첩)' 저장 모델.
    복용 중인 의약품 등록, 복용 시간대, 개인 메모 및 주성분 중복·상호작용 안전 점검에 활용됩니다.
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
    dosage_time = models.CharField("복용 시간대", max_length=100, blank=True, default="아침, 저녁 식후 30분")
    memo = models.CharField("복용 메모", max_length=255, blank=True, default="")
    created_at = models.DateTimeField("등록일시", auto_now_add=True)

    class Meta:
        verbose_name = "내 약통 보관 의약품"
        verbose_name_plural = "내 약통 보관 의약품 목록"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.item_name} ({self.dosage_time})"


class SearchLog(models.Model):
    """
    인기 검색어 및 최근 검색 통계 집계용 모델.
    """
    keyword = models.CharField("검색 키워드", max_length=100, db_index=True)
    search_type = models.CharField("검색 유형", max_length=30, default="unified")  # unified, grain, prmsn, easy
    count = models.PositiveIntegerField("검색 횟수", default=1)
    last_searched_at = models.DateTimeField("최근 검색일시", auto_now=True)

    class Meta:
        verbose_name = "검색 로그"
        verbose_name_plural = "검색 로그 목록"
        ordering = ["-count", "-last_searched_at"]

    def __str__(self):
        return f"{self.keyword} ({self.count}회)"
