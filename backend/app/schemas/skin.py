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
