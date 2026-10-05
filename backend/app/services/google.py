"""구글 OAuth: 인가 코드 교환, ID 토큰 검증"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import get_settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ["https://accounts.google.com", "accounts.google.com"]

# 구글 공개키 캐시 (키 교체 시 자동 갱신)
_jwks = jwt.PyJWKClient(CERTS_URL)


class GoogleNotConfigured(Exception):
    pass


class GoogleAuthError(Exception):
    pass


@dataclass(frozen=True)
class GoogleUser:
    sub: str
    email: str


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.google_client_id and settings.google_client_secret)


def authorization_url(redirect_uri: str) -> str:
    """구글 로그인 화면 주소 (개발용 테스트 흐름에서만 사용)"""
    params = {
        "client_id": get_settings().google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email",
        "prompt": "select_account",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str, redirect_uri: str) -> GoogleUser:
    """인가 코드 → ID 토큰 → 검증된 구글 사용자"""
    if not is_configured():
        raise GoogleNotConfigured
    settings = get_settings()
    try:
        res = httpx.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
    except httpx.HTTPError as e:
        raise GoogleAuthError("구글 서버에 연결할 수 없습니다") from e
    if res.status_code != 200 or "id_token" not in res.json():
        # 만료·재사용된 코드, redirect_uri 불일치 등
        raise GoogleAuthError("구글 인증에 실패했습니다. 다시 시도해 주세요")
    return verify_id_token(res.json()["id_token"])


def verify_id_token(id_token: str) -> GoogleUser:
    """구글 공개키 서명 + 발급자·대상 앱·만료·이메일 인증 여부 검증"""
    try:
        key = _jwks.get_signing_key_from_jwt(id_token).key
        payload = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=get_settings().google_client_id,
            issuer=ISSUERS,
        )
    except (jwt.PyJWKClientError, jwt.InvalidTokenError) as e:
        raise GoogleAuthError("구글 인증 정보가 올바르지 않습니다") from e
    if not payload.get("email") or payload.get("email_verified") is not True:
        raise GoogleAuthError("이메일이 인증되지 않은 구글 계정입니다")
    return GoogleUser(sub=payload["sub"], email=payload["email"])
