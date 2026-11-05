#!/usr/bin/env python
"""
================================================================================
[파일명] Backend/manage.py
[역할] Django 프로젝트의 최상위 명령줄 실행 진입점 (CLI Entry Point)
================================================================================

[백엔드 아키텍처 호출 흐름 (출발지 ➔ 목적지)]
1. 출발지 (From):
   - 개발자가 터미널에서 `python Backend/manage.py runserver` 또는 `migrate`, `test` 실행
   - 또는 IDE(PyCharm, WebStorm, VSCode)에서 이 파일을 직접 Run 버튼으로 실행
2. 현재 파일 (manage.py):
   - `_bootstrap_paths_and_env()` ➔ 프로젝트 루트의 `.env` 환경변수 파일 로드
   - `os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")` 설정
3. 목적지 (To):
   - [목적지 1] `Backend/config/settings.py`: 전역 설정(DB, 앱, API 키, 미들웨어)을 읽어들임
   - [목적지 2] `Backend/config/urls.py`: `settings.py`의 `ROOT_URLCONF`에 의해 URL 라우터로 연결됨
   - [목적지 3] `Backend/drugs/models.py`: `makemigrations` / `migrate` 실행 시 테이블 스키마 반영
   - [목적지 4] `Backend/drugs/tests.py`: `test` 명령 실행 시 자동화 단위 테스트 수행

[현재 구현된 서비스]
- `Backend/` 폴더를 파이썬 모듈 탐색 경로(`sys.path`) 최우선 순위에 자동 등록
- 프로젝트 루트(`e-drugs/.env`) 및 `Backend/.env` 파일 자동 탐색 및 로드
- 인자 없이 `python Backend/manage.py`만 실행해도 자동으로 로컬 서버(`runserver`) 구동

[향후 확장 가능한 서비스]
- 커스텀 관리 명령어 추가: `Backend/drugs/management/commands/sync_pills.py`를 만들면
  `python Backend/manage.py sync_pills` 명령어로 식약처 DB 배치를 주기적으로 동기화할 수 있습니다.
================================================================================
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_paths_and_env() -> None:
    """
    [역할]
    - 현재 `manage.py`가 위치한 `Backend` 디렉터리를 파이썬 `sys.path`에 추가하여
      어느 작업 디렉터리(루트 또는 Backend 폴더)에서 실행하더라도 `config`, `drugs` 패키지를
      정상적으로 import할 수 있도록 보장합니다.
    - `python-dotenv` 패키지가 설치되어 있다면 `.env` 파일을 미리 읽어 환경변수로 등록합니다.

    [연결 목적지]
    - 읽어들인 환경변수는 `Backend/config/settings.py`의 `get_env()` 함수에서 소비됩니다.

    [수정 가이드]
    - 만약 `.env.local`이나 `.env.production` 같은 별도 환경변수 파일을 우선 적용하고 싶다면:
      아래 `env_candidates` 튜플을 `(project_root / ".env.local", project_root / ".env")`로 변경하세요.
    """
    backend_dir: Path = Path(__file__).resolve().parent
    project_root: Path = backend_dir.parent

    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    # 어느 위치(루트 폴더 등)에서 `python Backend/manage.py test`를 실행하더라도
    # `drugs` 앱 테스트를 즉시 탐색할 수 있도록 작업 디렉터리를 Backend로 맞춥니다.
    os.chdir(backend_dir)

    env_candidates: tuple[Path, ...] = (project_root / ".env", backend_dir / ".env")
    try:
        from dotenv import load_dotenv

        for env_file in env_candidates:
            if env_file.is_file():
                load_dotenv(dotenv_path=env_file, override=False)
    except ImportError:
        # python-dotenv 미설치 환경에서는 Backend/config/settings.py 내부의
        # 순수 파이썬 폴백 로더(_load_dotenv_fallback)가 동일하게 .env를 파싱합니다.
        pass


def main() -> None:
    """
    [역할]
    - Django 관리 유틸리티(`execute_from_command_line`)를 호출하여 서버 실행, 마이그레이션,
      테스트, 관리자 계정 생성 등 모든 관리 작업을 수행합니다.

    [연결 목적지]
    - `DJANGO_SETTINGS_MODULE = "config.settings"` 지정을 통해
      `Backend/config/settings.py` 파일을 프로젝트 전역 설정 모듈로 가리킵니다.

    [수정 가이드]
    - 예1) 기본 개발 서버 포트를 8000번이 아닌 8080번으로 자동 실행하고 싶다면:
      아래 `sys.argv.append("runserver")` 바로 다음 줄에 `sys.argv.append("127.0.0.1:8080")`을 추가하세요.
    - 예2) 배포 환경 설정 파일(`config/settings_prod.py`)을 따로 분리해 바라보게 하고 싶다면:
      `os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_prod")`로 변경하세요.
    """
    _bootstrap_paths_and_env()

    # [핵심 연결 코드] Django에게 "설정 파일의 목적지는 Backend/config/settings.py 이다"라고 알려줍니다.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django를 불러올 수 없습니다. 가상환경(.venv)이 활성화되어 있는지, "
            "'pip install -r Backend/requirements.txt'가 실행되었는지 확인하세요."
        ) from exc

    # IDE에서 인자 없이 manage.py를 바로 실행(Run)했을 때 runserver가 자동 시작되도록 처리합니다.
    if len(sys.argv) == 1:
        print("[알약이가] 실행 인자가 지정되지 않아 로컬 개발 서버(http://127.0.0.1:8000)를 자동 시작합니다.")
        print("   (명령어 목록 확인이 필요하면 'python Backend/manage.py help'를 실행하세요.)")
        sys.argv.append("runserver")

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
