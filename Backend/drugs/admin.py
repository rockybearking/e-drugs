"""
[역할] Django 관리자(/admin/) 화면에 PillCache, SavedDrug, SearchLog 모델을 등록하고 목록·검색 구성을 정의
[경로] 브라우저 /admin/ 접속 -> Backend/config/urls.py -> Backend/drugs/admin.py -> Backend/drugs/models.py
[수정] 관리자 표에 노출할 컬럼을 바꾸려면 각 ModelAdmin의 list_display 튜플을 수정하세요.
"""
from __future__ import annotations

from django.contrib import admin

from .models import PillCache, SavedDrug, SearchLog


@admin.register(PillCache)
class PillCacheAdmin(admin.ModelAdmin):
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
    list_display = ("item_name", "entp_name", "etc_otc_name", "dosage_time", "memo", "created_at")
    search_fields = ("item_name", "entp_name", "ingr_name", "memo")


@admin.register(SearchLog)
class SearchLogAdmin(admin.ModelAdmin):
    list_display = ("keyword", "search_type", "count", "last_searched_at")
    list_filter = ("search_type",)
