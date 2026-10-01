"""계정 모듈 요청·응답 스키마."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import ActorKind


class TermsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    version: str
    required: bool
    effective_at: datetime


class GuestSessionCreate(BaseModel):
    """촬영 전 동의. 얼굴 이미지 약관 동의 + 만 14세 이상 확인."""

    face_terms_id: int = Field(description="GET /api/terms/current의 FACE_IMAGE id")
    age_confirmed: Literal[True] = Field(description="만 14세 이상 확인 (true만 허용)")


class GuestSessionRead(BaseModel):
    # DB에는 해시만 있어서 원문은 이 응답에서만 받을 수 있다
    qr_token: str
    expires_at: datetime


class ActorRead(BaseModel):
    kind: ActorKind
