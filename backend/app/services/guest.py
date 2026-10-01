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
    """세션을 만들거나(existing이 없을 때) 기존 세션을 이어 쓰고, 새 QR 토큰 원문을 돌려준다.

    DB에는 QR 토큰 해시만 있어서 예전 원문을 다시 줄 수 없으므로, 재사용할 때도
    새 토큰을 발급해 해시를 덮어쓴다 (예전 QR은 무효가 된다). 만료 시각은 연장하지 않는다.
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
