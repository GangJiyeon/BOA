"""토큰·IP 해시 유틸.

QR·키오스크·리프레시 토큰은 충분히 긴 무작위 값이라 SHA-256만으로 안전하고,
해시값을 그대로 UNIQUE 인덱스로 조회할 수 있다.
"""

import hashlib
import hmac
import secrets

from fastapi import Request

from app.core.config import get_settings


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_ip(ip: str) -> str:
    """IP 원문을 저장하지 않기 위한 HMAC. 같은 IP끼리 비교만 할 수 있다."""
    key = get_settings().ip_hash_secret.encode()
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()


def client_ip(request: Request) -> str:
    # TODO(배포): 프록시 뒤에서는 uvicorn --proxy-headers로 X-Forwarded-For를 반영한다
    return request.client.host if request.client else "unknown"
