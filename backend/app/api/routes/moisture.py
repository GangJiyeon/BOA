"""Stateless telemetry validation: no database mutation or score conversion."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.session import get_db
from app.models.skin import SkinAnalysis
from app.schemas.moisture import MoistureReceipt, MoistureSubmission

router = APIRouter(prefix="/skin/moisture", tags=["skin"])


@router.post("/validate", response_model=MoistureReceipt)
def validate_measurement(body: MoistureSubmission, db: Session = Depends(get_db)):
    if body.measurement.source != "ble_sensor" and not get_settings().moisture_allow_simulation:
        raise HTTPException(403, "가상 측정 수신은 개발 설정에서만 허용됩니다")
    if body.analysis_id is not None and db.get(SkinAnalysis, body.analysis_id) is None:
        raise HTTPException(404, "연결할 피부 분석 결과가 없습니다")
    # This receipt associates an existing analysis ID only for this request.
    # It is not durable storage, ownership authorization, or a calibrated score.
    return MoistureReceipt(**body.model_dump(), server_received_at=datetime.now(timezone.utc))
