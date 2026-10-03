"""가입: 약관 검증, 회원·동의 이력 생성"""

from sqlalchemy.orm import Session

from app.models import ConsentHistory, Terms, User
from app.services import terms


class SignupError(Exception):
    pass


def validate_terms(db: Session, agreed_ids: list[int]) -> list[Terms]:
    """동의한 약관 목록 반환, 현재 약관이 아닌 id나 필수 누락이면 SignupError"""
    current = {t.id: t for t in terms.current_terms(db)}
    agreed = set(agreed_ids)
    if agreed - current.keys():
        raise SignupError("약관이 갱신되었습니다. 다시 확인해 주세요")
    missing = [t.type for t in current.values() if t.required and t.id not in agreed]
    if missing:
        raise SignupError(f"필수 약관에 동의해 주세요: {', '.join(sorted(missing))}")
    return [current[i] for i in sorted(agreed)]


def create_user(
    db: Session,
    *,
    email: str,
    language: str,
    nationality: str,
    resides_in_korea: bool,
    agreed_terms: list[Terms],
    google_sub: str | None = None,
) -> User:
    """회원 생성 + 동의 이력(AGREE), 이메일·구글 계정 중복이면 flush에서 IntegrityError"""
    user = User(
        email=email,
        google_sub=google_sub,
        language=language,
        nationality=nationality,
        resides_in_korea=resides_in_korea,
    )
    db.add(user)
    db.flush()
    db.add_all(ConsentHistory(user_id=user.id, terms_id=t.id, action="AGREE") for t in agreed_terms)
    return user
