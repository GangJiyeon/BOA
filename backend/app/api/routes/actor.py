from fastapi import APIRouter, Depends
from app.api.deps import Actor, get_actor
from app.schemas.account import ActorRead

router = APIRouter(tags=["auth"])   # tags=["auth"] 스웨거용

# 요청자 타입 확인 (for httpOnly쿠키)
@router.get("/actor")
def read_actor(actor: Actor = Depends(get_actor)) -> ActorRead:
    return ActorRead(kind=actor.kind)
