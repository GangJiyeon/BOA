from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Actor, get_actor
from app.core.config import get_settings
from app.core.cookies import REFRESH_COOKIE, clear_auth_cookies, clear_guest_cookie
from app.core.security import create_signup_token, decode_signup_token
from app.db.session import get_db
from app.schemas.account import (
    EmailSendRead,
    EmailSendRequest,
    EmailVerifyRequest,
    GoogleLoginRequest,
    LoginResultRead,
    SignupRead,
    SignupRequest,
)
from app.services import auth, email_auth, google, guest, mail, signup

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
) -> LoginResultRead:
    """코드 확인 후 기존 회원은 로그인, 처음이면 가입 토큰 반환"""
    email = auth.normalize_email(body.email)
    error = email_auth.verify_code(db, email, body.code)
    if error is not None:
        db.commit()  # 틀린 횟수 저장
        raise HTTPException(400, error)

    user = auth.find_user_by_email(db, email)
    if user is None:
        db.commit()
        return LoginResultRead(signup_required=True, signup_token=create_signup_token(email))
    auth.login(db, response, user)
    db.commit()
    return LoginResultRead(signup_required=False, language=user.language)


def complete_google_login(
    db: Session, response: Response, google_user: google.GoogleUser
) -> LoginResultRead:
    """구글 사용자로 로그인 또는 가입 토큰 발급 (POST /google, 개발용 콜백 공통)"""
    email = auth.normalize_email(google_user.email)
    try:
        user = auth.find_or_link_google_user(db, google_user.sub, email)
    except auth.GoogleAccountConflict:
        raise HTTPException(409, "다른 구글 계정과 연결된 이메일입니다") from None
    if user is None:
        token = create_signup_token(email, google_sub=google_user.sub)
        return LoginResultRead(signup_required=True, signup_token=token)
    auth.login(db, response, user)
    db.commit()
    return LoginResultRead(signup_required=False, language=user.language)


def exchange_google_code(code: str, redirect_uri: str) -> google.GoogleUser:
    """구글 오류를 HTTP 오류로 변환"""
    try:
        return google.exchange_code(code, redirect_uri)
    except google.GoogleNotConfigured:
        raise HTTPException(503, "구글 로그인이 설정되지 않았습니다 (.env의 GOOGLE_CLIENT_ID 확인)") from None
    except google.GoogleAuthError as e:
        raise HTTPException(401, str(e)) from None


@router.post(
    "/google",
    responses={401: {"description": "구글 인증 실패"}, 409: {"description": "다른 구글 계정과 연결된 이메일"}},
)
def google_login(
    body: GoogleLoginRequest, response: Response, db: Session = Depends(get_db)
) -> LoginResultRead:
    """구글 로그인: 기존 회원(google_sub 또는 같은 이메일)은 로그인, 처음이면 가입 토큰 반환"""
    google_user = exchange_google_code(body.code, get_settings().google_redirect_uri)
    return complete_google_login(db, response, google_user)


@router.post(
    "/signup",
    status_code=201,
    responses={401: {"description": "가입 토큰 만료"}, 409: {"description": "이미 가입된 이메일"}},
)
def signup_user(
    body: SignupRequest,
    response: Response,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
) -> SignupRead:
    """가입 완료: 회원·동의 이력 생성, 비회원 결과 이관, 로그인 (한 트랜잭션)"""
    if actor.kind == "member":
        raise HTTPException(400, "이미 로그인되어 있습니다")
    claims = decode_signup_token(body.signup_token)
    if claims is None:
        raise HTTPException(401, "인증이 만료되었습니다. 다시 로그인해 주세요")
    if auth.find_user_by_email(db, claims.email) is not None:
        raise HTTPException(409, "이미 가입된 이메일입니다")
    try:
        agreed_terms = signup.validate_terms(db, body.agreed_terms_ids)
    except signup.SignupError as e:
        raise HTTPException(400, str(e)) from None

    try:
        user = signup.create_user(
            db,
            email=claims.email,
            google_sub=claims.google_sub,
            language=body.language,
            nationality=body.nationality,
            resides_in_korea=body.resides_in_korea,
            agreed_terms=agreed_terms,
        )
    except IntegrityError:
        # 동시 가입, 또는 이미 다른 회원에 연결된 구글 계정
        db.rollback()
        raise HTTPException(409, "이미 가입된 계정입니다") from None

    session = guest.find_active_session(db, actor.guest_id)
    if session is not None:
        guest.transfer_to_user(db, session, user.id)
    auth.login(db, response, user)
    db.commit()

    if session is not None:
        clear_guest_cookie(response)  # 세션이 회원 소유가 돼서 불필요
    return SignupRead(user_id=user.id, language=user.language)


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
