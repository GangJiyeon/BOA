from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import Actor, get_actor
from app.core.cookies import set_guest_cookie
from app.core.security import client_ip, hash_ip
from app.db.session import get_db
from app.schemas.account import GuestSessionCreate, GuestSessionRead
from app.services import guest, terms

router = APIRouter(prefix="/guest", tags=["guest"])


@router.post("/session", status_code=201)
def create_guest_session(
    body: GuestSessionCreate,
    request: Request,
    response: Response,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
) -> GuestSessionRead:
    """촬영 전 동의 + 비회원 세션 발급

    유효한 세션이 이미 있으면 그 세션을 이어 쓰고 QR 토큰만 새로 발급
    """
    if actor.kind == "member":
        raise HTTPException(400, "회원은 비회원 세션이 필요하지 않습니다")

    face_terms = terms.current_terms_of(db, terms.FACE_IMAGE)
    if face_terms is None or face_terms.id != body.face_terms_id:
        raise HTTPException(400, "약관이 갱신되었습니다. 다시 확인해 주세요")

    session, qr_token = guest.start_session(
        db,
        face_terms_id=face_terms.id,
        ip_hash=hash_ip(client_ip(request)),
        existing=guest.find_active_session(db, actor.guest_id),
    )
    db.commit()

    set_guest_cookie(response, session.id, session.expires_at)
    return GuestSessionRead(qr_token=qr_token, expires_at=session.expires_at)
