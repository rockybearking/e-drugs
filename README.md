# 알약이가 (e-Drug Care)
**식약처 공공데이터 통합 의약품 식별 및 복약 안전 관리 웹서비스**  
*(대학교 웹프로그래밍 2차 과제 — Django 6.1 Backend + Django ORM + 반응형 Frontend)*

---

## 1. 프로젝트 폴더 구조 (`Backend` / `Frontend` 분리 아키텍처)

```text
e-drugs/
├── .env                  # 보안키 및 식약처 공공데이터 3종 API Key / EndPoint 설정 (Git 제외)
├── .env.example          # 환경변수 설정 템플릿
├── .gitignore            # .env, .venv, __pycache__ 등 제외 규칙
├── README.md             # 프로젝트 구조 및 호출 흐름 안내 문서
├── Backend/              # Python Django 6.1 백엔드 서버 및 SQLite 데이터베이스
│   ├── manage.py         # Django 관리/실행 진입점 (인자 생략 시 runserver 자동 실행)
│   ├── requirements.txt  # Python 필수 패키지 목록
│   ├── db.sqlite3        # SQLite3 데이터베이스 (낱알 외형 캐시 · 내 약통 · 검색 로그)
│   ├── config/           # 프로젝트 전역 설정, 보안 미들웨어 및 루트 URL 라우팅
│   │   ├── settings.py   # .env 로드, SQLite WAL/캐시 튜닝, CSRF 설정, API 엔드포인트
│   │   ├── middleware.py # 요청별 CSP 암호화 논스(Nonce) 및 브라우저 보안 헤더 주입
│   │   ├── urls.py       # 루트 URL 매핑 (/admin, /style.css, /app.js, /favicon.ico, /)
│   │   ├── asgi.py       # ASGI 비동기 배포 진입점
│   │   └── wsgi.py       # WSGI 운영 배포 진입점
│   └── drugs/            # 의약품 검색 및 내 약통(CRUD) 도메인 애플리케이션
│       ├── models.py     # PillCache, SavedDrug, SearchLog ORM 모델
│       ├── services.py   # 식약처 3대 API 병렬 호출, XML/CDATA 파서, SQLite 푸시다운 검색
│       ├── views.py      # Frontend 서빙 및 검색·상세·내 약통 전체 CRUD 컨트롤러
│       ├── urls.py       # /api/... 세부 라우팅
│       ├── admin.py      # Django 관리자 페이지 모델 등록
│       ├── apps.py       # 앱 메타데이터 설정
│       └── tests.py      # 보안(CSP/CSRF)·파서·다중 외형 필터·내 약통 CRUD 단위 테스트
└── Frontend/             # PC · 태블릿 · 모바일 반응형 웹 프론트엔드
    ├── index.html        # 수직 색인 레일 + 메인 워크벤치 + 네이티브 <dialog> 모달 2종
    ├── style.css         # Editorial Apothecary Ledger 반응형 디자인 시스템
    └── app.js            # 비동기 API 컨트롤러 (CSRF, AbortController, 무-innerHTML DOM)
```

---

## 2. 파일 간 호출 흐름 (출발지 -> 목적지)

1. **`Backend/manage.py`** -> `.env` 로드 후 **`Backend/config/settings.py`** 실행
2. **`Backend/config/settings.py`** -> **`Backend/config/middleware.py`**(`SecurityHeadersMiddleware`, `CsrfViewMiddleware`), **`Backend/config/urls.py`**, **`Backend/db.sqlite3`** 연결
3. **`Backend/config/urls.py`** -> `/style.css`, `/app.js`, `/favicon.ico`를 **`Backend/drugs/views.py`**로 연결하고 나머지 경로를 **`Backend/drugs/urls.py`**로 위임
4. **`Backend/drugs/urls.py`** -> **`Backend/drugs/views.py`** 세부 엔드포인트 매핑:
   - `GET /` -> `index` (`Frontend/index.html` 렌더링 + CSP 논스 + CSRF 쿠키 발급)
   - `GET /api/status/` -> `api_status` (캐시 건수, API 상태, 다빈도 검색어 조회)
   - `GET /api/unified-search/` -> `api_unified_search` (품목·효능·업체 + 다중 낱알 외형 통합 검색)
   - `GET /api/permission-search/` -> `api_permission_search` (품목허가·주성분 색인 조회)
   - `GET /api/drug-detail/` -> `api_drug_detail` (단일 약품 3대 공공데이터 실시간 병합 명세)
   - `GET / POST / PATCH / DELETE /api/pillbox/` -> `api_pillbox` (내 약통 전체 CRUD + 주성분 중복 안전 리포트)
5. **`Backend/drugs/services.py`** -> 공유 스레드풀(`_API_EXECUTOR`)로 식약처 공공데이터 3종을 병렬 호출하고 `PillCache` 테이블에 일괄 Upsert 및 SQL 조건 푸시다운 검색 수행

---

## 3. 로컬 실행 및 테스트 방법

```powershell
# 1. 패키지 설치
pip install -r Backend\requirements.txt

# 2. DB 마이그레이션, 시스템 점검 및 단위 테스트 실행
python Backend\manage.py migrate
python Backend\manage.py check
python Backend\manage.py test drugs -v 2

# 3. Django 개발 서버 실행
python Backend\manage.py runserver
```

서버 구동 후 브라우저에서 **`http://127.0.0.1:8000`** 으로 접속합니다.
