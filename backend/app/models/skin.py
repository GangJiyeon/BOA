"""피부 분석 관련 모델.

지표 정의(skin_metrics) → 판정 구간(skin_metric_categories) → 분석 1건(skin_analyses)
→ 지표별 점수(skin_scores) 순으로 이어진다.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# 수분값의 입력 경로. sensor=아두이노 측정, manual=직접 입력, none=수분값 없음(4개 지표만)
MOISTURE_SOURCES = ("sensor", "manual", "none")


class SkinMetric(Base):
    """피부 지표 정의. 수분·홍조·밝기·트러블·균일도 5개가 시드로 들어간다."""

    __tablename__ = "skin_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 코드값으로 조회한다 (id는 환경마다 달라질 수 있으므로 로직에서 직접 쓰지 않는다)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(50))
    # True=점수가 높을수록 양호(수분·밝기·균일도), False=낮을수록 양호(홍조·트러블)
    higher_is_better: Mapped[bool]

    categories: Mapped[list["SkinMetricCategory"]] = relationship(
        back_populates="metric", cascade="all, delete-orphan"
    )


class SkinMetricCategory(Base):
    """지표별 판정 구간. 경계값은 이 테이블의 값만 UPDATE하면 재배포 없이 바뀐다."""

    __tablename__ = "skin_metric_categories"
    __table_args__ = (
        UniqueConstraint("metric_id", "min_score"),
        CheckConstraint("min_score <= max_score", name="score_range"),
        CheckConstraint("min_score >= 0 AND max_score <= 100", name="score_bounds"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_id: Mapped[int] = mapped_column(ForeignKey("skin_metrics.id", ondelete="CASCADE"))
    # 표시용 이름: 개선 필요 / 보통 / 양호
    name: Mapped[str] = mapped_column(String(50))
    min_score: Mapped[int] = mapped_column(SmallInteger)
    max_score: Mapped[int] = mapped_column(SmallInteger)

    metric: Mapped[SkinMetric] = relationship(back_populates="categories")


class SkinAnalysis(Base):
    """분석 1건. 항상 완결된 상태로 생성된다(점수 5개 또는 수분 제외 4개)."""

    __tablename__ = "skin_analyses"
    __table_args__ = (
        CheckConstraint(
            "moisture_source IN ('sensor', 'manual', 'none')", name="moisture_source"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # 인증 파트(users / guest_sessions)가 아직 없어 FK 제약은 걸지 않는다.
    # 해당 테이블이 머지되면 FK 추가 마이그레이션을 별도로 만든다.
    user_id: Mapped[int | None] = mapped_column(index=True)
    guest_id: Mapped[UUID | None] = mapped_column(index=True)

    # 분석에 사용한 원본 사진 (S3 업로드 후 저장된 images 레코드)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="SET NULL"))

    # 판정 기준 버전. 경계값을 바꾼 뒤의 데이터를 구분하기 위해 남긴다.
    logic_version: Mapped[str] = mapped_column(String(20), default="v1")
    moisture_source: Mapped[str] = mapped_column(String(10))

    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # 비회원 분석 결과의 보관 만료 시점 (회원은 NULL)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    scores: Mapped[list["SkinScore"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )


class SkinScore(Base):
    """지표별 점수와 판정 결과.

    category_id를 함께 저장하므로, 이후 경계값이 바뀌어도 과거 판정은 재해석되지 않는다.
    """

    __tablename__ = "skin_scores"
    __table_args__ = (
        UniqueConstraint("analysis_id", "metric_id"),
        CheckConstraint("score BETWEEN 0 AND 100", name="score_bounds"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("skin_analyses.id", ondelete="CASCADE"), index=True
    )
    metric_id: Mapped[int] = mapped_column(ForeignKey("skin_metrics.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("skin_metric_categories.id"))
    # 0~100으로 정규화된 점수 (5개 지표 모두 동일 스케일)
    score: Mapped[int] = mapped_column(SmallInteger)

    analysis: Mapped[SkinAnalysis] = relationship(back_populates="scores")
    metric: Mapped[SkinMetric] = relationship()
    category: Mapped[SkinMetricCategory] = relationship()
