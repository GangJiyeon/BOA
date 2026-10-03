from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import Actor, require_user
from app.api.routes.skin import to_read
from app.db.session import get_db
from app.models import GuestSession, SkinAnalysis, SkinScore
from app.schemas.account import QrClaimRead, QrResultRead
from app.schemas.skin import AnalysisRead
from app.services import guest

router = APIRouter(prefix="/qr", tags=["qr"])

# 없는 토큰·만료·이관 구분 안 함 (토큰 존재 여부 노출 방지)
EXPIRED = "만료된 링크입니다"


def _get_session(db: Session, token: str) -> GuestSession:
    session = guest.find_by_qr_token(db, token)
    if session is None:
        raise HTTPException(404, EXPIRED)
    return session


def _skin_results(db: Session, session: GuestSession) -> list[AnalysisRead]:
    analyses = db.scalars(
        select(SkinAnalysis)
        .where(SkinAnalysis.guest_id == session.id)
        .order_by(SkinAnalysis.analyzed_at)
        .options(
            selectinload(SkinAnalysis.scores).selectinload(SkinScore.metric),
            selectinload(SkinAnalysis.scores).selectinload(SkinScore.category),
        )
    )
    # Kim 응답 형식 재사용, 사진 id만 비움
    return [to_read(a).model_copy(update={"image_id": None}) for a in analyses]


@router.get("/{token}", responses={404: {"description": "만료된 링크"}})
def read_qr(token: str, db: Session = Depends(get_db)) -> QrResultRead:
    """QR 결과 조회 (로그인 불필요)"""
    session = _get_session(db, token)
    return QrResultRead(expires_at=session.expires_at, skin=_skin_results(db, session))


@router.post("/{token}/claim", responses={404: {"description": "만료된 링크"}})
def claim_qr(
    token: str, actor: Actor = Depends(require_user), db: Session = Depends(get_db)
) -> QrClaimRead:
    """내 계정에 저장, 이후 같은 QR은 만료됨 (키오스크 QR로 회원 결과 조회 방지)"""
    session = _get_session(db, token)
    skin_count = db.scalar(
        select(func.count()).select_from(SkinAnalysis).where(SkinAnalysis.guest_id == session.id)
    )
    guest.transfer_to_user(db, session, actor.user_id)
    db.commit()
    return QrClaimRead(skin_count=skin_count)
