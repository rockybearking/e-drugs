"""
================================================================================
[파일명] Backend/config/wsgi.py
[역할] 운영 환경 동기식(Synchronous) 웹 서버(Gunicorn, uWSGI 등) 배포 진입점
================================================================================

[백엔드 아키텍처 호출 흐름 (출발지 ➔ 현재 파일 ➔ 목적지)]
1. 출발지 (From):
   - 리눅스/클라우드 운영 서버에서 `gunicorn config.wsgi:application` 명령으로 실행할 때 호출됨
   - 또한 `Backend/config/settings.py`의 `WSGI_APPLICATION = "config.wsgi.application"`이 이 파일을 가리킴
2. 현재 파일 (config/wsgi.py)이 가리키는 목적지 (To):
   - `config.settings` (`Backend/config/settings.py`)를 읽어 Django 환경을 초기화한 뒤,
   - `get_wsgi_application()`을 통해 HTTP 요청을 `Backend/config/urls.py`로 전달하는 `application` 객체를 생성합니다.

[현재 구현된 서비스]
- `Backend` 폴더 경로 자동 등록 및 WSGI 표준 `application` 핸들러 노출

[향후 확장(구현) 가능한 서비스 가이드]
- 운영 서버에서 정적 파일을 Nginx 없이 직접 서빙하려면 `whitenoise` 패키지를 설치하고
  `Backend/config/settings.py`의 `MIDDLEWARE`에 `WhiteNoiseMiddleware`를 추가하면 이 WSGI 서버가 고속 처리합니다.
================================================================================
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from django.core.wsgi import get_wsgi_application

BACKEND_DIR: Path = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# [목적지] Backend/config/settings.py 를 기본 설정 파일로 지정
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# [목적지] 외부 WSGI 서버(Gunicorn 등)가 호출하는 최종 Django 애플리케이션 객체
application = get_wsgi_application()
