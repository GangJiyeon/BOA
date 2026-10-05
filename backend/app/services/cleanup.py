"""만료 데이터 정리 (매일 새벽 4시 자동 + scripts/cleanup_expired.py 수동)

여러 번 돌려도 결과가 같아서 서버가 여러 개여도 중복 실행 문제 없음
"""

import logging
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import EmailVerification, GuestSession, RefreshToken
from app.services.account import RESULT_MODELS

logger = logging.getLogger("uvicorn.error")

# 스케줄러용 고정 시간대 (컨테이너에 tzdata 없어도 동작)
KST = timezone(timedelta(hours=9))
RUN_HOUR = 4


def cleanup_expired(db: Session) -> dict[str, int]:
    """지운 행 수를 테이블별로 반환, 커밋은 호출하는 쪽에서

    분석 결과엔 세션 FK가 없어 세션보다 먼저 guest_id로 삭제
    회원에게 이관된 세션은 expires_at이 NULL이라 제외
    """
    now = datetime.now(UTC)
    expired_sessions = select(GuestSession.id).where(
        GuestSession.user_id.is_(None), GuestSession.expires_at < now
    )

    def run(stmt) -> int:
        return db.execute(stmt.execution_options(synchronize_session=False)).rowcount

    counts = {
        model.__tablename__: run(delete(model).where(model.guest_id.in_(expired_sessions)))
        for model in RESULT_MODELS
    }
    counts["guest_sessions"] = run(delete(GuestSession).where(GuestSession.id.in_(expired_sessions)))
    counts["refresh_tokens"] = run(delete(RefreshToken).where(RefreshToken.expires_at < now))
    counts["email_verifications"] = run(
        delete(EmailVerification).where(EmailVerification.expires_at < now)
    )
    return counts


def run_cleanup() -> dict[str, int]:
    """스케줄러·스크립트 진입점, 자체 세션으로 실행 후 커밋"""
    with SessionLocal() as db:
        counts = cleanup_expired(db)
        db.commit()
    logger.info("[정리] 만료 데이터 삭제: %s", counts)
    return counts
