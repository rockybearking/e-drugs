"""
[역할] 동기식 운영 웹 서버(Gunicorn, uWSGI 등) 배포용 WSGI 애플리케이션 진입점
[경로] WSGI 서버 구동 -> Backend/config/wsgi.py -> Backend/config/settings.py -> Backend/config/urls.py
[수정] 운영용 설정 모듈을 분리했다면 DJANGO_SETTINGS_MODULE 값을 해당 모듈 경로로 변경하세요.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from django.core.wsgi import get_wsgi_application

BACKEND_DIR: Path = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()
