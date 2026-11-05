"""
================================================================================
[파일명] Backend/drugs/apps.py
[역할] `drugs` 애플리케이션의 메타데이터 및 설정 클래스(`DrugsConfig`) 정의 모듈
================================================================================

[백엔드 아키텍처 호출 흐름 (출발지 ➔ 현재 파일 ➔ 목적지)]
1. 출발지 (From):
   - `Backend/config/settings.py`의 `INSTALLED_APPS`에 선언된 `"drugs.apps.DrugsConfig"`가
     이 파일의 `DrugsConfig` 클래스를 직접 가리킵니다.
2. 현재 파일 (drugs/apps.py)이 가리키는 목적지 (To):
   - `name = "drugs"` 설정을 통해 `Backend/drugs/` 폴더 안의 `models.py`, `admin.py`,
     `migrations/`를 Django 프레임워크에 등록합니다.

[현재 구현된 서비스]
- 기본 기본키(Primary Key) 타입을 64비트 정수(`BigAutoField`)로 지정
- 관리자(`/admin/`) 페이지에 표시될 한글 앱 이름(`verbose_name`) 지정

[향후 확장(구현) 가능한 서비스 가이드]
- 서버가 켜질 때 자동으로 실행할 초기화 작업(예: 시그널 등록)이 필요하다면,
  `DrugsConfig` 클래스 내부에 `def ready(self) -> None:` 메서드를 정의하여 구현할 수 있습니다.
================================================================================
"""
from __future__ import annotations

from django.apps import AppConfig


class DrugsConfig(AppConfig):
    """
    [역할] `drugs` 앱의 설정 정보를 담는 구성 클래스입니다.
    [수정 가이드]
    - 관리자 페이지(`/admin/`) 좌측 메뉴에 표시되는 섹션 제목을 바꾸고 싶다면:
      아래 `verbose_name` 문자열을 원하는 이름으로 변경하세요.
    """

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "drugs"
    verbose_name: str = "식약처 3대 OpenAPI 통합 의약품 서비스"
