"""토큰·IP 해시 유틸

액세스 토큰: JWT(user_id, 15분), DB 조회 없이 검증
QR·키오스크·리프레시 토큰: 긴 무작위 값이라 SHA-256 해시로 저장·조회
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Request

from app.core.config import get_settings

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),  # PyJWT는 sub 문자열만 허용
        "type": ACCESS_TOKEN_TYPE,  # 가입 토큰과 구분용
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """유효하면 user_id, 만료·위조면 None"""
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        return None
    return int(payload["sub"])


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
