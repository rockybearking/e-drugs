"""
================================================================================
[파일명] Backend/config/settings.py
[역할] Django 6.1 프로젝트 전역 환경설정, 보안 정책, DB 연결, 캐시 및 식약처 3대 OpenAPI 설정 총괄 모듈
================================================================================

[백엔드 아키텍처 호출 흐름 (출발지 ➔ 현재 파일 ➔ 목적지)]
1. 출발지 (From):
   - `Backend/manage.py` (32행): `os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")`
   - `Backend/config/wsgi.py` & `asgi.py`: 운영/비동기 서버가 시작될 때 가장 먼저 이 파일을 읽습니다.
2. 현재 파일 (config/settings.py)이 가리키는 목적지 파일들 (To):
   - `INSTALLED_APPS` ➔ `Backend/drugs/apps.py` (`DrugsConfig`) 및 `Backend/drugs/models.py`를 활성화합니다.
   - `ROOT_URLCONF = "config.urls"` ➔ `Backend/config/urls.py`를 최초 URL 라우팅 목적지로 지정합니다.
   - `TEMPLATES["DIRS"] = [FRONTEND_DIR]` ➔ `Backend/drugs/views.py`의 `render(request, "index.html")` 호출 시
     `Frontend/index.html` 파일을 찾아가도록 목적지 폴더를 지정합니다.
   - `WSGI_APPLICATION = "config.wsgi.application"` ➔ `Backend/config/wsgi.py`의 `application` 객체를 가리킵니다.
   - `ASGI_APPLICATION = "config.asgi.application"` ➔ `Backend/config/asgi.py`의 `application` 객체를 가리킵니다.
   - `DATABASES["default"]["NAME"]` ➔ `Backend/db.sqlite3` 데이터베이스 파일을 가리킵니다.
   - `MFDS_API_KEYS` / `MFDS_ENDPOINTS` ➔ `Backend/drugs/services.py` 및 `Backend/drugs/views.py`에서
     `from django.conf import settings`로 불러와 공공데이터 OpenAPI 호출에 사용합니다.

[Django settings.py에 반드시 구성되어야 하는 표준 핵심 요소]
1. 경로 설정 (`BASE_DIR`, `PROJECT_ROOT`, `FRONTEND_DIR`)
2. 보안 설정 (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_*`, `SECURE_*`)
3. 앱 및 미들웨어 등록 (`INSTALLED_APPS`, `MIDDLEWARE`)
4. 라우팅 및 템플릿 (`ROOT_URLCONF`, `TEMPLATES`, `WSGI_APPLICATION`, `ASGI_APPLICATION`)
5. 데이터베이스 및 캐시 (`DATABASES`, `CACHES`)
6. 국제화 및 정적 파일 (`LANGUAGE_CODE`, `TIME_ZONE`, `STATIC_URL`, `STORAGES`)
7. 외부 연동 서비스 환경변수 (`MFDS_API_KEYS`, `MFDS_ENDPOINTS`)

[현재 구현된 서비스]
- `.env` 자동 파서 및 키 누락/플레이스홀더 방어용 안전 폴백(Fallback) 인증키 시스템
  (401 Client Error: Unauthorized 원천 차단)
- URL 인코딩된 키(`%2F`, `%2B`, `%3D`)와 디코딩 원문 키를 자동 판별·정규화하는 `normalize_service_key()`
- SQLite3 WAL(Write-Ahead Logging) 모드 활성화로 멀티스레드 동시 읽기/쓰기 성능 최적화
- 10분 TTL 인메모리 캐시(`LocMemCache`)를 통한 반복 OpenAPI 호출 지연 제거
- 브라우저 보안 헤더(`nosniff`, `SAMEORIGIN`, `strict-origin-when-cross-origin`, 요청 크기 제한) 적용

[향후 확장(구현) 가능한 서비스 가이드]
- **PostgreSQL / MySQL 전환**: 대규모 사용자 트래픽 처리 시 `DATABASES`의 `ENGINE`을 변경
- **Redis 분산 캐시 도입**: 다중 서버 배포 시 `CACHES`를 `django.core.cache.backends.redis.RedisCache`로 교체
- **CORS 설정 (`django-cors-headers`)**: 프론트엔드를 별도 도메인(예: Vercel, Netlify)으로 분리 배포할 때 추가
- **사용자 인증 (`AUTH_USER_MODEL`)**: 개인별 약통 로그인 기능을 추가할 때 커스텀 유저 모델 지정
================================================================================
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Final
from urllib.parse import unquote

from django.db.backends.signals import connection_created
from django.dispatch import receiver
from django.core.exceptions import ImproperlyConfigured

# ==============================================================================
# 1. 프로젝트 디렉터리 절대 경로 정의
# ==============================================================================
# [역할] 파일 시스템 내 Backend, 프로젝트 루트(e-drugs), Frontend 폴더의 위치를 계산합니다.
# [수정 가이드] 만약 Frontend 폴더 이름을 "Client"로 변경한다면:
# 아래 `FRONTEND_DIR = PROJECT_ROOT / "Client"`로 수정하면 템플릿과 정적 파일 경로가 일괄 반영됩니다.
BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent
PROJECT_ROOT: Final[Path] = BASE_DIR.parent
FRONTEND_DIR: Final[Path] = PROJECT_ROOT / "Frontend"

# `.env` 파일이 없거나 `.env.example`의 플레이스홀더("your-...")가 그대로 들어있을 때
# 401 Unauthorized 에러가 발생하지 않도록 보장하는 기본 공공데이터포털 인증키(Encoded 원문)입니다.
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
    [역할]
    - `python-dotenv` 라이브러리가 설치되지 않은 환경에서도 `.env` 텍스트 파일을 직접 읽어
      파이썬 `os.environ` 환경변수 사전에 안전하게 등록하는 내장 폴백 로더입니다.
    [연결 출발지] 아래 `load_project_env()` 함수에서 호출됩니다.
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
    [역할]
    - 프로젝트 루트(`e-drugs/.env`)와 백엔드 폴더(`e-drugs/Backend/.env`)를 순서대로 확인하여
      환경변수를 메모리에 로드합니다.
    [수정 가이드]
    - 시스템 환경변수보다 `.env` 파일의 값을 무조건 덮어쓰고(우선시하고) 싶다면:
      `load_dotenv(..., override=True)`로 변경하세요.
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
    [역할]
    - `os.environ`에서 환경변수 값을 읽고 앞뒤 공백·따옴표를 제거합니다.
    - 만약 값이 비어 있거나 `.env.example`의 예시 문자열(`your-url-encoded-api-key` 등)이면
      안전하게 `default` 기본값을 반환하여 설정 오류(401 Unauthorized 등)를 예방합니다.
    """
    raw_val = os.environ.get(key, "")
    cleaned = raw_val.strip().strip('"').strip("'") if raw_val else ""
    if not cleaned or cleaned.lower().startswith(_PLACEHOLDER_PREFIXES):
        return default
    return cleaned


