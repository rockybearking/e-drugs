"""
Django settings for e-Drug Care (알약이가) project.
Django 6.1 기준 최신 설정 구조 및 프로젝트 루트 통합 .env 기반 보안·API 설정 모듈.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote
from django.core.exceptions import ImproperlyConfigured

# 경로 정의
# - BASE_DIR: .../e-drugs/Backend
# - PROJECT_ROOT: .../e-drugs
# - FRONTEND_DIR: .../e-drugs/Frontend
BASE_DIR: Path = Path(__file__).resolve().parent.parent
PROJECT_ROOT: Path = BASE_DIR.parent
FRONTEND_DIR: Path = PROJECT_ROOT / "Frontend"


def _load_dotenv_fallback(env_path: Path) -> None:
    """python-dotenv 패키지가 없는 환경에서도 .env 파일을 파싱하여 os.environ에 등록합니다."""
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def load_project_env() -> None:
    """프로젝트 루트(.env) 및 Backend 폴더(.env)에서 환경변수를 통합 로드합니다."""
    env_candidates = (PROJECT_ROOT / ".env", BASE_DIR / ".env")
    try:
        from dotenv import load_dotenv

        for env_file in env_candidates:
            if env_file.is_file():
                load_dotenv(dotenv_path=env_file, override=False, interpolate=False)
    except ImportError:
        for env_file in env_candidates:
            _load_dotenv_fallback(env_file)


def get_env(key: str, default: str = "") -> str:
    """환경변수 값을 안전하게 읽고 불필요한 공백 및 따옴표를 제거합니다."""
    val = os.environ.get(key, default)
    return val.strip().strip('"').strip("'") if val else default


def get_env_bool(key: str, default: bool = False) -> bool:
    """문자열 환경변수를 파이썬 불리언(bool) 값으로 변환합니다."""
    raw = get_env(key, str(default)).lower()
    return raw in {"1", "true", "yes", "on"}


def normalize_service_key(raw_key: str) -> str:
    """
    공공데이터포털 API 인증키 정규화 함수.
    .env에 URL Encoded 키(%2F, %2B, %3D 포함) 또는 Decoded 원문 키 어느 쪽을 넣더라도
    requests 라이브러리의 params 인코딩 시 이중 인코딩(Error 30)이 발생하지 않도록 원문 키로 통일합니다.
    """
    if not raw_key:
        return ""
    return unquote(raw_key.strip())


# .env 환경변수 즉시 로드
load_project_env()

# 보안 및 디버그 설정
DEBUG: bool = get_env_bool("DJANGO_DEBUG", default=True)

SECRET_KEY: str = get_env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-dev-fallback-only-set-in-dotenv"
    else:
        raise ImproperlyConfigured("운영 환경(DEBUG=False)에서는 .env에 DJANGO_SECRET_KEY가 반드시 설정되어야 합니다.")

ALLOWED_HOSTS: list[str] = [
    host.strip()
    for host in get_env("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,*").split(",")
    if host.strip()
]

# 애플리케이션 정의
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "drugs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
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

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# SQLite3 데이터베이스 설정 (WAL 저널 모드 및 타임아웃 최적화로 동시 읽기/쓰기 성능 향상)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "timeout": 20,
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
    }
}

# 인메모리 캐시 (반복적인 식약처 OpenAPI 호출 지연 최소화)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "edrugs-openapi-cache",
        "TIMEOUT": 600,  # 10분 캐싱
    }
}

# 국제화 및 시간대
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

# 정적 파일 및 Django 6.x 표준 STORAGES 설정
STATIC_URL = "/static/"
STATICFILES_DIRS = [FRONTEND_DIR]
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ==============================================================================
# 공공데이터포털 식약처 3대 OpenAPI 통합 설정 (.env 연동)
# ==============================================================================
PUBLIC_DATA_API_ENCODED_KEY: str = get_env("PUBLIC_DATA_API_ENCODED_KEY")
PUBLIC_DATA_API_DECODED_KEY: str = normalize_service_key(
    get_env("PUBLIC_DATA_API_DECODED_KEY")
    or get_env("PUBLIC_DATA_API_KEY")
    or PUBLIC_DATA_API_ENCODED_KEY
)

MFDS_API_KEYS: dict[str, str] = {
    "GRAIN": normalize_service_key(get_env("MFDS_GRAIN_API_KEY")) or PUBLIC_DATA_API_DECODED_KEY,
    "PERMISSION": normalize_service_key(get_env("MFDS_PERMISSION_API_KEY")) or PUBLIC_DATA_API_DECODED_KEY,
    "EASY": normalize_service_key(get_env("MFDS_EASY_DRUG_API_KEY")) or PUBLIC_DATA_API_DECODED_KEY,
}

# 하위 호환 상수
MFDS_SERVICE_KEY_ENCODED: str = PUBLIC_DATA_API_ENCODED_KEY
MFDS_SERVICE_KEY_DECODED: str = PUBLIC_DATA_API_DECODED_KEY

_GRAIN_BASE = get_env(
    "MFDS_GRAIN_END_POINT",
    "https://apis.data.go.kr/1471000/MdcinGrnIdntfcInfoService03",
).rstrip("/")
_PRMSN_BASE = get_env(
    "MFDS_PERMISSION_END_POINT",
    "https://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService08",
).rstrip("/")
_EASY_BASE = get_env(
    "MFDS_EASY_DRUG_END_POINT",
    "https://apis.data.go.kr/1471000/DrbEasyDrugInfoService",
).rstrip("/")

MFDS_ENDPOINTS: dict[str, str] = {
    # 1. 식품의약품안전처_의약품 낱알식별 정보
    "GRAIN_BASE": _GRAIN_BASE,
    "GRAIN_LIST": f"{_GRAIN_BASE}/getMdcinGrnIdntfcInfoList03",
    # 2. 식품의약품안전처_의약품 제품 허가정보
    "PRMSN_BASE": _PRMSN_BASE,
    "PRMSN_LIST": f"{_PRMSN_BASE}/getDrugPrdtPrmsnInq08",
    "PRMSN_DETAIL": f"{_PRMSN_BASE}/getDrugPrdtPrmsnDtlInq08",
    # 3. 식품의약품안전처_의약품개요정보(e약은요)
    "EASY_BASE": _EASY_BASE,
    "EASY_LIST": f"{_EASY_BASE}/getDrbEasyDrugList",
}
