"""계정 모듈 테이블

피부 모델(skin.py)과 같은 규칙: 복수형 테이블명, 기본키 id, Alembic 마이그레이션으로 생성
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CHAR, DateTime, ForeignKey, SmallInteger, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 구글 계정 고유 ID, 이메일 가입 회원은 구글 로그인 시 채움
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    # 항상 소문자로 저장 (Jiyeon@gmail.com = jiyeon@gmail.com)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    language: Mapped[str] = mapped_column(String(5))  # ko / en / zh / ja
    nationality: Mapped[str | None] = mapped_column(CHAR(2))  # ISO 3166-1 alpha-2
    resides_in_korea: Mapped[bool | None]
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Terms(Base):
    """약관 버전, 본문은 프론트 locales에 두고 DB에는 종류·버전·필수 여부만 저장"""

    __tablename__ = "terms"
    __table_args__ = (UniqueConstraint("type", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # SERVICE / PRIVACY / AGE_14 / FACE_IMAGE / PHOTO_STORAGE / MARKETING
    type: Mapped[str] = mapped_column(String(30))
    version: Mapped[str] = mapped_column(String(20))
    required: Mapped[bool]
    # 종류별로 시행일이 지난 것 중 가장 최신 버전이 현재 약관
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConsentHistory(TimestampMixin, Base):
    """동의·철회 이력, 수정 없이 행 추가만 (종류별 최신 행이 현재 상태)"""

    __tablename__ = "consent_histories"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    terms_id: Mapped[int] = mapped_column(ForeignKey("terms.id"))
    action: Mapped[str] = mapped_column(String(10))  # AGREE / WITHDRAW


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # 원문은 쿠키에만, DB에는 SHA-256 해시(64자)만 저장
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EmailVerification(Base):
    """이메일 인증 코드, 이메일당 한 행이라 이메일이 기본키 (인증 성공 시 행 삭제)"""

    __tablename__ = "email_verifications"

    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    attempt_count: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Kiosk(Base):
    __tablename__ = "kiosks"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # 해제된 기기는 일반 비회원으로 취급
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuestSession(Base):
    """비회원(웹·키오스크) 세션, 분석 결과는 guest_id로 연결

    회원 이관 시 user_id 채움, qr_token_hash·expires_at은 NULL
    """

    __tablename__ = "guest_sessions"

    # 쿠키(guest_id)·분석 결과 guest_id 값, 저장 전에 알 수 있게 파이썬에서 생성
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # 키오스크 세션이면 채움 (웹 비회원은 NULL)
    kiosk_id: Mapped[int | None] = mapped_column(ForeignKey("kiosks.id"))
    # IP 원문 대신 HMAC-SHA256. 키오스크 세션은 NULL
    ip_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    qr_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 촬영 전 동의한 얼굴 이미지 약관
    face_terms_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id"))
