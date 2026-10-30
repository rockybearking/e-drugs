from django.contrib import admin
from .models import PillCache, SavedDrug, SearchLog


@admin.register(PillCache)
class PillCacheAdmin(admin.ModelAdmin):
    list_display = ("item_seq", "item_name", "entp_name", "drug_shape", "color_class1", "print_front", "print_back", "etc_otc_name")
    search_fields = ("item_name", "entp_name", "print_front", "print_back", "item_seq")
    list_filter = ("drug_shape", "color_class1", "etc_otc_name")


@admin.register(SavedDrug)
class SavedDrugAdmin(admin.ModelAdmin):
    list_display = ("item_name", "entp_name", "etc_otc_name", "dosage_time", "created_at")
    search_fields = ("item_name", "entp_name", "ingr_name")


@admin.register(SearchLog)
class SearchLogAdmin(admin.ModelAdmin):
    list_display = ("keyword", "search_type", "count", "last_searched_at")
    list_filter = ("search_type",)
