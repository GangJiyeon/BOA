from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    # 쉼표로 구분: "http://localhost:5173,https://boa.vercel.app"
    cors_origins: str = "http://localhost:5173"

    aws_region: str = "ap-northeast-2"
    s3_bucket: str = ""
    # 비어 있으면 boto3가 기본 자격증명(EC2 IAM Role 등)을 사용한다
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # 비회원 IP HMAC 키, 배포 시 변경 필수
    ip_hash_secret: str = "dev-ip-hash-secret"
    # 로컬 false, 배포 true(Safari는 http에서 Secure 쿠키 막음)
    cookie_secure: bool = False
    guest_session_days: int = 7

    # JWT 서명 키, 배포 시 변경 필수 (HS256은 32바이트 이상 권장)
    jwt_secret: str = "dev-jwt-secret-change-me-in-production"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    signup_token_minutes: int = 10
    # 이메일 인증 코드
    email_code_minutes: int = 10
    email_max_attempts: int = 5
    email_resend_seconds: int = 60
    # 구글 OAuth (비우면 구글 로그인 503)
    google_client_id: str = ""
    google_client_secret: str = ""
    # 프론트가 인가 코드를 받은 redirect_uri와 같아야 함 (GIS 팝업 방식은 postmessage)
    google_redirect_uri: str = "postmessage"
    # 개발용 로그인 API(POST /api/auth/dev-login), 배포에서는 false
    dev_login: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def s3_enabled(self) -> bool:
        return bool(self.s3_bucket)


@lru_cache
def get_settings() -> Settings:
    return Settings()
