#!/usr/bin/env python
"""
[역할] Django CLI 실행 진입점 (.env 환경변수 로드, 모듈 경로 고정, 서버·마이그레이션·테스트 구동)
[경로] 터미널/IDE 실행 -> Backend/manage.py -> Backend/config/settings.py -> urls.py / models.py / tests.py
[수정] 기본 개발 서버 포트를 바꾸려면 main()의 runserver 인자 뒤에 "127.0.0.1:8080"을 추가하세요.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_paths_and_env() -> None:
    """
    [역할] Backend 폴더를 sys.path와 작업 디렉터리로 고정하고 루트 .env 파일을 환경변수로 로드합니다.
    [경로] main() -> _bootstrap_paths_and_env() -> Backend/config/settings.py (get_env 소비)
    [수정] 별도 환경 파일(.env.local 등)을 우선 적용하려면 env_candidates 튜플의 첫 항목에 추가하세요.
    """
    backend_dir: Path = Path(__file__).resolve().parent
    project_root: Path = backend_dir.parent

    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    os.chdir(backend_dir)

    env_candidates: tuple[Path, ...] = (project_root / ".env", backend_dir / ".env")
    try:
        from dotenv import load_dotenv

        for env_file in env_candidates:
            if env_file.is_file():
                load_dotenv(dotenv_path=env_file, override=False)
    except ImportError:
        pass


def main() -> None:
    """
    [역할] DJANGO_SETTINGS_MODULE을 지정하고 Django 관리 명령어(runserver, migrate, test 등)를 실행합니다.
    [경로] __main__ -> main() -> django.core.management.execute_from_command_line
    [수정] 운영용 설정 파일을 분리할 경우 "config.settings"를 "config.settings_prod"로 변경하세요.
    """
    _bootstrap_paths_and_env()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django를 불러올 수 없습니다. 'pip install -r Backend/requirements.txt' 실행 여부를 확인하세요."
        ) from exc

    if len(sys.argv) == 1:
        print("[알약이가] 인자가 생략되어 개발 서버(http://127.0.0.1:8000)를 시작합니다.")
        sys.argv.append("runserver")

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
