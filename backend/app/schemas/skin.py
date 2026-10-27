"""피부 분석 API 요청·응답 스키마."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

MoistureSource = Literal["sensor", "manual", "none"]


class AnalysisCreate(BaseModel):
    """분석 생성 요청.

    사진은 S3 업로드(POST /api/images)가 끝난 뒤의 image_id로 넘긴다.
    수분값은 moisture_source에 따라 필요한 필드가 달라진다.
    """

    image_id: int | None = None
    moisture_source: MoistureSource = "none"
    # 아두이노 센서 원시값 (moisture_source=sensor일 때)
    moisture_raw: int | None = Field(default=None, ge=0, le=1023)
    # 직접 입력 점수 (moisture_source=manual일 때 — 디버깅·센서 장애 대체용)
    moisture_score: int | None = Field(default=None, ge=0, le=100)

    # 비회원 분석일 때 클라이언트가 보유한 게스트 식별자
    guest_id: UUID | None = None

    @model_validator(mode="after")
    def check_moisture(self):
        """source와 실제로 들어온 수분값이 어긋나는 요청을 미리 막는다."""
        if self.moisture_source == "sensor" and self.moisture_raw is None:
            raise ValueError("moisture_source가 sensor이면 moisture_raw가 필요합니다")
        if self.moisture_source == "manual" and self.moisture_score is None:
            raise ValueError("moisture_source가 manual이면 moisture_score가 필요합니다")
        if self.moisture_source == "none" and (
            self.moisture_raw is not None or self.moisture_score is not None
        ):
            raise ValueError("moisture_source가 none이면 수분값을 보내지 않습니다")
        return self


class ScoreRead(BaseModel):
    """지표 1개의 점수와 판정 결과."""

    metric_code: str
    metric_name: str
    score: int
    category_name: str
    # 이 지표가 높을수록 좋은지 (프론트에서 게이지 방향 표시에 사용)
    higher_is_better: bool


class AnalysisRead(BaseModel):
    id: int
    analyzed_at: datetime
    logic_version: str
    moisture_source: MoistureSource
    image_id: int | None
    scores: list[ScoreRead]


class DebugAnalysisRead(AnalysisRead):
    """디버그 응답. 정규화 전 원시값을 함께 내려 임계값 조정에 쓴다."""

    raw: dict[str, float]


# ── 재현성 측정 (디버그) ─────────────────────────────────────────────


class RepeatabilityPhoto(BaseModel):
    """사진 한 장의 분석 결과."""

    file: str
    scores: dict[str, int]          # 지표 코드 → 점수
    categories: dict[str, str]      # 지표 코드 → 판정 (양호/보통/개선 필요)
    raw: dict[str, float]           # 정규화 전 원시값 (부위별 노출 비율 포함)


class RepeatabilityRejected(BaseModel):
    """분석이 거절된 사진 (얼굴 미검출·노출 이상 등)."""

    file: str
    code: str
    message: str


class RepeatabilityMetric(BaseModel):
    """지표 하나의 반복 측정 통계."""

    metric_code: str
    raw_key: str                    # 통계를 낸 원시값 이름
    raw_mean: float
    raw_std: float
    raw_cv_percent: float | None    # 변동계수. 평균이 0에 가까우면 의미가 없어 null
    score_min: int
    score_max: int
    score_range: int
    categories: list[str]           # 나온 판정 종류 (1개면 모든 사진의 판정이 같음)
    category_agreed: bool
    judged_by: Literal["cv", "score_range"]  # 아래 passed를 무엇으로 판단했는지
    passed: bool


class RepeatabilityReport(BaseModel):
    """같은 사람·같은 조건 반복 촬영의 재현성 리포트."""

    photo_count: int                # 분석에 성공한 사진 수
    rejected_count: int
    metrics: list[RepeatabilityMetric]
    regions_consistent: bool        # 모든 사진에서 같은 부위가 분석에 쓰였는지
    region_sets: dict[str, list[str]]  # 사진별 사용 부위 (regions_consistent가 false일 때 확인)
    photos: list[RepeatabilityPhoto]
    rejected: list[RepeatabilityRejected]
    criteria: dict[str, float]      # 적용한 합격 기준
