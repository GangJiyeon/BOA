"""이메일 인증 코드 발급·확인"""

import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_email_code
from app.models import EmailVerification


class ResendTooSoon(Exception):
    pass


def issue_code(db: Session, email: str) -> str:
    """6자리 코드 발급 후 원문 반환, 재발송 간격 안이면 ResendTooSoon"""
    settings = get_settings()
    now = datetime.now(UTC)
    row = db.get(EmailVerification, email)
    if row is not None and row.sent_at + timedelta(seconds=settings.email_resend_seconds) > now:
        raise ResendTooSoon

    code = f"{secrets.randbelow(1_000_000):06d}"
    if row is None:
        row = EmailVerification(email=email)
        db.add(row)
    # 재발송 시 이전 코드 무효, 시도 횟수 초기화
    row.code_hash = hash_email_code(email, code)
    row.attempt_count = 0
    row.sent_at = now
    row.expires_at = now + timedelta(minutes=settings.email_code_minutes)
    return code


def verify_code(db: Session, email: str, code: str) -> str | None:
    """성공이면 None(행 삭제), 실패면 사용자에게 보여줄 메시지

    틀린 횟수도 저장해야 해서 예외 대신 메시지 반환 (커밋은 호출하는 쪽에서)
    """
    row = db.get(EmailVerification, email)
    if row is None or row.expires_at <= datetime.now(UTC):
        return "인증 코드가 만료되었습니다. 다시 받아 주세요"
    if row.attempt_count >= get_settings().email_max_attempts:
        return "시도 횟수를 초과했습니다. 코드를 다시 받아 주세요"
    if not hmac.compare_digest(row.code_hash, hash_email_code(email, code)):
        row.attempt_count += 1
        return "인증 코드가 올바르지 않습니다"
    db.delete(row)
    return None
