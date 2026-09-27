from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Image(TimestampMixin, Base):
    """S3에 올라간 이미지. 파일 자체는 S3에, DB에는 key만 저장한다."""

    __tablename__ = "images"

    id: Mapped[int] = mapped_column(primary_key=True)
    s3_key: Mapped[str] = mapped_column(String(512), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
