"""AI 스튜디오 헤어 합성 결과

요청 1건 = 1행, 이미지 파일은 studio_dir/{asset_dir}/ 아래
(light.jpg, light_mask.png, mid.jpg, mid_mask.png)
원본 얼굴 사진은 저장 안 함
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HairRender(Base):
    __tablename__ = "hair_renders"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 다른 결과 테이블과 같이 회원·세션 FK 없음
    user_id: Mapped[int | None] = mapped_column(index=True)
    guest_id: Mapped[UUID | None] = mapped_column(index=True)

    run_id: Mapped[int | None] = mapped_column(ForeignKey("hair_rec_runs.id", ondelete="SET NULL"))
    style_id: Mapped[str] = mapped_column(ForeignKey("hair_style_catalog.style_id"))

    # pending / done / failed
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(String(300))
    # 추측 불가 폴더명 (공개 static 경로라서)
    asset_dir: Mapped[str] = mapped_column(String(64), unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
