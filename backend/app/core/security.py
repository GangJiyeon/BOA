"""토큰·IP 해시 유틸

액세스 토큰: JWT(user_id, 15분), DB 조회 없이 검증
QR·키오스크·리프레시 토큰: 긴 무작위 값이라 SHA-256 해시로 저장·조회
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Request

from app.core.config import get_settings

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"
SIGNUP_TOKEN_TYPE = "signup"


def _encode(token_type: str, sub: str, minutes: int, **claims: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,  # PyJWT는 sub 문자열만 허용
        "type": token_type,  # 액세스·가입 토큰 구분용
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        **claims,
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=JWT_ALGORITHM)


def _decode(token: str, token_type: str) -> dict | None:
    """유효하면 payload, 만료·위조·종류 불일치면 None"""
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != token_type:
        return None
    return payload


def create_access_token(user_id: int) -> str:
    return _encode(ACCESS_TOKEN_TYPE, str(user_id), get_settings().access_token_minutes)


def decode_access_token(token: str) -> int | None:
    """유효하면 user_id, 만료·위조면 None"""
    payload = _decode(token, ACCESS_TOKEN_TYPE)
    return int(payload["sub"]) if payload is not None else None


@dataclass(frozen=True)
class SignupClaims:
    email: str
    google_sub: str | None  # 구글 가입이면 채움


def create_signup_token(email: str, google_sub: str | None = None) -> str:
    """이메일(또는 구글) 인증 완료 표시, 가입 API에서 사용 (응답 본문으로 전달)"""
    claims = {"google_sub": google_sub} if google_sub else {}
    return _encode(SIGNUP_TOKEN_TYPE, email, get_settings().signup_token_minutes, **claims)


def decode_signup_token(token: str) -> SignupClaims | None:
    """유효하면 email·google_sub, 만료·위조면 None"""
    payload = _decode(token, SIGNUP_TOKEN_TYPE)
    if payload is None:
        return None
    return SignupClaims(email=payload["sub"], google_sub=payload.get("google_sub"))


def hash_email_code(email: str, code: str) -> str:
    """6자리 코드는 경우의 수가 적어 HMAC 사용 (DB 유출 시 대입 방지), 이메일에 묶음"""
    key = get_settings().jwt_secret.encode()
    return hmac.new(key, f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_ip(ip: str) -> str:
    """IP 원문 대신 HMAC 저장, 같은 IP끼리 비교만 가능"""
    key = get_settings().ip_hash_secret.encode()
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()


def client_ip(request: Request) -> str:
    # TODO(배포): 프록시 뒤에서는 uvicorn --proxy-headers로 X-Forwarded-For 반영
    return request.client.host if request.client else "unknown"
