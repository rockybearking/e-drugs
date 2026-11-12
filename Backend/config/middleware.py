"""
[역할] 요청별 암호화 CSP 논스(nonce) 발급 및 브라우저 보안 헤더(CSP, Permissions-Policy, COOP) 주입 미들웨어
[경로] Backend/config/settings.py (MIDDLEWARE) -> 모든 HTTP 요청/응답 -> Backend/drugs/views.py (request.csp_nonce 전달)
[수정] 외부 이미지·폰트 도메인을 추가 허용하려면 아래 Content-Security-Policy 문자열의 img-src / font-src 지시어를 수정하세요.
"""
from __future__ import annotations

import secrets
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse


class SecurityHeadersMiddleware:
    """앱 라우트에 요청별 CSP 논스와 권한 격리 헤더를 부여합니다 (/admin/ 경로는 내장 스크립트 호환을 위해 제외)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        nonce = secrets.token_urlsafe(16)
        request.csp_nonce = nonce  # type: ignore[attr-defined]

        response = self.get_response(request)
        response.setdefault(
            "Permissions-Policy",
            "camera=(), geolocation=(), microphone=()",
        )
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")

        if not request.path.startswith("/admin/"):
            csp_directives = (
                "default-src 'self'",
                f"script-src 'self' 'nonce-{nonce}' 'strict-dynamic' 'report-sample'",
                "style-src 'self'",
                "img-src 'self' data: https: http:",
                "font-src 'self'",
                "connect-src 'self'",
                "object-src 'none'",
                "base-uri 'none'",
                "frame-ancestors 'self'",
                "form-action 'self'",
            )
            response.setdefault("Content-Security-Policy", "; ".join(csp_directives))

        return response
