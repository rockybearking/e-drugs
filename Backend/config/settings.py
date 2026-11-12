"""
[역할] Django 6.1 전역 환경설정 (경로, 보안, CSRF/CSP 미들웨어, SQLite WAL 튜닝, 캐시, 식약처 OpenAPI 인증키·엔드포인트)
[경로] manage.py / wsgi.py / asgi.py -> Backend/config/settings.py -> urls.py, views.py, services.py, models.py
[수정] 운영 배포 시 .env에서 DJANGO_DEBUG="False", DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS를 실제 값으로 변경하세요.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Final
from urllib.parse import unquote

from django.core.exceptions import ImproperlyConfigured
from django.db.backends.signals import connection_created
from django.dispatch import receiver

# [역할] Backend, 프로젝트 루트, Frontend 디렉터리 절대 경로 상수
# [수정] 프론트엔드 폴더명을 바꾸면 FRONTEND_DIR 경로만 변경하세요.
BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent
PROJECT_ROOT: Final[Path] = BASE_DIR.parent
FRONTEND_DIR: Final[Path] = PROJECT_ROOT / "Frontend"

_DEFAULT_MFDS_ENCODED_KEY: Final[str] = (
    "s%2FvWNiKH1YndVRu2mPOq7OXAIj%2Byk0M3JTgvN%2B8UVdSFPq8SBR7zuUdG3mxklTrj6WYIiUidSIUwgE8bz09fzQ%3D%3D"
)
_PLACEHOLDER_PREFIXES: Final[tuple[str, ...]] = (
    "your-",
    "replace-",
    "insert-",
    "example-",
    "<your",
)


def _load_dotenv_fallback(env_path: Path) -> None:
    """
    [역할] python-dotenv 미설치 환경에서 .env 파일을 파싱해 os.environ에 등록합니다.
    [경로] load_project_env() -> _load_dotenv_fallback() -> os.environ
    [수정] 주석 기호를 추가 지원하려면 line.startswith 조건을 수정하세요.
    """
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        clean_key = key.strip()
        clean_val = value.strip().strip('"').strip("'")
        if clean_key:
            os.environ.setdefault(clean_key, clean_val)


def load_project_env() -> None:
    """
    [역할] 루트(.env) 및 Backend(.env) 환경변수 파일을 순서대로 메모리에 적재합니다.
    [경로] settings.py 초기화 -> load_project_env() -> get_env()
    [수정] 시스템 환경변수보다 .env 값을 우선하려면 override=True로 변경하세요.
    """
    env_candidates: tuple[Path, ...] = (PROJECT_ROOT / ".env", BASE_DIR / ".env")
    try:
        from dotenv import load_dotenv

        for env_file in env_candidates:
            if env_file.is_file():
                load_dotenv(dotenv_path=env_file, override=False, interpolate=False)
    except ImportError:
        for env_file in env_candidates:
            _load_dotenv_fallback(env_file)


def get_env(key: str, default: str = "") -> str:
    """
    [역할] 환경변수를 읽고 공백·따옴표를 제거하며, 빈 값이나 예시 문자열이면 default를 반환합니다.
    [경로] os.environ -> get_env() -> SECRET_KEY, ALLOWED_HOSTS, MFDS_API_KEYS 설정
    [수정] 플레이스홀더 접두어를 추가 차단하려면 _PLACEHOLDER_PREFIXES에 등록하세요.
    """
    raw_val = os.environ.get(key, "")
    cleaned = raw_val.strip().strip('"').strip("'") if raw_val else ""
    if not cleaned or cleaned.lower().startswith(_PLACEHOLDER_PREFIXES):
        return default
    return cleaned


def get_env_bool(key: str, default: bool = False) -> bool:
    """
    [역할] 문자열 환경변수("1", "true", "yes", "on")를 bool 타입으로 변환합니다.
    [경로] get_env() -> get_env_bool() -> DEBUG 설정
    [수정] 참(True)으로 인정할 문자열을 늘리려면 집합 항목을 추가하세요.
    """
    return get_env(key, str(default)).lower() in {"1", "true", "yes", "on"}


def normalize_service_key(raw_key: str) -> str:
    """
    [역할] URL 인코딩 키(%2F 등)와 디코딩 원문 키를 모두 urllib.parse 호환 원문 키로 정규화합니다.
    [경로] .env 키 문자열 -> normalize_service_key() -> MFDS_API_KEYS -> Backend/drugs/services.py
    [수정] 별도 키 포맷 검증이 필요하면 return unquote(cleaned) 직전에 검증 로직을 추가하세요.
    """
    if not raw_key:
        return ""
    cleaned = raw_key.strip().strip('"').strip("'")
    if cleaned.lower().startswith(_PLACEHOLDER_PREFIXES):
        return ""
    return unquote(cleaned)


load_project_env()

# 보안 및 호스트 설정
DEBUG: bool = get_env_bool("DJANGO_DEBUG", default=True)

SECRET_KEY: str = get_env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-edrug-care-dev-fallback-secret-key-only"
    else:
        raise ImproperlyConfigured(
            "DEBUG=False 운영 환경에서는 .env에 유효한 DJANGO_SECRET_KEY를 설정해야 합니다."
        )

_default_hosts = "127.0.0.1,localhost,[::1],testserver"
ALLOWED_HOSTS: list[str] = [
    host.strip()
    for host in get_env("DJANGO_ALLOWED_HOSTS", _default_hosts).split(",")
    if host.strip()
]
if DEBUG and "testserver" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("testserver")

SECURE_CONTENT_TYPE_NOSNIFF: bool = True
SECURE_REFERRER_POLICY: str = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS: str = "SAMEORIGIN"
SESSION_COOKIE_HTTPONLY: bool = True
SESSION_COOKIE_SAMESITE: str = "Lax"
CSRF_COOKIE_HTTPONLY: bool = False
CSRF_COOKIE_SAMESITE: str = "Lax"
DATA_UPLOAD_MAX_MEMORY_SIZE: int = 1_048_576

# 앱 및 미들웨어 체인 (경로: 요청 수신 -> MIDDLEWARE -> Backend/config/urls.py)
# [수정] 신규 Django 앱 추가 시 INSTALLED_APPS 끝에 앱 설정 경로를 추가하세요.
INSTALLED_APPS: list[str] = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "drugs.apps.DrugsConfig",
]

MIDDLEWARE: list[str] = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF: str = "config.urls"

TEMPLATES: list[dict[str, Any]] = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [FRONTEND_DIR],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION: str = "config.wsgi.application"
ASGI_APPLICATION: str = "config.asgi.application"

# 데이터베이스(SQLite3) 및 인메모리 캐시 설정 (목적지: Backend/db.sqlite3)
# [수정] PostgreSQL 등으로 전환 시 DATABASES["default"]["ENGINE"] 및 접속 정보를 교체하세요.
DATABASES: dict[str, dict[str, Any]] = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "timeout": 20,
        },
    }
}


@receiver(connection_created)
def _configure_sqlite_pragmas(sender: Any, connection: Any, **kwargs: Any) -> None:
    """
    [역할] SQLite 연결 시 WAL 모드, 메모리 임시 저장소, 20MB 페이지 캐시를 활성화해 읽기·쓰기 속도를 높입니다.
    [경로] connection_created 시그널 -> _configure_sqlite_pragmas() -> Backend/db.sqlite3
    [수정] 메모리 캐시 한도를 조정하려면 cache_size 값(음수는 KB 단위, -20000 = 약 20MB)을 변경하세요.
    """
    if connection.vendor == "sqlite":
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA temp_store=MEMORY;")
            cursor.execute("PRAGMA cache_size=-20000;")
            cursor.execute("PRAGMA busy_timeout=5000;")


# [역할] 식약처 OpenAPI 응답 인메모리 캐시 (목적지: Backend/drugs/services.py)
# [수정] 캐시 유지 시간을 바꾸려면 TIMEOUT(초) 값을 수정하세요.
CACHES: dict[str, dict[str, Any]] = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "edrugs-openapi-cache",
        "TIMEOUT": 600,
    }
}

LANGUAGE_CODE: str = "ko-kr"
TIME_ZONE: str = "Asia/Seoul"
USE_I18N: bool = True
USE_TZ: bool = True

STATIC_URL: str = "/static/"
STATICFILES_DIRS: list[Path] = [FRONTEND_DIR]
STATIC_ROOT: Path = BASE_DIR / "staticfiles"

STORAGES: dict[str, dict[str, str]] = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD: str = "django.db.models.BigAutoField"

# 식약처 공공데이터 3종 인증키 및 엔드포인트 (목적지: Backend/drugs/services.py, views.py)
# [수정] 식약처 API 버전 업그레이드 시 .env 또는 아래 기본 URL 문자열만 변경하세요.
PUBLIC_DATA_API_DECODED_KEY: str = normalize_service_key(
    get_env("PUBLIC_DATA_API_DECODED_KEY")
    or get_env("PUBLIC_DATA_API_KEY")
    or get_env("PUBLIC_DATA_API_ENCODED_KEY", default=_DEFAULT_MFDS_ENCODED_KEY)
)

MFDS_API_KEYS: dict[str, str] = {
    "GRAIN": normalize_service_key(get_env("MFDS_GRAIN_API_KEY")) or PUBLIC_DATA_API_DECODED_KEY,
    "PERMISSION": normalize_service_key(get_env("MFDS_PERMISSION_API_KEY"))
    or PUBLIC_DATA_API_DECODED_KEY,
    "EASY": normalize_service_key(get_env("MFDS_EASY_DRUG_API_KEY")) or PUBLIC_DATA_API_DECODED_KEY,
}

_GRAIN_BASE: str = get_env(
    "MFDS_GRAIN_END_POINT",
    "https://apis.data.go.kr/1471000/MdcinGrnIdntfcInfoService03",
).rstrip("/")
_PRMSN_BASE: str = get_env(
    "MFDS_PERMISSION_END_POINT",
    "https://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService08",
).rstrip("/")
_EASY_BASE: str = get_env(
    "MFDS_EASY_DRUG_END_POINT",
    "https://apis.data.go.kr/1471000/DrbEasyDrugInfoService",
).rstrip("/")

MFDS_ENDPOINTS: dict[str, str] = {
    "GRAIN_BASE": _GRAIN_BASE,
    "GRAIN_LIST": f"{_GRAIN_BASE}/getMdcinGrnIdntfcInfoList03",
    "PRMSN_BASE": _PRMSN_BASE,
    "PRMSN_LIST": f"{_PRMSN_BASE}/getDrugPrdtPrmsnInq08",
    "PRMSN_DETAIL": f"{_PRMSN_BASE}/getDrugPrdtPrmsnDtlInq08",
    "EASY_BASE": _EASY_BASE,
    "EASY_LIST": f"{_EASY_BASE}/getDrbEasyDrugList",
}
