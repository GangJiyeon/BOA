"""계정 모듈 요청·응답 스키마"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import ActorKind
from app.schemas.skin import AnalysisRead


class TermsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    version: str
    required: bool
    effective_at: datetime


class GuestSessionCreate(BaseModel):
    """촬영 전 동의: 얼굴 이미지 약관 + 만 14세 이상 확인"""

    face_terms_id: int = Field(description="GET /api/terms/current의 FACE_IMAGE id")
    age_confirmed: Literal[True] = Field(description="만 14세 이상 확인 (true만 허용)")


class GuestSessionRead(BaseModel):
    # DB에는 해시만 저장, 원문은 이 응답에서만 제공
    qr_token: str
    expires_at: datetime


class ActorRead(BaseModel):
    kind: ActorKind


class DevLoginRequest(BaseModel):
    """개발용 로그인, 회원 없으면 생성 후 로그인"""

    email: str = Field(default="admin0614@test.com", description="소문자로 저장")


class DevLoginRead(BaseModel):
    user_id: int
    email: str


# 이메일 형식만 간단히 확인 (실제 존재 여부는 코드 수신으로 확인)
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class EmailSendRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=255)


class EmailSendRead(BaseModel):
    resend_seconds: int = Field(description="재발송 버튼 비활성화 시간")
    dev_code: str | None = Field(default=None, description="DEV_LOGIN=true일 때만 포함")


class EmailVerifyRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=255)
    code: str = Field(pattern=r"^\d{6}$")


class LoginResultRead(BaseModel):
    """이메일·구글 로그인 공통: 기존 회원이면 로그인(쿠키 발급), 처음이면 가입 토큰 반환"""

    signup_required: bool
    signup_token: str | None = Field(default=None, description="가입 API에 전달, 10분 유효")
    language: str | None = Field(default=None, description="로그인 시 저장된 언어")


Language = Literal["ko", "en", "zh", "ja"]


class SignupRequest(BaseModel):
    signup_token: str = Field(description="email/verify 또는 google 응답의 signup_token")
    language: Language
    nationality: str = Field(pattern=r"^[A-Z]{2}$", description="ISO 3166-1 alpha-2 (예: KR, US)")
    resides_in_korea: bool
    agreed_terms_ids: list[int] = Field(description="체크한 약관 id, 필수 4종 포함")


class SignupRead(BaseModel):
    user_id: int
    language: str


class GoogleLoginRequest(BaseModel):
    code: str = Field(description="구글이 프론트로 돌려준 인가 코드")


class QuotaItem(BaseModel):
    limit: int | None = Field(description="하루 한도, null이면 제한 없음 (회원·키오스크)")
    used: int
    remaining: int | None


class QuotaRead(BaseModel):
    skin: QuotaItem
    hair: QuotaItem


class QrResultRead(BaseModel):
    """QR 결과, 얼굴 사진·사진 id는 포함 안 함"""

    expires_at: datetime
    skin: list[AnalysisRead]
    hair: list[dict] = Field(default_factory=list, description="헤어 파트 머지 후 추가")


class QrClaimRead(BaseModel):
    skin_count: int = Field(description="내 계정으로 옮긴 피부 분석 수")
