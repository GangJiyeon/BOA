from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HairRenderBase(BaseModel):
    image: str = Field(description="얼굴 복원까지 끝난 베이스 이미지 URL")
    mask: str = Field(description="머리 마스크 PNG URL (흰색일수록 머리)")


class HairRenderRead(BaseModel):
    id: int
    style_id: str
    status: Literal["pending", "done", "failed"]
    error: str | None
    created_at: datetime
    # 세 베이스는 합성 완료 시 함께 제공
    mid: HairRenderBase | None = None
    brown: HairRenderBase | None = Field(None, description="중간 갈색 베이스 (중간톤 색용)")
    light: HairRenderBase | None = None
    hair_hex: str | None = Field(None, description="원본 사진 속 머리색 #rrggbb")
