"""키오스크 기기 등록·해제·조회"""

import hmac
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_token, new_token
from app.models import Kiosk


class AdminCodeNotConfigured(Exception):
    pass


def check_admin_code(code: str) -> bool:
    """관리자 코드 확인, 시간이 일정한 비교 (응답 시간으로 코드 추측 방지)"""
    admin_code = get_settings().admin_code
    if not admin_code:
        raise AdminCodeNotConfigured
    return hmac.compare_digest(code.encode(), admin_code.encode())


def find_active(db: Session, kiosk_token: str | None) -> Kiosk | None:
    """해제 안 된 기기만, 없거나 해제됐으면 None"""
    if not kiosk_token:
        return None
    kiosk = db.scalar(select(Kiosk).where(Kiosk.token_hash == hash_token(kiosk_token)))
    if kiosk is None or kiosk.revoked_at is not None:
        return None
    return kiosk


def register(db: Session) -> tuple[Kiosk, str]:
    """새 기기 등록, 토큰 원문 반환 (DB에는 해시만)"""
    token = new_token()
    kiosk = Kiosk(token_hash=hash_token(token))
    db.add(kiosk)
    db.flush()
    return kiosk, token


def revoke(db: Session, kiosk: Kiosk) -> None:
    kiosk.revoked_at = datetime.now(UTC)
