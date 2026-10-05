"""수집 원문 관측 이력. 함량 문자열은 검증된 농도나 추천 점수가 아니다."""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CosmeticObservationBatch(Base):
    __tablename__ = "cosmetic_observation_batches"
    __table_args__ = (
        CheckConstraint("record_count >= 0 AND amount_count >= 0 AND amount_count <= record_count", name="observation_counts"),
    )
    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_file_sha256: Mapped[str] = mapped_column(String(64))
    payload_hash: Mapped[str] = mapped_column(String(64))
    importer_version: Mapped[str] = mapped_column(String(40))
    record_count: Mapped[int] = mapped_column(Integer)
    amount_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProductIngredientObservation(Base):
    __tablename__ = "product_ingredient_observations"
    __table_args__ = (
        ForeignKeyConstraint(["product_id", "ingredient_id"],
                             ["product_ingredients.product_id", "product_ingredients.ingredient_id"]),
        CheckConstraint("source_position >= 0", name="observation_position"),
        CheckConstraint("review_status = 'unreviewed'", name="observation_review_status"),
    )
    batch_id: Mapped[str] = mapped_column(String(64), ForeignKey("cosmetic_observation_batches.batch_id"), primary_key=True)
    source_formula_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    source_position: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(BigInteger, index=True)
    ingredient_id: Mapped[int] = mapped_column(BigInteger)
    source_product_id: Mapped[str] = mapped_column(String(255))
    source_ingredient_id: Mapped[int] = mapped_column(BigInteger)
    source_url: Mapped[str] = mapped_column(Text)
    source_record_hash: Mapped[str] = mapped_column(Text)
    raw_token: Mapped[str] = mapped_column(Text)
    amount_text: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(20), default="unreviewed")
