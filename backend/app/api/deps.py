# 요청자 판별 > user_id / guest_id 필요 시 사용
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.cookies import ACCESS_COOKIE, GUEST_COOKIE, KIOSK_COOKIE
from app.core.security import decode_access_token
from app.db.session import get_db
from app.services import guest, kiosk

ActorKind = Literal["member", "guest", "kiosk", "anonymous"]


@dataclass(frozen=True)
class Actor:

    kind: ActorKind
    user_id: int | None = None      # user_id
    guest_id: UUID | None = None    # guest_id
    kiosk_id: int | None = None     # kiosk_id


def _parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def get_actor(request: Request, db: Session = Depends(get_db)) -> Actor:
    """아래 순서로 확인, 처음 맞는 요청자 반환

    쿠키는 request에서 직접 읽음 (Cookie() 쓰면 Swagger에 입력칸 생김)
    """
    guest_id = _parse_uuid(request.cookies.get(GUEST_COOKIE))
    # 1. 키오스크: 해제 안 된 kiosk_token (해제·위조 토큰은 무시 → 아래 판별로)
    device = kiosk.find_active(db, request.cookies.get(KIOSK_COOKIE))
    if device is not None:
        session = guest.find_active_session(db, guest_id)
        # 이 기기에서 시작한 세션만 인정 (동의 전이면 guest_id 없음)
        session_id = session.id if session is not None and session.kiosk_id == device.id else None
        return Actor(kind="kiosk", guest_id=session_id, kiosk_id=device.id)
    # 2. 회원: access_token 쿠키
    access_token = request.cookies.get(ACCESS_COOKIE)
    if access_token:
        user_id = decode_access_token(access_token)
        if user_id is None:
            # 만료·위조 토큰은 거부 (비회원으로 넘기면 회원 결과가 비회원 쪽에 저장될 수 있음)
            # 프론트는 POST /api/auth/refresh 후 재요청
            raise HTTPException(401, "로그인이 만료되었습니다")
        return Actor(kind="member", user_id=user_id)
    # 3. 비회원
    session = guest.find_active_session(db, guest_id)
    if session is not None:
        return Actor(kind="guest", guest_id=session.id)
    # 4. 익명
    return Actor(kind="anonymous")


def require_analysis_actor(actor: Actor = Depends(get_actor)) -> Actor:
    """분석 API용, 촬영 동의 전(익명, 세션 없는 키오스크)이면 403"""
    if actor.kind == "anonymous" or (actor.kind == "kiosk" and actor.guest_id is None):
        raise HTTPException(403, "촬영 동의가 필요합니다")
    return actor


def require_user(actor: Actor = Depends(get_actor)) -> Actor:
    """로그인 필요한 API용 (마이페이지 등), 회원 아니면 401"""
    if actor.kind != "member":
        raise HTTPException(401, "로그인이 필요합니다")
    return actor
