"""수집 SQLite를 읽기 전용으로 추천 엔진에 연결하는 재현 도구.

실행: python scripts/preview_cosmetics_from_sqlite.py data/beauty_catalog.db
PostgreSQL/사용자 DB에 접속하지 않으며 파일도 생성하지 않는다.
출력에는 원본 SQLite 상품 코드를 쓴다. 내부 임시 정수 ID는 PostgreSQL ID와 무관하다.
"""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.cosmetic import CosmeticPreviewRequest
from app.services.cosmetic_recommendation import MetricDefinition, ProductCandidate, recommend
from app.services.cosmetic_rules import METRICS
from app.services.cosmetic_rule_types import load_seed_bundle


def load_catalog(path: Path):
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        ingredients = defaultdict(set)
        # 기존 import_cosmetics.py와 같은 대표 성분표 연결만 사용한다.
        for row in db.execute("""
            SELECT pf.cosmetic_id, i.name
            FROM primary_formulas pf
            JOIN formula_ingredients fi ON fi.formula_id=pf.formula_id
            JOIN ingredients i ON i.id=fi.ingredient_id
        """):
            ingredients[row["cosmetic_id"]].add(row["name"])
        rows = db.execute("SELECT * FROM cosmetics ORDER BY id").fetchall()
        source_ids = {i: p["id"] for i, p in enumerate(rows, 1)}
        products = [ProductCandidate(
            i, p["name"], p["brand"], p["category"], p["normalization_status"],
            p["ingredients_raw"], frozenset(ingredients[p["id"]]), p["image_url"], p["source_url"],
        ) for i, p in enumerate(rows, 1)]
        known = {r[0] for r in db.execute("SELECT name FROM ingredients")}
        return products, known, source_ids
    finally:
        db.close()


def default_definitions():
    """seed_skin_metrics.py의 초기 구간을 재현. 운영 DB의 실제 구간 조회를 대체하지 않음."""
    return [MetricDefinition(code, name, direction, tuple(zip(
        ["개선 필요", "보통", "양호"] if direction else ["양호", "보통", "개선 필요"],
        [0, 34, 67], [33, 66, 100],
    ))) for code, (name, direction) in METRICS.items()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    products, known, source_ids = load_catalog(args.source)
    scenarios = {
        "five_concerns": dict(moisture=25, redness=75, brightness=30, trouble=75, uniformity=30),
        "moisture_only": dict(moisture=25, redness=10, brightness=80, trouble=10, uniformity=80),
        "no_moisture": dict(moisture=None, redness=75, brightness=30, trouble=75, uniformity=30),
        "all_good": dict(moisture=80, redness=10, brightness=80, trouble=10, uniformity=80),
    }
    report = {"source": "SQLite snapshot (read-only)", "thresholds": "default development seed", "scenarios": {}}
    for name, scores in scenarios.items():
        result = recommend(CosmeticPreviewRequest(scores=scores), default_definitions(), products, known, rule_bundle=load_seed_bundle())
        report["scenarios"][name] = {
            "rule_version": result.rule_version, "scorable_target_count": result.scorable_target_count,
            "deferred_metrics": result.deferred_metrics, "target_count": result.target_count, "stats": result.stats.model_dump(),
            "top5": [{"source_product_id": source_ids[p.product_id], "name": p.product_name, "match_count": p.match_count} for p in result.recommendations],
            "empty_reason": result.empty_reason,
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
