# 💊 알약이가 (e-Drug Care)
**식약처 3대 공공데이터(OpenAPI) 통합 스마트 의약품 식별 및 복약 안전 플랫폼**  
*(대학교 웹프로그래밍 실습 — Django 6.1 Backend + 반응형 Frontend 통합 프로젝트)*

---

## 1. 프로젝트 폴더 구조 (`Backend` / `Frontend` 분리 아키텍처)

```text
e-drugs/
├── .env                  # 통합 보안키 및 공공데이터포털 3대 API Key / EndPoint 설정 (Git 제외)
├── .env.example          # 환경변수 설정 템플릿
├── .gitignore            # .env, .venv, __pycache__ 등 제외 규칙
├── README.md             # 프로젝트 안내 및 백엔드 아키텍처 흐름 문서
├── Backend/              # Python Django 6.1 백엔드 서버 및 데이터베이스
│   ├── manage.py         # Django 관리/실행 진입점 (인자 생략 시 runserver 자동 실행 지원)
│   ├── requirements.txt  # Python 필수 패키지 목록 (UTF-8)
│   ├── db.sqlite3        # SQLite3 데이터베이스 (낱알 외형 캐시·내 약통·검색 로그)
│   ├── generate_ppt.py   # 서비스 기획서 PPTX 자동 생성 스크립트
│   ├── config/           # 프로젝트 전역 설정 및 루트 URL 라우팅
│   │   ├── settings.py   # .env 로드, 폴백 인증키, DB(WAL 최적화), 캐시, 보안 헤더, API 설정
│   │   ├── urls.py       # 루트 URL 매핑 (/admin, /style.css, /app.js, /favicon.ico, /)
│   │   ├── asgi.py       # ASGI 비동기 배포 진입점
│   │   └── wsgi.py       # WSGI 운영 배포 진입점
│   └── drugs/            # 핵심 의약품 도메인 애플리케이션
│       ├── models.py     # PillCache, SavedDrug, SearchLog ORM 모델
│       ├── services.py   # 3대 OpenAPI 병렬 호출, CDATA/XML 정밀 파서, SQLite 고속 일괄 Upsert
│       ├── views.py      # Frontend 템플릿/정적 서빙 및 REST JSON API 컨트롤러
│       ├── urls.py       # /api/... 세부 라우팅
│       ├── admin.py      # Django 관리자 페이지 모델 등록
│       ├── apps.py       # 앱 메타데이터 설정
│       └── tests.py      # 백엔드 및 프론트엔드 자동화 단위 테스트 (7종)
└── Frontend/             # PC·모바일 반응형 웹 프론트엔드
    ├── index.html        # 메인 3-Tab UI 및 3-in-1 상세 모달 마크업
    ├── style.css         # 반응형 디자인 시스템 및 모바일 하단 네비게이션 스타일
    ├── app.js            # 비동기 API 컨트롤러 (AbortController, XSS/URL 방어, 정적 폴백)
    └── package.json      # 프론트엔드 패키지 메타데이터
```

---

## 2. 백엔드 파일 간 호출 흐름 (출발지 ➔ 목적지 아키텍처 맵)

백엔드 서버가 실행되고 브라우저(`Frontend/app.js`) 요청을 처리할 때 각 파일이 가리키는 목적지 순서입니다:

1. **`Backend/manage.py`** (실행 진입점)
   - `.env` 파일을 로드하고 `DJANGO_SETTINGS_MODULE = "config.settings"`를 통해 **`Backend/config/settings.py`**를 가리킵니다.
2. **`Backend/config/settings.py`** (전역 설정 총괄)
   - `ROOT_URLCONF = "config.urls"` ➔ 최초 URL 라우터로 **`Backend/config/urls.py`**를 가리킵니다.
   - `TEMPLATES["DIRS"] = [FRONTEND_DIR]` ➔ HTML 템플릿 폴더로 **`Frontend/index.html`**을 가리킵니다.
   - `INSTALLED_APPS` ➔ **`Backend/drugs/apps.py`** (`DrugsConfig`) 및 **`Backend/drugs/models.py`**를 등록합니다.
   - `DATABASES` ➔ **`Backend/db.sqlite3`** 파일을 가리킵니다.
3. **`Backend/config/urls.py`** (루트 URL 안내 데스크)
   - `/admin/` ➔ **`Backend/drugs/admin.py`**
   - `/style.css`, `/app.js`, `/favicon.ico` ➔ **`Backend/drugs/views.py`** (`serve_frontend_asset`, `serve_favicon`)
   - `""` (나머지 모든 주소) ➔ **`Backend/drugs/urls.py`**로 위임(`include("drugs.urls")`)합니다.
4. **`Backend/drugs/urls.py`** (세부 API 주소록)
   - `/` ➔ `views.index` (**`Frontend/index.html`** 렌더링)
   - `/api/status/` ➔ `views.api_status`
   - `/api/unified-search/` ➔ `views.api_unified_search`
   - `/api/grain-search/` ➔ `views.api_grain_search`
   - `/api/permission-search/` ➔ `views.api_permission_search`
   - `/api/drug-detail/` ➔ `views.api_drug_detail`
   - `/api/pillbox/` ➔ `views.api_pillbox`
5. **`Backend/drugs/views.py`** (요청/응답 컨트롤러)
   - 입력 파라미터 검증 후 **`Backend/drugs/services.py`**의 검색·병합 함수를 호출하거나 **`Backend/drugs/models.py`**의 DB 모델을 조회·저장합니다.
6. **`Backend/drugs/services.py`** (비즈니스 로직 & OpenAPI 엔진)
   - **`Backend/config/settings.py`**의 `MFDS_API_KEYS`와 `MFDS_ENDPOINTS`를 사용해 외부 식약처 3대 OpenAPI를 병렬 호출하고, **`Backend/drugs/models.py`**의 `PillCache` 테이블에 고속 캐싱합니다.

---

## 3. 연동된 식약처 OpenAPI 3종 (`.env` 통합 관리)

1. **[식품의약품안전처_의약품 낱알식별 정보]**
   - End Point: `https://apis.data.go.kr/1471000/MdcinGrnIdntfcInfoService03`
   - 상세 오퍼레이션: `/getMdcinGrnIdntfcInfoList03`
2. **[식품의약품안전처_의약품 제품 허가정보]**
   - End Point: `https://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService08`
   - 상세 오퍼레이션: `/getDrugPrdtPrmsnInq08` (목록), `/getDrugPrdtPrmsnDtlInq08` (상세)
3. **[식품의약품안전처_의약품개요정보(e약은요)]**
   - End Point: `https://apis.data.go.kr/1471000/DrbEasyDrugInfoService`
   - 상세 오퍼레이션: `/getDrbEasyDrugList`

---

## 4. 로컬 실행 및 테스트 방법

터미널(PowerShell / 명령 프롬프트)에서 `e-drugs` 루트 폴더 기준으로 아래 명령어를 실행하세요.

```powershell
# 1. 가상환경 활성화 (선택) 및 패키지 설치
.\.venv\Scripts\Activate.ps1
pip install -r Backend\requirements.txt

# 2. DB 마이그레이션 및 자동화 테스트 검증
python Backend\manage.py migrate
python Backend\manage.py test

# 3. Django 로컬 개발 서버 실행 (두 방식 모두 동일하게 작동)
python Backend\manage.py runserver
# 또는 WebStorm/PyCharm에서 Backend/manage.py 직접 Run 실행 지원
```

서버 구동 후 브라우저에서 **`http://127.0.0.1:8000`** 으로 접속하면 Django Backend + SQLite 연동 모드로 동작합니다.