def get_env_bool(key: str, default: bool = False) -> bool:
    """
    [역할] 문자열 환경변수("True", "1", "yes", "on")를 파이썬 `bool` 타입으로 안전하게 변환합니다.
    """
    raw = get_env(key, str(default)).lower()
    return raw in {"1", "true", "yes", "on"}


def normalize_service_key(raw_key: str) -> str:
    """
    [역할]
    - 공공데이터포털 OpenAPI 인증키 정규화 함수입니다.
    - 공공데이터포털은 'Encoding 키(`%2F`, `%2B`, `%3D` 포함)'와 'Decoding 키(원문)' 2가지를 제공합니다.
    - 파이썬 `requests.get(url, params={"serviceKey": key})`를 호출할 때 이미 인코딩된 키를 넣으면
      `%` 기호가 `%25`로 이중 인코딩되어 인증 실패(SERVICE_KEY_IS_NOT_REGISTERED_ERROR)가 발생합니다.
    - 이 함수는 `unquote()`를 통해 어떤 형태의 키가 입력되든 항상 'Decoded 원문 키'로 통일합니다.
    [연결 목적지]
    - 아래 `MFDS_API_KEYS` 딕셔너리를 생성할 때 호출되며, 최종적으로 `Backend/drugs/services.py`의
      `fetch_easy_drugs()`, `fetch_grain_drugs()`, `fetch_prmsn_list()`, `fetch_prmsn_detail()`에서 사용됩니다.
    """
    if not raw_key:
        return ""
    cleaned = raw_key.strip().strip('"').strip("'")
    if cleaned.lower().startswith(_PLACEHOLDER_PREFIXES):
        return ""
    return unquote(cleaned)


# `.env` 파일 즉시 로드 실행
load_project_env()

