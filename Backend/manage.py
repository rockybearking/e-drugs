#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_paths_and_env() -> None:
    """Backend 루트 경로를 sys.path에 보장하고 프로젝트 통합 .env 파일을 로드합니다."""
    backend_dir = Path(__file__).resolve().parent
    project_root = backend_dir.parent

    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    try:
        from dotenv import load_dotenv

        for env_file in (project_root / ".env", backend_dir / ".env"):
            if env_file.is_file():
                load_dotenv(dotenv_path=env_file, override=False)
    except ImportError:
        # python-dotenv 미설치 시 config.settings 내부 폴백 로더가 처리합니다.
        pass


def main() -> None:
    """Run administrative tasks."""
    _bootstrap_paths_and_env()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # IDE(WebStorm/PyCharm 등)에서 서브커맨드 인자 없이 manage.py를 바로 실행(Run)했을 때
    # 도움말만 출력하고 종료되는 대신 로컬 개발 서버(runserver)가 구동되도록 처리합니다.
    if len(sys.argv) == 1:
        print("💡 [알약이가] 실행 인자가 지정되지 않아 로컬 개발 서버(http://127.0.0.1:8000)를 자동 시작합니다.")
        print("   (명령어 목록 확인이 필요하면 'python manage.py help'를 실행하세요.)")
        sys.argv.append("runserver")

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
