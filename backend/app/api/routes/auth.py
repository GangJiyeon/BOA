from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.cookies import REFRESH_COOKIE, clear_auth_cookies
from app.core.security import create_signup_token
from app.db.session import get_db
from app.schemas.account import (
    EmailSendRead,
    EmailSendRequest,
    EmailVerifyRead,
    EmailVerifyRequest,
)
from app.services import auth, email_auth, mail

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/email/send", responses={429: {"description": "재발송 간격 안"}})
def send_email_code(body: EmailSendRequest, db: Session = Depends(get_db)) -> EmailSendRead:
    """인증 코드 발송, 가입 여부와 관계없이 같은 응답 (가입된 이메일 탐색 방지)"""
    settings = get_settings()
    email = auth.normalize_email(body.email)
    try:
        code = email_auth.issue_code(db, email)
    except email_auth.ResendTooSoon:
        raise HTTPException(429, "잠시 후 다시 요청해 주세요") from None
    db.commit()
    mail.send_login_code(email, code)
    return EmailSendRead(
        resend_seconds=settings.email_resend_seconds,
        dev_code=code if settings.dev_login else None,
    )


@router.post("/email/verify")
def verify_email_code(
    body: EmailVerifyRequest, response: Response, db: Session = Depends(get_db)
) -> EmailVerifyRead:
    """코드 확인 후 기존 회원은 로그인, 처음이면 가입 토큰 반환"""
    email = auth.normalize_email(body.email)
    error = email_auth.verify_code(db, email, body.code)
    if error is not None:
        db.commit()  # 틀린 횟수 저장
        raise HTTPException(400, error)

    user = auth.find_user_by_email(db, email)
    if user is None:
        db.commit()
        return EmailVerifyRead(signup_required=True, signup_token=create_signup_token(email))
    auth.login(db, response, user)
    db.commit()
    return EmailVerifyRead(signup_required=False, language=user.language)


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
