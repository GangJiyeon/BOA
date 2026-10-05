"""함량/성분 원문 보존. 기본은 DB 조회만 하는 dry-run, --apply 때 새 관측 이력만 INSERT.

마이그레이션 전에도 dry-run 가능. 기존 제품/성분/추천 규칙을 수정하지 않는다.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.exc import SQLAlchemyError
from app.services.cosmetic_observation_import import ObservationImportError, import_observations, read_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=Path("data/beauty_catalog.db"))
    parser.add_argument("--apply", action="store_true", help="사전 검사 후 새 관측 이력만 저장")
    args = parser.parse_args()
    try:
        source = read_snapshot(args.source)
        from app.db.session import SessionLocal
        with SessionLocal.begin() as db:
            if not args.apply and db.bind.dialect.name == "postgresql":
                from sqlalchemy import text
                db.execute(text("SET TRANSACTION READ ONLY"))
            report = import_observations(db, source, apply=args.apply)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (ObservationImportError, SQLAlchemyError, OSError) as exc:
        # DB 연결 문자열/SQL 인자 원문을 출력하지 않는다.
        print(str(exc) if isinstance(exc, ObservationImportError)
              else "원본 파일 또는 DB 접근 실패. 파일 권한·DB 연결·마이그레이션 상태를 확인하세요.", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
