"""계정 모듈 요청·응답 스키마"""

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
    """촬영 전 동의: 얼굴 이미지 약관 + 만 14세 이상 확인"""

    face_terms_id: int = Field(description="GET /api/terms/current의 FACE_IMAGE id")
    age_confirmed: Literal[True] = Field(description="만 14세 이상 확인 (true만 허용)")


class GuestSessionRead(BaseModel):
    # DB에는 해시만 저장, 원문은 이 응답에서만 제공
    qr_token: str
    expires_at: datetime


class ActorRead(BaseModel):
    kind: ActorKind


class DevLoginRequest(BaseModel):
    """개발용 로그인, 회원 없으면 생성 후 로그인"""

    email: str = Field(default="admin0614@test.com", description="소문자로 저장")


class DevLoginRead(BaseModel):
    user_id: int
    email: str
