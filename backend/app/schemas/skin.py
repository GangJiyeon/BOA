"""피부 분석 API 요청·응답 스키마."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from app.schemas.moisture import CompletedReceipt

MoistureSource = Literal["sensor", "manual", "none"]


class ScoreRead(BaseModel):
    """지표 1개의 점수와 판정 결과."""

    metric_code: str
    metric_name: str
    score: int
    category_name: str
    # 이 지표가 높을수록 좋은지 (프론트에서 게이지 방향 표시에 사용)
    higher_is_better: bool


class AnalysisRead(BaseModel):
    moisture_measurement: CompletedReceipt | None = None
    id: int
    analyzed_at: datetime
    logic_version: str
    moisture_source: MoistureSource
    image_id: int | None
    scores: list[ScoreRead]


class DebugAnalysisRead(AnalysisRead):
    """디버그 응답. 정규화 전 원시값을 함께 내려 임계값 조정에 쓴다."""

    raw: dict[str, float]

