"""인증 쿠키 설정, 옵션은 _options()로 통일"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import Response

from app.core.config import get_settings

GUEST_COOKIE = "guest_id"
ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
KIOSK_COOKIE = "kiosk_token"
# 리프레시 토큰은 갱신·로그아웃 요청에만 전송
REFRESH_PATH = "/api/auth"


def _options(path: str = "/") -> dict:
    return {"httponly": True, "samesite": "lax", "secure": get_settings().cookie_secure, "path": path}


def set_guest_cookie(response: Response, guest_id: UUID, expires_at: datetime) -> None:
    # DB 시각은 +09로 옴, 쿠키 expires는 UTC만 허용
    response.set_cookie(
        GUEST_COOKIE, str(guest_id), expires=expires_at.astimezone(UTC), **_options()
    )


def clear_guest_cookie(response: Response) -> None:
    response.delete_cookie(GUEST_COOKIE, **_options())


def set_auth_cookies(
    response: Response, access_token: str, refresh_token: str, refresh_expires_at: datetime
) -> None:
    """액세스 쿠키도 리프레시 토큰만큼 유지

    쿠키가 토큰(15분)보다 먼저 사라지면 만료가 아닌 비로그인으로 판별됨
    → 쿠키를 남겨야 만료 토큰에 401 반환 가능
    """
    expires = refresh_expires_at.astimezone(UTC)
    response.set_cookie(ACCESS_COOKIE, access_token, expires=expires, **_options())
    response.set_cookie(REFRESH_COOKIE, refresh_token, expires=expires, **_options(REFRESH_PATH))


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, **_options())
    response.delete_cookie(REFRESH_COOKIE, **_options(REFRESH_PATH))


def set_kiosk_cookie(response: Response, kiosk_token: str) -> None:
    # 해제 전까지 유지 (브라우저 최대 400일)
    max_age = get_settings().kiosk_token_days * 24 * 60 * 60
    response.set_cookie(KIOSK_COOKIE, kiosk_token, max_age=max_age, **_options())


def clear_kiosk_cookie(response: Response) -> None:
    response.delete_cookie(KIOSK_COOKIE, **_options())
