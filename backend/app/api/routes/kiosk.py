from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import Actor, get_actor
from app.core.cookies import (
    KIOSK_COOKIE,
    clear_guest_cookie,
    clear_kiosk_cookie,
    set_guest_cookie,
    set_kiosk_cookie,
)
from app.db.session import get_db
from app.models import Kiosk
from app.schemas.account import (
    GuestSessionCreate,
    GuestSessionRead,
    KioskRead,
    KioskRegisterRequest,
    KioskRevokeRequest,
    KioskStatusRead,
)
from app.services import guest, kiosk, terms

router = APIRouter(prefix="/kiosk", tags=["kiosk"])

NOT_KIOSK = "키오스크로 등록되지 않은 기기입니다"


def _require_admin(code: str) -> None:
    try:
        ok = kiosk.check_admin_code(code)
    except kiosk.AdminCodeNotConfigured:
        raise HTTPException(503, "키오스크가 설정되지 않았습니다 (.env의 ADMIN_CODE 확인)") from None
    if not ok:
        raise HTTPException(403, "관리자 코드가 올바르지 않습니다")


@router.post("/register", status_code=201)
def register_kiosk(
    body: KioskRegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> KioskRead:
    """이 기기를 키오스크로 등록, 해제 전까지 키오스크로 인식"""
    _require_admin(body.admin_code)
    # 같은 기기 재등록이면 이전 등록은 해제 (주인 없는 활성 기기 방지)
    previous = kiosk.find_active(db, request.cookies.get(KIOSK_COOKIE))
    if previous is not None:
        kiosk.revoke(db, previous)
    device, token = kiosk.register(db)
    db.commit()
    set_kiosk_cookie(response, token)
    clear_guest_cookie(response)  # 등록 전 비회원 세션은 이어 쓰지 않음
    return KioskRead(kiosk_id=device.id, registered_at=device.registered_at)


@router.post("/revoke", responses={404: {"description": "없거나 이미 해제된 기기"}})
def revoke_kiosk(
    body: KioskRevokeRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> KioskRead:
    """기기 해제, 이후 일반 비회원 취급 (해제 요청한 기기가 그 기기면 쿠키도 삭제)"""
    _require_admin(body.admin_code)
    device = db.get(Kiosk, body.kiosk_id)
    if device is None or device.revoked_at is not None:
        raise HTTPException(404, "등록된 키오스크가 없습니다")
    kiosk.revoke(db, device)
    db.commit()
    current = kiosk.find_active(db, request.cookies.get(KIOSK_COOKIE))
    if current is None:
        clear_kiosk_cookie(response)
    return KioskRead(kiosk_id=device.id, registered_at=device.registered_at)


@router.get("/me", responses={404: {"description": NOT_KIOSK}})
def read_kiosk(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> KioskStatusRead:
    """이 기기의 키오스크 번호(해제할 때 필요)와 사용 중 여부"""
    if actor.kind != "kiosk":
        raise HTTPException(404, NOT_KIOSK)
    device = db.get(Kiosk, actor.kiosk_id)
    return KioskStatusRead(
        kiosk_id=device.id,
        registered_at=device.registered_at,
        session_active=actor.guest_id is not None,
    )


@router.post("/session", status_code=201, responses={403: {"description": NOT_KIOSK}})
def start_kiosk_session(
    body: GuestSessionCreate,
    response: Response,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
) -> GuestSessionRead:
    """사용자 한 명 시작 (촬영 전 동의), 항상 새 세션 → QR 한 장에 그 사람 결과만"""
    if actor.kind != "kiosk":
        raise HTTPException(403, NOT_KIOSK)
    face_terms = terms.current_terms_of(db, terms.FACE_IMAGE)
    if face_terms is None or face_terms.id != body.face_terms_id:
        raise HTTPException(400, "약관이 갱신되었습니다. 다시 확인해 주세요")

    # 공용 기기라 IP 저장 안 함
    session, qr_token = guest.start_session(
        db, face_terms_id=face_terms.id, ip_hash=None, kiosk_id=actor.kiosk_id
    )
    db.commit()
    set_guest_cookie(response, session.id, session.expires_at)
    return GuestSessionRead(qr_token=qr_token, expires_at=session.expires_at)


@router.delete("/session", status_code=204)
def end_kiosk_session() -> Response:
    """사용자 종료·무입력 타임아웃 시 호출, 세션 쿠키만 삭제 (결과는 QR로 계속 조회)"""
    response = Response(status_code=204)
    clear_guest_cookie(response)
    return response
