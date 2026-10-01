"""현재 약관 조회// 종류별로 시행일이 지난 것 중 가장 최신 버전이 현재 약관"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Terms

FACE_IMAGE = "FACE_IMAGE"


def current_terms(db: Session) -> list[Terms]:
    stmt = (
        select(Terms)
        .where(Terms.effective_at <= func.now())
        .distinct(Terms.type)
        .order_by(Terms.type, Terms.effective_at.desc())
    )
    return list(db.scalars(stmt))


def current_terms_of(db: Session, terms_type: str) -> Terms | None:
    stmt = (
        select(Terms)
        .where(Terms.type == terms_type, Terms.effective_at <= func.now())
        .order_by(Terms.effective_at.desc())
        .limit(1)
    )
    return db.scalar(stmt)
