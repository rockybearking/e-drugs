"""
[역할] drugs 앱 메타데이터(기본 PK 타입, 앱 이름, 관리자 표시명) 정의
[경로] Backend/config/settings.py (INSTALLED_APPS) -> Backend/drugs/apps.py -> models.py, admin.py 등록
[수정] /admin/ 화면의 앱 섹션 제목을 바꾸려면 verbose_name 문자열을 변경하세요.
"""
from __future__ import annotations

from django.apps import AppConfig


class DrugsConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "drugs"
    verbose_name: str = "식약처 공공데이터 통합 의약품 서비스"
