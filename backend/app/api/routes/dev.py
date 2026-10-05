"""개발용 API, DEV_LOGIN=true일 때만 등록 (main.py)"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.routes.auth import complete_google_login, exchange_google_code
from app.db.session import get_db
from app.models import User
from app.schemas.account import DevLoginRead, DevLoginRequest, LoginResultRead
from app.services import auth, google

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


@router.get("/google/dev-start", response_class=RedirectResponse)
def google_dev_start(request: Request) -> RedirectResponse:
    """브라우저로 열기 → 구글 로그인 → dev-callback에서 결과 확인 (Swagger로는 못 엶)

    구글 콘솔에 리디렉션 URI 등록 필요: http://localhost:8000/api/auth/google/dev-callback
    """
    if not google.is_configured():
        raise HTTPException(503, "구글 로그인이 설정되지 않았습니다 (.env의 GOOGLE_CLIENT_ID 확인)")
    return RedirectResponse(google.authorization_url(str(request.url_for("google_dev_callback"))))


@router.get("/google/dev-callback", name="google_dev_callback")
def google_dev_callback(
    code: str, request: Request, response: Response, db: Session = Depends(get_db)
) -> LoginResultRead:
    """구글이 돌려보내는 주소, 결과(로그인 또는 signup_token)를 JSON으로 표시"""
    google_user = exchange_google_code(code, str(request.url_for("google_dev_callback")))
    return complete_google_login(db, response, google_user)
