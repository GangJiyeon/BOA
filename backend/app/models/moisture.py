"""Completed relative sensor observations; deliberately not SkinScore rows."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class MoistureObservation(Base):
    __tablename__ = 'moisture_observations'
    id: Mapped[int] = mapped_column(primary_key=True)
    measurement_id: Mapped[str] = mapped_column(String(36), unique=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey('skin_analyses.id', ondelete='CASCADE'), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    analysis: Mapped['SkinAnalysis'] = relationship(back_populates='moisture_observations')
