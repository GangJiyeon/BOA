"""약관 v1 시드

실행: cd backend >> docker compose exec api python scripts/seed_terms.py
약관 본문은 프론트 locales, DB에는 종류·버전·필수 여부
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Terms

# (종류, 필수 여부)
TERMS = [
    ("SERVICE", True),          # 서비스 이용약관
    ("PRIVACY", True),          # 개인정보 수집·이용
    ("AGE_14", True),           # 만 14세 이상 확인
    ("FACE_IMAGE", True),       # 얼굴 이미지 처리 (가입 필수 + 비회원 촬영 전 동의)
    ("PHOTO_STORAGE", False),   # 사진 보관
    ("MARKETING", False),       # 마케팅 수신
]
VERSION = "v1"
# 팀원마다 같은 값이 들어가도록 고정 날짜
EFFECTIVE_AT = datetime(2026, 9, 1, tzinfo=UTC)


def seed_terms(db: Session) -> None:
    for terms_type, required in TERMS:
        exists = db.scalar(
            select(Terms).where(Terms.type == terms_type, Terms.version == VERSION)
        )
        if not exists:
            db.add(
                Terms(type=terms_type, version=VERSION, required=required, effective_at=EFFECTIVE_AT)
            )
    db.flush()


def main() -> None:
    with SessionLocal() as db:
        seed_terms(db)
        db.commit()
        count = len(db.scalars(select(Terms)).all())
        print(f"약관 {count}개 준비 완료")


if __name__ == "__main__":
    main()
