from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ImageContentType = Literal["image/jpeg", "image/png", "image/webp"]


class UploadUrlRequest(BaseModel):
    content_type: ImageContentType


class UploadUrlResponse(BaseModel):
    key: str
    upload_url: str


class ImageCreate(BaseModel):
    key: str
    content_type: ImageContentType


class ImageRead(BaseModel):
    id: int
    url: str
    content_type: str
    created_at: datetime
