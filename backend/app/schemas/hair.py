from datetime import datetime

from pydantic import BaseModel, Field


class LandmarkPoint(BaseModel):
    x: float
    y: float


# face_shape_analysis.REQUIRED_POINTS 와 동일한 11개 키가 모두 있어야 한다
LandmarkSet = dict[str, LandmarkPoint]


class FaceAnalysisRequest(BaseModel):
    # 1장(single) 또는 3장(triple) 분량의 랜드마크 세트
    landmark_sets: list[LandmarkSet] = Field(min_length=1, max_length=3)
    user_id: int | None = None
    guest_id: str | None = None  # UUID 문자열
    image_id: int | None = None


class FaceAnalysisResult(BaseModel):
    id: int
    face_shape: str
    top2: str | None
    confidence: float | None
    source: str
    ratios: dict[str, float] | None
    updated_at: datetime


class HairRecommendRequest(BaseModel):
    face_analysis_id: int
    user_id: int | None = None
    guest_id: str | None = None
    preferred_length: str | None = None
    preferred_texture: str | None = None
    top_n: int = 5
    weights: dict[str, float] | None = None  # 기본값: {"face":0.5,"texture":0.25,"length":0.25}


class HairRecommendationItem(BaseModel):
    rank: int
    style_id: str
    name: str
    face_fit: float
    texture_fit: float | None
    length_fit: float | None
    score: float
    note: str | None
    asset_id: str | None
    image: str | None


class HairRecommendResult(BaseModel):
    run_id: int
    face_analysis_id: int
    preferred_length: str | None
    preferred_texture: str | None
    created_at: datetime
    recommendations: list[HairRecommendationItem]


class HairStyleCreate(BaseModel):
    style_id: str
    name: str
    length: str
    texture: str
    face_fit: dict[str, float]
    asset_id: str | None = None
    image: str | None = None
    guide: str | None = None


class HairStyleRead(HairStyleCreate):
    pass