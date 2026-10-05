from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.account import TermsRead
from app.services import terms

router = APIRouter(prefix="/terms", tags=["terms"])


@router.get("/current")
def get_current_terms(db: Session = Depends(get_db)) -> list[TermsRead]:
    """종류별 현재 약관 (가입 화면, 촬영 전 동의 화면용)"""
    return [TermsRead.model_validate(t) for t in terms.current_terms(db)]