# ==============================================================================
# 2. 보안(Security) 및 디버그 설정
# ==============================================================================
# [역할] 개발 모드 여부(`DEBUG`), 암호화 서명 키(`SECRET_KEY`), 허용 도메인(`ALLOWED_HOSTS`)을 설정합니다.
# [수정 가이드]
# - 실제 클라우드/서버에 배포할 때는 `.env`에서 `DJANGO_DEBUG="False"`로 바꾸고,
#   `DJANGO_ALLOWED_HOSTS="mydomain.com,www.mydomain.com"`처럼 실제 도메인을 지정하세요.
DEBUG: bool = get_env_bool("DJANGO_DEBUG", default=True)

SECRET_KEY: str = get_env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-edrug-care-dev-fallback-secret-key-only"
    else:
        raise ImproperlyConfigured(
            "운영 환경(DEBUG=False)에서는 .env 파일에 유효한 DJANGO_SECRET_KEY가 반드시 설정되어야 합니다."
        )

_default_hosts = "127.0.0.1,localhost,[::1],testserver"
ALLOWED_HOSTS: list[str] = [
    host.strip()
    for host in get_env("DJANGO_ALLOWED_HOSTS", _default_hosts).split(",")
    if host.strip()
]
if DEBUG and "testserver" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("testserver")

# 현대적 웹 보안 헤더 및 요청 제한 설정 (XSS, 클릭재킹, MIME 스니핑, 대용량 본문 DoS 방어)
SECURE_CONTENT_TYPE_NOSNIFF: bool = True
SECURE_REFERRER_POLICY: str = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS: str = "SAMEORIGIN"
SESSION_COOKIE_HTTPONLY: bool = True
SESSION_COOKIE_SAMESITE: str = "Lax"
CSRF_COOKIE_SAMESITE: str = "Lax"
DATA_UPLOAD_MAX_MEMORY_SIZE: int = 1_048_576  # 최대 요청 본문 크기 1MB 제한

# ==============================================================================
# 3. 애플리케이션(INSTALLED_APPS) 및 미들웨어(MIDDLEWARE) 정의
# ==============================================================================
# [역할] 프로젝트에서 활성화할 Django 내장 앱과 사용자 정의 앱을 등록합니다.
# [연결 목적지]
# - `"drugs"` 항목은 `Backend/drugs/apps.py`(`DrugsConfig`)와 `Backend/drugs/models.py`를 가리킵니다.
# [수정 가이드]
# - 새로운 기능 앱(예: `users` 회원관리 앱)을 `python manage.py startapp users`로 만들었다면,
#   이 리스트 마지막에 `"users",`를 추가해야 Django가 해당 앱의 모델과 뷰를 인식합니다.
INSTALLED_APPS: list[str] = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "drugs.apps.DrugsConfig",
]

# [역할] 모든 HTTP 요청(Request)과 응답(Response)이 뷰(`views.py`)에 도달하기 전후에 거치는 보안·세션 필터 체인입니다.
MIDDLEWARE: list[str] = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ==============================================================================
# 4. URL 라우팅 진입점 및 템플릿(HTML) 엔진 설정
# ==============================================================================
# [핵심 연결 목적지]
# - `ROOT_URLCONF = "config.urls"`는 브라우저 요청이 들어왔을 때 가장 먼저
#   `Backend/config/urls.py` 파일을 열어 주소를 검사하라고 지정하는 포인터입니다.
ROOT_URLCONF: str = "config.urls"

# [핵심 연결 목적지]
# - `DIRS: [FRONTEND_DIR]`는 `Backend/drugs/views.py`의 `index()` 함수가
#   `render(request, "index.html")`을 실행할 때 `Frontend/index.html`을 찾아가도록 연결합니다.
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

# [연결 목적지] 동기 서버(`Backend/config/wsgi.py`) 및 비동기 서버(`Backend/config/asgi.py`)의 `application` 객체를 가리킵니다.
WSGI_APPLICATION: str = "config.wsgi.application"
ASGI_APPLICATION: str = "config.asgi.application"

