"""
================================================================================
[파일명] Backend/config/asgi.py
[역할] 차세대 비동기(Asynchronous) 웹 서버(Uvicorn, Daphne 등) 및 WebSocket 배포 진입점
================================================================================

[백엔드 아키텍처 호출 흐름 (출발지 ➔ 현재 파일 ➔ 목적지)]
1. 출발지 (From):
   - 비동기 서버 실행 시(예: `uvicorn config.asgi:application`) 호출됨
   - `Backend/config/settings.py`의 `ASGI_APPLICATION = "config.asgi.application"`이 이 파일을 가리킴
2. 현재 파일 (config/asgi.py)이 가리키는 목적지 (To):
   - `config.settings` (`Backend/config/settings.py`)를 로드하고
   - HTTP 및 비동기 요청을 `Backend/config/urls.py`로 라우팅하는 `application` 객체를 생성합니다.

[현재 구현된 서비스]
- Django 6.1 표준 ASGI `application` 엔드포인트 구성

[향후 확장(구현) 가능한 서비스 가이드]
- 실시간 복약 알림 푸시나 약사 실시간 상담 채팅(WebSocket) 기능을 추가하고 싶다면,
  `django-channels` 라이브러리를 설치한 뒤 이 파일의 `application`을 `ProtocolTypeRouter`로 감싸도록 확장합니다.
================================================================================
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from django.core.asgi import get_asgi_application

BACKEND_DIR: Path = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# [목적지] Backend/config/settings.py 를 기본 설정 파일로 지정
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# [목적지] 외부 ASGI 서버(Uvicorn 등)가 호출하는 최종 비동기 애플리케이션 객체
application = get_asgi_application()
