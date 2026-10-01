"""개발용 API, DEV_LOGIN=true일 때만 등록 (main.py)"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.schemas.account import DevLoginRead, DevLoginRequest
from app.services import auth

router = APIRouter(prefix="/auth", tags=["dev"])


@router.post("/dev-login")
def dev_login(
    body: DevLoginRequest, response: Response, db: Session = Depends(get_db)
) -> DevLoginRead:
    """인증·가입 없이 바로 로그인, 회원 없으면 생성 (Swagger 테스트용)"""
    email = auth.normalize_email(body.email)
    user = auth.find_user_by_email(db, email)
    if user is None:
        user = User(email=email, language="ko")
        db.add(user)
        db.flush()
    auth.login(db, response, user)
    db.commit()
    return DevLoginRead(user_id=user.id, email=user.email)