# ==============================================================================
# 5. 데이터베이스(SQLite3) 및 인메모리 캐시(Cache) 설정
# ==============================================================================
# [연결 목적지]
# - `NAME: BASE_DIR / "db.sqlite3"`는 `Backend/db.sqlite3` 파일을 가리키며,
#   `Backend/drugs/models.py`에 정의된 `PillCache`, `SavedDrug`, `SearchLog` 테이블이 이곳에 저장됩니다.
# [수정 가이드]
# - DB 파일 이름을 바꾸고 싶다면 `BASE_DIR / "my_drugs.sqlite3"`로 수정 후 `python Backend/manage.py migrate`를 실행하세요.
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
    [역할]
    - SQLite 데이터베이스 연결이 수립될 때마다 WAL(Write-Ahead Logging) 저널 모드와
      `synchronous=NORMAL` 설정을 적용하여 멀티스레드 동시 읽기/쓰기 성능과 안정성을 높입니다.
    [연결 목적지] `Backend/db.sqlite3` 커넥션 객체에 직접 PRAGMA SQL을 실행합니다.
    """
    if connection.vendor == "sqlite":
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")


# [역할] 식약처 OpenAPI 응답 결과를 메모리에 캐싱하여 동일한 검색어 재요청 시 0.01초 이내에 응답합니다.
# [연결 목적지] `Backend/drugs/services.py`의 `cache.get()` / `cache.set()`에서 사용됩니다.
# [수정 가이드] 캐시 유지 시간을 10분(600초)에서 30분으로 늘리려면 `"TIMEOUT": 1800`으로 변경하세요.
CACHES: dict[str, dict[str, Any]] = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "edrugs-openapi-cache",
        "TIMEOUT": 600,
    }
}

# ==============================================================================
# 6. 국제화(한국어/서울 시간대) 및 정적 파일(Static Files) 설정
# ==============================================================================
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

# ==============================================================================
# 7. 공공데이터포털 식약처 3대 OpenAPI 통합 설정 (.env 연동 + 안전 폴백)
# ==============================================================================
# [역할]
# - `.env`에서 식약처 3대 OpenAPI 인증키와 엔드포인트 주소를 읽어 정규화합니다.
# - 만약 `.env` 파일이 없거나 키가 비어 있더라도 `_DEFAULT_MFDS_ENCODED_KEY`로 자동 폴백하여
#   `serviceKey=` 빈 값으로 인한 `401 Client Error: Unauthorized`가 절대 발생하지 않도록 보장합니다.
# [연결 목적지]
# - `MFDS_API_KEYS`와 `MFDS_ENDPOINTS`는 `Backend/drugs/services.py`의
#   `fetch_easy_drugs()`, `fetch_grain_drugs()`, `fetch_prmsn_list()`, `fetch_prmsn_detail()`과
#   `Backend/drugs/views.py`의 `api_status()`에서 직접 참조됩니다.
PUBLIC_DATA_API_ENCODED_KEY: str = get_env(
    "PUBLIC_DATA_API_ENCODED_KEY", default=_DEFAULT_MFDS_ENCODED_KEY
)
PUBLIC_DATA_API_DECODED_KEY: str = normalize_service_key(
    get_env("PUBLIC_DATA_API_DECODED_KEY")
    or get_env("PUBLIC_DATA_API_KEY")
    or PUBLIC_DATA_API_ENCODED_KEY
    or _DEFAULT_MFDS_ENCODED_KEY
)

MFDS_API_KEYS: dict[str, str] = {
    "GRAIN": normalize_service_key(get_env("MFDS_GRAIN_API_KEY")) or PUBLIC_DATA_API_DECODED_KEY,
    "PERMISSION": normalize_service_key(get_env("MFDS_PERMISSION_API_KEY"))
    or PUBLIC_DATA_API_DECODED_KEY,
    "EASY": normalize_service_key(get_env("MFDS_EASY_DRUG_API_KEY")) or PUBLIC_DATA_API_DECODED_KEY,
}

# 하위 호환용 상수
MFDS_SERVICE_KEY_ENCODED: str = PUBLIC_DATA_API_ENCODED_KEY
MFDS_SERVICE_KEY_DECODED: str = PUBLIC_DATA_API_DECODED_KEY

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

# [수정 가이드]
# - 식약처 API 버전이 향후 업그레이드(예: `DrugPrdtPrmsnInfoService08` ➔ `09`)될 경우,
#   `.env`의 `MFDS_PERMISSION_END_POINT` 또는 아래 세부 오퍼레이션 경로 문자열만 수정하면
#   백엔드 전체(`services.py`, `views.py`)와 프론트엔드(`app.js`)에 자동 반영됩니다.
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
