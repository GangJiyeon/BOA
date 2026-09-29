"""피부 지표와 판정 구간 시드.

실행: (backend 폴더에서) python scripts/seed_skin_metrics.py
같은 키로 이미 존재하면 건너뛰므로 여러 번 실행해도 안전하다.

지표 5개와 지표별 구간 3개씩(총 15개)은 점수 라벨링이 동작하기 위한
기준 데이터이므로 로컬·운영 양쪽에 모두 들어가야 한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import SkinMetric, SkinMetricCategory

# (코드, 표시명, 높을수록 양호인지)
METRICS = [
    ("moisture", "수분", True),
    ("redness", "홍조", False),
    ("brightness", "밝기", True),
    ("trouble", "트러블", False),
    ("uniformity", "균일도", True),
]

# 초기값은 0~100 균등 3분할. 데이터가 쌓이면 이 값만 UPDATE해서 조정한다.
BOUNDS = [(0, 33), (34, 66), (67, 100)]
# 점수가 높을수록 양호한 지표의 구간 이름 (낮은 구간부터)
NAMES_ASC = ["개선 필요", "보통", "양호"]
# 점수가 낮을수록 양호한 지표(홍조·트러블)는 이름이 반대로 붙는다
NAMES_DESC = ["양호", "보통", "개선 필요"]


def seed_metrics(db: Session) -> None:
    for code, name, higher_is_better in METRICS:
        metric = db.scalar(select(SkinMetric).where(SkinMetric.code == code))
        if not metric:
            metric = SkinMetric(code=code, name=name, higher_is_better=higher_is_better)
            db.add(metric)
            db.flush()

        names = NAMES_ASC if higher_is_better else NAMES_DESC
        for (min_score, max_score), category_name in zip(BOUNDS, names):
            exists = db.scalar(
                select(SkinMetricCategory).where(
                    SkinMetricCategory.metric_id == metric.id,
                    SkinMetricCategory.min_score == min_score,
                )
            )
            if not exists:
                db.add(
                    SkinMetricCategory(
                        metric_id=metric.id,
                        name=category_name,
                        min_score=min_score,
                        max_score=max_score,
                    )
                )
    db.flush()


def main() -> None:
    with SessionLocal() as db:
        seed_metrics(db)
        db.commit()
        metric_count = len(db.scalars(select(SkinMetric)).all())
        category_count = len(db.scalars(select(SkinMetricCategory)).all())
        print(f"지표 {metric_count}개, 판정 구간 {category_count}개 준비 완료")


if __name__ == "__main__":
    main()
