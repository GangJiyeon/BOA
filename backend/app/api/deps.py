# 요청자 판별 > user_id / guest_id 필요 시 사용
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.cookies import GUEST_COOKIE
from app.db.session import get_db
from app.services import guest

ActorKind = Literal["member", "guest", "kiosk", "anonymous"]


@dataclass(frozen=True)
class Actor:

    kind: ActorKind
    user_id: int | None = None      # user_id
    guest_id: UUID | None = None    # guest_id
    kiosk_id: int | None = None     # guest_id


def _parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def get_actor(request: Request, db: Session = Depends(get_db)) -> Actor:
    """아래 순서로 확인해서 처음 맞는 요청자를 돌려준다.

    쿠키는 Cookie() 파라미터 대신 request에서 읽는다. 그래야 Swagger 화면에
    쿠키 입력칸이 생기지 않고, 브라우저가 가진 쿠키가 그대로 쓰인다.
    """
    # 1. 키오스크: kiosk_token 쿠키 (8단계)
    # 2. 회원: access_token 쿠키 (2단계)
    # 3. 비회원
    session = guest.find_active_session(db, _parse_uuid(request.cookies.get(GUEST_COOKIE)))
    if session is not None:
        return Actor(kind="guest", guest_id=session.id)
    # 4. 익명
    return Actor(kind="anonymous")


def require_analysis_actor(actor: Actor = Depends(get_actor)) -> Actor:
    """분석 API용. 익명(촬영 동의 전)이면 거부한다."""
    if actor.kind == "anonymous":
        raise HTTPException(403, "촬영 동의가 필요합니다")
    return actor
