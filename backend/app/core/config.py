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

    # 비회원 IP는 원문 대신 이 키로 만든 HMAC만 저장한다. 배포 시 반드시 바꿀 것
    ip_hash_secret: str = "dev-ip-hash-secret"
    # 로컬 false, 배포 true(Safari는 http에서 Secure 쿠키 막음)
    cookie_secure: bool = False
    guest_session_days: int = 7

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def s3_enabled(self) -> bool:
        return bool(self.s3_bucket)


@lru_cache
def get_settings() -> Settings:
    return Settings()
