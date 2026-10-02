"""헤어 추천 관련 모델.

얼굴형 분석(face_analyses) → 사용자 선호도(user_hair_preferences) + 스타일 카탈로그(hair_style_catalog)
→ 추천 실행 1건(hair_rec_runs) → 추천 결과 N개(hair_recommendations) 순으로 이어진다.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FaceAnalysis(Base):
    """얼굴형 분석 1건. 사진 3장의 랜드마크 비율을 중앙값으로 취합한 결과를 담는다."""

    __tablename__ = "face_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 인증 파트(users / guest_sessions)가 아직 없어 FK 제약은 걸지 않는다.
    # 해당 테이블이 머지되면 FK 추가 마이그레이션을 별도로 만든다.
    user_id: Mapped[int | None] = mapped_column(index=True)
    guest_id: Mapped[UUID | None] = mapped_column(index=True)

    # 분석에 사용한 원본 사진 (S3 업로드 후 저장된 images 레코드)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="SET NULL"))

    # 계란형 / 둥근형 / 사각형 / 긴형 / 하트형 / 다이아몬드형
    face_shape: Mapped[str] = mapped_column(String(20))
    # 2순위 후보 얼굴형 (경계선상 케이스 참고용)
    top2: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    # 얼굴형 판별에 쓰인 원본 비율값 (얼굴길이/광대너비, 턱너비/광대너비, 이마너비/턱너비, 턱각도, 광대돌출도)
    ratios: Mapped[dict | None] = mapped_column(JSONB)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    runs: Mapped[list["HairRecRun"]] = relationship(back_populates="face_analysis")


class UserHairPreferences(Base):
    """회원별 헤어 선호도. 비회원은 매 요청마다 선호도를 직접 전달하므로 이 테이블을 쓰지 않는다."""

    __tablename__ = "user_hair_preferences"

    # 인증 파트가 머지되기 전까지는 FK 없이 PK만 건다.
    user_id: Mapped[int] = mapped_column(primary_key=True)
    texture_pref: Mapped[str | None] = mapped_column(String(30))
    length_pref: Mapped[str | None] = mapped_column(String(30))

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class HairStyleCatalog(Base):
    """헤어 스타일 카탈로그. 얼굴형별 적합도(face_fit)는 0~1 사이 값을 JSONB로 저장한다."""

    __tablename__ = "hair_style_catalog"

    style_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    length: Mapped[str] = mapped_column(String(30))
    texture: Mapped[str] = mapped_column(String(30))
    # 예: {"둥근형": 0.9, "계란형": 0.7, ...}
    face_fit: Mapped[dict] = mapped_column(JSONB)
    asset_id: Mapped[str | None] = mapped_column(String(100))
    image: Mapped[str | None] = mapped_column(String(500))
    # 시술 시간, 유지 관리 주기 등 상담 가이드 텍스트
    guide: Mapped[str | None] = mapped_column(String(1000))

    recommendations: Mapped[list["HairRecommendation"]] = relationship(back_populates="style")


class HairRecRun(Base):
    """추천 실행 1건. 같은 얼굴 분석 결과에 대해 선호 조건을 바꿔가며 여러 번 실행될 수 있다."""

    __tablename__ = "hair_rec_runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 인증 파트가 아직 없어 FK 제약은 걸지 않는다.
    user_id: Mapped[int | None] = mapped_column(index=True)
    guest_id: Mapped[UUID | None] = mapped_column(index=True)

    face_analysis_id: Mapped[int] = mapped_column(
        ForeignKey("face_analyses.id", ondelete="CASCADE"), index=True
    )

    # 이번 실행에 적용한 선호 조건 (회원이면 user_hair_preferences와 다를 수 있음 - 임시 변경 허용)
    preferred_length: Mapped[str | None] = mapped_column(String(30))
    preferred_texture: Mapped[str | None] = mapped_column(String(30))
    # Score = 0.5*face_fit + 0.25*texture_fit + 0.25*length_fit 의 가중치. 기본값 외 커스텀 실행 대비
    weights: Mapped[dict | None] = mapped_column(JSONB)
    top_n: Mapped[int] = mapped_column(SmallInteger, default=5)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    face_analysis: Mapped[FaceAnalysis] = relationship(back_populates="runs")
    recommendations: Mapped[list["HairRecommendation"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class HairRecommendation(Base):
    """추천 결과 1건. 한 run 안에서 rank로 순위를 매긴다."""

    __tablename__ = "hair_recommendations"
    __table_args__ = (UniqueConstraint("run_id", "rank"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("hair_rec_runs.id", ondelete="CASCADE"), index=True
    )
    rank: Mapped[int] = mapped_column(SmallInteger)
    style_id: Mapped[str] = mapped_column(ForeignKey("hair_style_catalog.style_id"))

    face_fit: Mapped[float] = mapped_column(Numeric(5, 4))
    texture_fit: Mapped[float] = mapped_column(Numeric(5, 4))
    length_fit: Mapped[float] = mapped_column(Numeric(5, 4))
    # 0.5*face_fit + 0.25*texture_fit + 0.25*length_fit
    score: Mapped[float] = mapped_column(Numeric(5, 4))

    run: Mapped[HairRecRun] = relationship(back_populates="recommendations")
    style: Mapped[HairStyleCatalog] = relationship(back_populates="recommendations")