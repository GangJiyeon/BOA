"""기본은 조회만 하는 사전 검사. --apply 지정 시 규칙 3개 테이블에 새 버전 INSERT."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db.session import SessionLocal
from app.services.cosmetic_rule_types import load_seed_bundle
from app.services.cosmetic_rule_repository import seed_rule_bundle
from app.services.cosmetic_recommendation import RecommendationConfigurationError
from sqlalchemy.exc import SQLAlchemyError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="검사 성공 후 규칙 데이터 저장")
    args = parser.parse_args()
    try:
        with SessionLocal.begin() as db:
            report = seed_rule_bundle(db, load_seed_bundle(), apply=args.apply)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (RecommendationConfigurationError, SQLAlchemyError) as exc:
        # SQLAlchemy 원문에는 접속/SQL 파라미터가 포함될 수 있어 노출하지 않는다.
        message = str(exc) if isinstance(exc, RecommendationConfigurationError) else "규칙 DB 접근 실패. alembic upgrade head 적용 여부와 DB 연결을 확인하세요."
        print(message, file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
