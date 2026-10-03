"""로그인 성공 처리, 리프레시 토큰 관리

모든 로그인(이메일·구글·개발용)은 login() 사용, 커밋은 호출하는 쪽에서
"""

from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.cookies import set_auth_cookies
from app.core.security import create_access_token, hash_token, new_token
from app.models import RefreshToken, User


def normalize_email(email: str) -> str:
    """모든 로그인·가입에서 사용 (Jiyeon@gmail.com = jiyeon@gmail.com)"""
    return email.strip().lower()


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


class GoogleAccountConflict(Exception):
    pass


def find_or_link_google_user(db: Session, google_sub: str, email: str) -> User | None:
    """google_sub로 회원 조회, 없으면 같은 이메일 회원에 구글 연결, 둘 다 없으면 None

    이메일 연결은 구글이 email_verified를 보장한 경우만 (google.verify_id_token에서 확인)
    """
    user = db.scalar(select(User).where(User.google_sub == google_sub))
    if user is not None:
        return user
    user = find_user_by_email(db, email)
    if user is None:
        return None
    if user.google_sub is not None:
        # 같은 이메일이 다른 구글 계정과 이미 연결됨
        raise GoogleAccountConflict
    user.google_sub = google_sub
    return user


def issue_tokens(db: Session, response: Response, user_id: int) -> None:
    """액세스 토큰(JWT) + 새 리프레시 토큰 쿠키 발급, DB에는 리프레시 토큰 해시만 저장"""
    refresh_token = new_token()
    expires_at = datetime.now(UTC) + timedelta(days=get_settings().refresh_token_days)
    db.add(RefreshToken(user_id=user_id, token_hash=hash_token(refresh_token), expires_at=expires_at))
    set_auth_cookies(response, create_access_token(user_id), refresh_token, expires_at)


def login(db: Session, response: Response, user: User) -> None:
    user.last_login_at = datetime.now(UTC)
    issue_tokens(db, response, user.id)


def find_refresh_token(db: Session, token: str | None) -> RefreshToken | None:
    """만료 여부와 관계없이 해시로 조회 (로그아웃 시 만료 토큰도 삭제)"""
    if not token:
        return None
    return db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(token)))


def rotate_refresh_token(db: Session, response: Response, token: str | None) -> bool:
    """유효한 리프레시 토큰이면 삭제 후 새 토큰 쌍 발급

    매번 교체 → 예전 토큰은 행이 없어 거부됨
    """
    row = find_refresh_token(db, token)
    if row is None:
        return False
    if row.expires_at <= datetime.now(UTC):
        db.delete(row)
        return False
    user_id = row.user_id
    db.delete(row)
    issue_tokens(db, response, user_id)
    return True
