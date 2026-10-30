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
├── README.md             # 프로젝트 안내 문서
├── Backend/              # Python Django 6.1 백엔드 서버 및 데이터베이스
│   ├── manage.py         # Django 관리/실행 진입점 (인자 생략 시 runserver 자동 실행 지원)
│   ├── requirements.txt  # Python 필수 패키지 목록
│   ├── db.sqlite3        # SQLite3 데이터베이스 (낱알 외형 캐시·내 약통·검색 로그)
│   ├── generate_ppt.py   # 서비스 기획서 PPTX 자동 생성 스크립트
│   ├── config/           # 프로젝트 전역 설정 및 루트 URL 라우팅
│   │   ├── settings.py   # .env 로드, DB(WAL 최적화), 캐시, STORAGES, API 엔드포인트 설정
│   │   ├── urls.py       # 루트 URL 매핑 (/admin, /style.css, /app.js, /)
│   │   ├── asgi.py       # ASGI 비동기 배포 진입점
│   │   └── wsgi.py       # WSGI 운영 배포 진입점
│   └── drugs/            # 핵심 의약품 도메인 애플리케이션
│       ├── models.py     # PillCache, SavedDrug, SearchLog ORM 모델
│       ├── services.py   # 3대 OpenAPI 병렬 호출, 정규화 병합, SQLite 고속 일괄 Upsert
│       ├── views.py      # Frontend 템플릿/정적 서빙 및 REST JSON API 컨트롤러
│       ├── urls.py       # /api/... 세부 라우팅
│       ├── admin.py      # Django 관리자 페이지 모델 등록
│       ├── apps.py       # 앱 메타데이터 설정
│       └── tests.py      # 백엔드 자동화 단위 테스트
└── Frontend/             # PC·모바일 반응형 웹 프론트엔드
    ├── index.html        # 메인 4-Tab UI 및 3-in-1 상세 모달 마크업
    ├── style.css         # 반응형 디자인 시스템 및 모바일 하단 네비게이션 스타일
    ├── app.js            # 비동기 API 컨트롤러 (AbortController, XSS 방어, 정적 폴백)
    └── package.json      # 프론트엔드 패키지 메타데이터
```

---

## 2. 연동된 식약처 OpenAPI 3종 (`.env` 통합 관리)

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

## 3. 로컬 실행 방법

터미널(PowerShell / 명령 프롬프트)에서 `e-drugs` 루트 폴더 기준으로 아래 명령어를 실행하세요.

```powershell
# 1. 가상환경 활성화 (선택) 및 패키지 설치
.\.venv\Scripts\Activate.ps1
pip install -r Backend\requirements.txt

# 2. DB 마이그레이션 확인
python Backend\manage.py migrate

# 3. Django 로컬 개발 서버 실행 (두 방식 모두 동일하게 작동)
python Backend\manage.py runserver
# 또는 WebStorm/PyCharm에서 Backend/manage.py 직접 Run 실행 지원
```

서버 구동 후 브라우저에서 **`http://127.0.0.1:8000`** 으로 접속하면 `🟢 Django Backend + SQLite 연동` 모드로 동작합니다.
