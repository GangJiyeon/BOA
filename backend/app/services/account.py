"""마이페이지: 동의 상태, 선택 약관 변경, 회원 탈퇴"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    ConsentHistory,
    EmailVerification,
    FaceAnalysis,
    HairRecRun,
    SkinAnalysis,
    Terms,
    User,
)
from app.services import terms

# 분석 결과 모델 (회원·세션 FK가 없어 직접 삭제·이관), 하위 행은 각 테이블 CASCADE
RESULT_MODELS = (SkinAnalysis, HairRecRun, FaceAnalysis)


class ConsentError(Exception):
    pass


@dataclass(frozen=True)
class ConsentStatus:
    type: str
    required: bool
    agreed: bool
    version: str | None
    updated_at: datetime | None


def consent_statuses(db: Session, user_id: int) -> list[ConsentStatus]:
    """현재 약관 종류별로 가장 최근 동의·철회 기록 기준 상태"""
    rows = db.execute(
        select(ConsentHistory, Terms)
        .join(Terms, Terms.id == ConsentHistory.terms_id)
        .where(ConsentHistory.user_id == user_id)
        .order_by(ConsentHistory.created_at.desc(), ConsentHistory.id.desc())
    ).all()
    latest: dict[str, tuple[ConsentHistory, Terms]] = {}
    for history, t in rows:
        latest.setdefault(t.type, (history, t))

    result = []
    for current in terms.current_terms(db):
        history, t = latest.get(current.type, (None, None))
        result.append(
            ConsentStatus(
                type=current.type,
                required=current.required,
                agreed=history is not None and history.action == "AGREE",
                version=t.version if t else None,
                updated_at=history.created_at if history else None,
            )
        )
    return result


def change_consent(db: Session, user_id: int, terms_type: str, action: str) -> ConsentStatus:
    """선택 약관 동의·철회, 이미 같은 상태면 기록 추가 안 함"""
    current = terms.current_terms_of(db, terms_type)
    if current is None:
        raise ConsentError("없는 약관입니다")
    if current.required:
        raise ConsentError("필수 약관은 철회할 수 없습니다. 탈퇴를 이용해 주세요")

    status = next(s for s in consent_statuses(db, user_id) if s.type == terms_type)
    if status.agreed == (action == "AGREE"):
        return status
    # TODO(사진 저장 도입 시): PHOTO_STORAGE 철회면 저장된 얼굴 사진 삭제
    db.add(ConsentHistory(user_id=user_id, terms_id=current.id, action=action))
    db.flush()
    return next(s for s in consent_statuses(db, user_id) if s.type == terms_type)


def delete_user(db: Session, user: User) -> None:
    """회원 탈퇴, 커밋은 호출하는 쪽에서

    분석 결과 테이블엔 아직 회원 FK가 없어 직접 삭제 (점수 등 하위 행은 각 테이블 CASCADE)
    동의 이력·리프레시 토큰·비회원 세션은 users CASCADE로 삭제
    """
    db.execute(delete(EmailVerification).where(EmailVerification.email == user.email))
    for model in RESULT_MODELS:
        db.execute(delete(model).where(model.user_id == user.id))
    db.delete(user)
