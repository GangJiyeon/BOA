from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.cosmetic import CosmeticPreviewRequest, CosmeticPreviewResponse
from app.services.cosmetic_catalog import preview_from_database
from app.services.cosmetic_recommendation import RecommendationConfigurationError, RecommendationInputError

router = APIRouter(prefix="/cosmetics", tags=["cosmetics"])


@router.post("/recommendations/preview", response_model=CosmeticPreviewResponse)
def preview_recommendations(body: CosmeticPreviewRequest, db: Session = Depends(get_db)):
    """직접 입력/피부 분석 점수로 최대 5개 제품을 조회한다. 입력과 결과는 저장하지 않는다."""
    try:
        return preview_from_database(db, body)
    except RecommendationInputError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RecommendationConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
