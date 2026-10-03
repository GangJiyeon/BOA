from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import Actor, require_user
from app.core.cookies import clear_auth_cookies
from app.db.session import get_db
from app.models import User
from app.schemas.account import (
    ConsentChangeRequest,
    ConsentStatusRead,
    MeRead,
    MeUpdate,
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
        language=user.language,
        nationality=user.nationality,
        resides_in_korea=user.resides_in_korea,
        google_linked=user.google_sub is not None,
    )


@router.get("")
def read_me(actor: Actor = Depends(require_user), db: Session = Depends(get_db)) -> MeRead:
    return _to_read(_get_user(db, actor))


@router.patch("")
def update_me(
    body: MeUpdate, actor: Actor = Depends(require_user), db: Session = Depends(get_db)
) -> MeRead:
    """언어 변경 (프론트는 응답의 language로 lang 쿠키 갱신)"""
    user = _get_user(db, actor)
    user.language = body.language
    db.commit()
    return _to_read(user)


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
