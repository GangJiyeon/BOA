# 요청자 판별 > user_id / guest_id 필요 시 사용
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.cookies import ACCESS_COOKIE, GUEST_COOKIE, KIOSK_COOKIE
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User
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
        if user_id is None or db.get(User, user_id) is None:
            # 만료·위조 토큰과 탈퇴한 회원은 거부 (비회원으로 넘기면 결과 소유자가 바뀔 수 있음)
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


class OwnedResult(Protocol):
    user_id: int | None
    guest_id: UUID | None


def require_owned_result(result: OwnedResult | None, actor: Actor) -> None:
    """회원 소유권을 우선한다. 이관 전 guest_id로 회원 결과를 읽을 수 없다."""
    if result is not None:
        if result.user_id is not None:
            if actor.kind == "member" and result.user_id == actor.user_id:
                return
        elif actor.guest_id is not None and result.guest_id == actor.guest_id:
            return
    # 존재 여부도 다른 사용자에게 공개하지 않는다.
    raise HTTPException(404, "분석 결과를 찾을 수 없습니다")
