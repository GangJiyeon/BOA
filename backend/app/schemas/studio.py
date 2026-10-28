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
    # done일 때만 채움, light = 밝은 애쉬 블론드 / mid = 중간 브라운
    light: HairRenderBase | None = None
    mid: HairRenderBase | None = None
