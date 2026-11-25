from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import literal, select, union_all
from sqlalchemy.orm import Session

from app.api.deps import Actor, require_user
from app.core.cookies import clear_auth_cookies
from app.db.session import get_db
from app.models import HairRecRun, SkinAnalysis, User
from app.schemas.account import (
    AnalysisHistoryItem,
    AnalysisHistoryRead,
    ConsentChangeRequest,
    ConsentStatusRead,
    MeRead,
)
from app.services import account

router = APIRouter(prefix="/me", tags=["me"])


def _get_user(db: Session, actor: Actor) -> User:
    # 탈퇴 직후 남은 액세스 토큰(최대 15분) 대비
    user = db.get(User, actor.user_id)
    if user is None:
        raise HTTPException(401, "로그인이 필요합니다")
    return user


def _to_read(user: User) -> MeRead:
    return MeRead(
        email=user.email,
        nationality=user.nationality,
        resides_in_korea=user.resides_in_korea,
        google_linked=user.google_sub is not None,
    )


@router.get("")
def read_me(actor: Actor = Depends(require_user), db: Session = Depends(get_db)) -> MeRead:
    return _to_read(_get_user(db, actor))


@router.get("/consents")
def read_consents(
    actor: Actor = Depends(require_user), db: Session = Depends(get_db)
) -> list[ConsentStatusRead]:
    """약관 종류별 현재 동의 상태"""
    _get_user(db, actor)
    return [ConsentStatusRead(**vars(s)) for s in account.consent_statuses(db, actor.user_id)]


@router.post("/consents")
def change_consent(
    body: ConsentChangeRequest, actor: Actor = Depends(require_user), db: Session = Depends(get_db)
) -> ConsentStatusRead:
    """선택 약관(PHOTO_STORAGE, MARKETING) 동의·철회, 필수 약관은 400"""
    _get_user(db, actor)
    try:
        status = account.change_consent(db, actor.user_id, body.type, body.action)
    except account.ConsentError as e:
        raise HTTPException(400, str(e)) from None
    db.commit()
    return ConsentStatusRead(**vars(status))


@router.delete("", status_code=204)
def delete_me(actor: Actor = Depends(require_user), db: Session = Depends(get_db)) -> Response:
    """회원 탈퇴: 분석 결과·동의 이력·토큰·비회원 세션까지 삭제 (확인 창은 프론트)"""
    account.delete_user(db, _get_user(db, actor))
    db.commit()
    response = Response(status_code=204)
    clear_auth_cookies(response)
    return response


@router.get("/analyses")
def read_analysis_history(
    kind: str = Query("all", pattern="^(all|skin|hair)$"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    actor: Actor = Depends(require_user),
    db: Session = Depends(get_db),
) -> AnalysisHistoryRead:
    """회원 본인의 피부·헤어 추천 기록. 소유자 필터 후 DB에서 정렬·페이지 분할."""
    _get_user(db, actor)
    sources = []
    if kind in ("all", "skin"):
        sources.append(select(
            literal("skin").label("kind"), SkinAnalysis.id.label("id"),
            SkinAnalysis.analyzed_at.label("created_at"),
        ).where(SkinAnalysis.user_id == actor.user_id))
    if kind in ("all", "hair"):
        sources.append(select(
            literal("hair").label("kind"), HairRecRun.id.label("id"),
            HairRecRun.created_at.label("created_at"),
        ).where(HairRecRun.user_id == actor.user_id))
    history = union_all(*sources).subquery()
    rows = db.execute(select(history).order_by(
        history.c.created_at.desc(), history.c.kind, history.c.id.desc(),
    ).offset(offset).limit(limit + 1)).mappings().all()
    # 다음 페이지 존재 여부만 알아내므로 전체 COUNT 쿼리는 필요 없다.
    return AnalysisHistoryRead(
        items=[AnalysisHistoryItem(**row) for row in rows[:limit]],
        limit=limit, offset=offset, has_more=len(rows) > limit,
    )
