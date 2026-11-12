"""
[역할] 비동기 웹 서버(Uvicorn, Daphne 등) 배포용 ASGI 애플리케이션 진입점
[경로] ASGI 서버 구동 -> Backend/config/asgi.py -> Backend/config/settings.py -> Backend/config/urls.py
[수정] WebSocket 기능을 추가하려면 django-channels의 ProtocolTypeRouter로 application을 감싸세요.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from django.core.asgi import get_asgi_application

BACKEND_DIR: Path = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_asgi_application()
