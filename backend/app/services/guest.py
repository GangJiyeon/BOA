"""비회원 세션 생성·조회"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_token, new_token
from app.models import GuestSession


def find_active_session(db: Session, guest_id: UUID | None) -> GuestSession | None:
    """비회원&만료 전인 세션만 반환

    회원 이관 세션: user_id 부여 & 제외(expires_at == NULL)
    """
    if guest_id is None:
        return None
    session = db.get(GuestSession, guest_id)
    if session is None or session.user_id is not None or session.expires_at is None:
        return None
    if session.expires_at <= datetime.now(UTC):
        return None
    return session


def start_session(
    db: Session,
    *,
    face_terms_id: int,
    ip_hash: str | None,
    kiosk_id: int | None = None,
    existing: GuestSession | None = None,
) -> tuple[GuestSession, str]:
    """세션 생성(existing 없을 때) 또는 기존 세션 재사용, 새 QR 토큰 원문 반환

    DB에는 해시만 있어 예전 원문 재발급 불가 → 재사용 시에도 새 토큰으로 덮어씀 (예전 QR 무효)
    만료 시각은 연장 안 함
    """
    session = existing
    if session is None:
        days = get_settings().guest_session_days
        session = GuestSession(
            kiosk_id=kiosk_id,
            ip_hash=ip_hash,
            expires_at=datetime.now(UTC) + timedelta(days=days),
        )
        db.add(session)

    qr_token = new_token()
    session.face_terms_id = face_terms_id
    session.qr_token_hash = hash_token(qr_token)
    db.flush()
    return session, qr_token
