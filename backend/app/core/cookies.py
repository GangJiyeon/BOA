"""인증 쿠키 설정. 옵션을 한곳에 모아 쿠키마다 설정이 어긋나지 않게 한다."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import Response

from app.core.config import get_settings

GUEST_COOKIE = "guest_id"


def _options() -> dict:
    return {"httponly": True, "samesite": "lax", "secure": get_settings().cookie_secure, "path": "/"}


def set_guest_cookie(response: Response, guest_id: UUID, expires_at: datetime) -> None:
    # DB에서 읽은 시각은 DB 세션 시간대(+09)로 오는데, 쿠키 expires는 UTC만 받는다
    response.set_cookie(
        GUEST_COOKIE, str(guest_id), expires=expires_at.astimezone(UTC), **_options()
    )


def clear_guest_cookie(response: Response) -> None:
    response.delete_cookie(GUEST_COOKIE, **_options())
