from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.cookies import REFRESH_COOKIE, clear_auth_cookies
from app.db.session import get_db
from app.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/refresh", status_code=204, responses={401: {"description": "다시 로그인 필요"}})
def refresh(request: Request, db: Session = Depends(get_db)) -> Response:
    """액세스 토큰 만료(401) 시 호출, 리프레시 토큰도 교체"""
    response = Response(status_code=204)
    ok = auth.rotate_refresh_token(db, response, request.cookies.get(REFRESH_COOKIE))
    db.commit()  # 실패해도 만료 행 삭제는 반영
    if not ok:
        # 인증 쿠키 삭제 (안 지우면 get_actor가 계속 401 반환)
        failed = JSONResponse({"detail": "다시 로그인해 주세요"}, status_code=401)
        clear_auth_cookies(failed)
        return failed
    return response


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    """리프레시 토큰·인증 쿠키 삭제, guest_id 쿠키는 유지"""
    row = auth.find_refresh_token(db, request.cookies.get(REFRESH_COOKIE))
    if row is not None:
        db.delete(row)
        db.commit()
    response = Response(status_code=204)
    clear_auth_cookies(response)
    return response
