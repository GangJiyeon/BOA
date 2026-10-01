"""계정 모듈 테이블.

피부 모델(skin.py)과 같은 규칙을 따른다: 복수형 테이블명, 기본키 id, Alembic 마이그레이션으로 생성.
회원(users) → 동의 이력·리프레시 토큰, 비회원 세션(guest_sessions) → 분석 결과(guest_id) 순으로 이어진다.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CHAR, DateTime, ForeignKey, SmallInteger, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 구글 계정 고유 ID. 이메일 가입 회원은 구글 로그인 시 채워진다
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    # 항상 소문자로 저장한다 (Jiyeon@gmail.com과 jiyeon@gmail.com을 같은 계정으로)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    language: Mapped[str] = mapped_column(String(5))  # ko / en / zh / ja
    nationality: Mapped[str | None] = mapped_column(CHAR(2))  # ISO 3166-1 alpha-2
    resides_in_korea: Mapped[bool | None]
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Terms(Base):
    """약관 버전. 본문은 프론트 locales에 두고 DB에는 종류·버전·필수 여부만 둔다."""

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
    """동의·철회 이력. 수정하지 않고 행을 추가만 한다 (종류별 최신 행이 현재 상태)."""

    __tablename__ = "consent_histories"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    terms_id: Mapped[int] = mapped_column(ForeignKey("terms.id"))
    action: Mapped[str] = mapped_column(String(10))  # AGREE / WITHDRAW


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # 원문은 쿠키에만 있고 DB에는 SHA-256 해시(64자)만 둔다
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EmailVerification(Base):
    """이메일 인증 코드. 이메일당 한 행이라 이메일을 기본키로 두고, 인증에 성공하면 행을 지운다."""

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
    # 해제된 기기는 일반 비회원으로 취급한다
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuestSession(Base):
    """비회원(웹·키오스크) 세션. 분석 결과는 guest_id로 이 세션에 묶인다.

    회원에게 이관되면 user_id가 채워지고 qr_token_hash·expires_at은 NULL이 된다.
    """

    __tablename__ = "guest_sessions"

    # 쿠키(guest_id)와 분석 결과의 guest_id에 들어가는 값. 저장 전에 알 수 있게 파이썬에서 만든다
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # 키오스크에서 만든 세션이면 채워진다 (웹 비회원은 NULL)
    kiosk_id: Mapped[int | None] = mapped_column(ForeignKey("kiosks.id"))
    # IP 원문 대신 HMAC-SHA256. 키오스크 세션은 NULL
    ip_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    qr_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 촬영 전 동의한 얼굴 이미지 약관
    face_terms_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id"))
