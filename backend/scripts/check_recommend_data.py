"""화장품 추천에 필요한 DB 데이터가 있는지 점검한다 (조회만, 쓰기 없음).

사용법 (backend 폴더에서)
    docker compose exec api python scripts/check_recommend_data.py
"""

import sys
from pathlib import Path

# backend 폴더를 import 경로에 추가 (다른 scripts와 같은 방식)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.services.cosmetic_rule_types import DEFAULT_RULE_VERSION  # noqa: E402

# (테이블, 설명, 채우는 방법)
CHECKS = [
    ("skin_metrics", "피부 지표 (5개 필요)", "scripts/seed_skin_metrics.py"),
    ("skin_metric_categories", "지표별 판정 구간 (15개 필요)", "scripts/seed_skin_metrics.py"),
    ("products", "화장품 제품", "scripts/import_cosmetics.py (팀 수집 DB 필요)"),
    ("ingredients", "성분", "scripts/import_cosmetics.py (팀 수집 DB 필요)"),
    ("product_ingredients", "제품-성분 연결", "scripts/import_cosmetics.py (팀 수집 DB 필요)"),
    ("cosmetic_rule_sets", "추천 규칙 버전", "scripts/seed_cosmetic_rules.py --apply"),
    ("cosmetic_rule_evidence", "규칙 근거", "scripts/seed_cosmetic_rules.py --apply"),
    ("category_ingredients", "판정 구간-성분 규칙", "scripts/seed_cosmetic_rules.py --apply"),
]


def main() -> None:
    with SessionLocal() as db:
        # DB 접속 정보 (비밀번호 제외)
        print(f"DB: {db.get_bind().url.render_as_string(hide_password=True)}\n")
        tables = set(inspect(db.get_bind()).get_table_names())

        # alembic 버전 테이블이 있으면 현재 버전 표시
        if "alembic_version" in tables:
            version = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
            print(f"alembic 버전: {version}")
        else:
            print("alembic 버전: (alembic_version 테이블 없음 → 팀 스키마 SQL로 만든 DB)")
        print(f"사용할 규칙 버전: {DEFAULT_RULE_VERSION}\n")

        # 테이블별 존재 여부와 행 개수
        for table, desc, fix in CHECKS:
            if table not in tables:
                print(f"❌ {table:<24} 테이블 없음      ({desc}) → 스키마/마이그레이션 필요")
                continue
            count = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            mark = "✅" if count else "⚠️"
            hint = "" if count else f" → {fix}"
            print(f"{mark} {table:<24} {count:>6}행       ({desc}){hint}")

        # 기본 규칙 버전이 실제로 들어 있는지
        if "cosmetic_rule_sets" in tables:
            found = db.execute(
                text("SELECT COUNT(*) FROM cosmetic_rule_sets WHERE version = :v"),
                {"v": DEFAULT_RULE_VERSION},
            ).scalar()
            print(f"\n기본 규칙 버전({DEFAULT_RULE_VERSION}) 존재: {'예' if found else '아니오'}")


if __name__ == "__main__":
    main()
