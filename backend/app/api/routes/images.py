import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Image
from app.schemas.image import ImageCreate, ImageRead, UploadUrlRequest, UploadUrlResponse
from app.services import s3

router = APIRouter(prefix="/images", tags=["images"])

EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def require_s3():
    if not get_settings().s3_enabled:
        raise HTTPException(503, "S3가 설정되지 않았습니다 (.env의 S3_BUCKET 확인)")


def to_read(image: Image) -> ImageRead:
    return ImageRead(
        id=image.id,
        url=s3.presigned_download_url(image.s3_key),
        content_type=image.content_type,
        created_at=image.created_at,
    )


@router.post("/upload-url", dependencies=[Depends(require_s3)])
def create_upload_url(body: UploadUrlRequest) -> UploadUrlResponse:
    """1단계: 브라우저가 S3에 직접 PUT 할 수 있는 presigned URL을 발급한다."""
    key = f"images/{uuid.uuid4()}.{EXTENSIONS[body.content_type]}"
    return UploadUrlResponse(key=key, upload_url=s3.presigned_upload_url(key, body.content_type))


@router.post("", status_code=201, dependencies=[Depends(require_s3)])
def create_image(body: ImageCreate, db: Session = Depends(get_db)) -> ImageRead:
    """2단계: 업로드가 끝난 뒤 key를 DB에 저장한다."""
    image = Image(s3_key=body.key, content_type=body.content_type)
    db.add(image)
    db.commit()
    db.refresh(image)
    return to_read(image)


@router.get("", dependencies=[Depends(require_s3)])
def list_images(db: Session = Depends(get_db)) -> list[ImageRead]:
    images = db.scalars(select(Image).order_by(Image.id.desc())).all()
    return [to_read(i) for i in images]
