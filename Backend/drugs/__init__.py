"""
================================================================================
[파일명] Backend/drugs/__init__.py
[역할] `drugs` 디렉터리를 Django 도메인 애플리케이션 패키지로 인식시키는 초기화 파일
================================================================================

[백엔드 아키텍처 설명]
- `drugs` 패키지는 알약이가(e-Drug Care)의 핵심 비즈니스 도메인(의약품 검색·식별·허가조회·내 약통)을
  담당하는 Django 앱입니다.
- 내부 구성 파일들의 연결 관계:
  - `apps.py` ➔ `Backend/config/settings.py`의 `INSTALLED_APPS`에 앱을 등록
  - `urls.py` ➔ `Backend/config/urls.py`로부터 URL 요청을 넘겨받아 `views.py` 함수로 연결
  - `views.py` ➔ 프론트엔드(`Frontend/app.js`)의 HTTP 요청을 받아 `services.py`와 `models.py`를 호출
  - `services.py` ➔ 식약처 3대 OpenAPI 병렬 호출, XML/JSON 파싱, `PillCache` 고속 저장 수행
  - `models.py` ➔ `Backend/db.sqlite3` 데이터베이스의 테이블(`PillCache`, `SavedDrug`, `SearchLog`) 정의
  - `admin.py` ➔ `/admin/` 관리자 화면에서 DB 테이블을 조회·편집할 수 있도록 등록
  - `tests.py` ➔ 위 모든 모듈이 정상 작동하는지 검증하는 자동화 테스트
================================================================================
"""
