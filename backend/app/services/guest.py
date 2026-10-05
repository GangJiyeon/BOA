"""비회원 세션 생성·조회·이관"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_token, new_token
from app.models import FaceAnalysis, GuestSession, HairRecRun, SkinAnalysis


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


def find_by_qr_token(db: Session, qr_token: str) -> GuestSession | None:
    """QR 토큰으로 비회원 세션 조회, 없거나 만료·이관된 세션이면 None"""
    session = db.scalar(select(GuestSession).where(GuestSession.qr_token_hash == hash_token(qr_token)))
    return find_active_session(db, session.id) if session is not None else None


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


def transfer_to_user(db: Session, session: GuestSession, user_id: int) -> None:
    """비회원 세션·분석 결과를 회원에게 이관 (가입, QR 저장 공통)

    QR·만료 시각 비움 → 예전 QR로 회원 결과 조회 불가, 만료 배치 대상 제외
    """
    session.user_id = user_id
    session.qr_token_hash = None
    session.expires_at = None
    # 분석 결과 (guest_id는 그대로, expires_at은 피부 테이블에만 있음)
    db.execute(
        update(SkinAnalysis)
        .where(SkinAnalysis.guest_id == session.id)
        .values(user_id=user_id, expires_at=None)
    )
    for model in (HairRecRun, FaceAnalysis):
        db.execute(update(model).where(model.guest_id == session.id).values(user_id=user_id))
