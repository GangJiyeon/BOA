"""원본 DB 읽기 전용 순위 비교. 기본 API/규칙 변경, PostgreSQL 접속 없음."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.cosmetic_ranking import rank_candidates, POLICY_VERSION
from app.services.cosmetic_rule_types import load_seed_bundle
from app.services.cosmetic_recommendation import recommend
from app.services.cosmetic_observation_import import read_snapshot
from scripts.audit_cosmetic_quality import scenarios
from scripts.preview_cosmetics_from_sqlite import default_definitions, load_catalog


def compare(path):
    snapshot = read_snapshot(path)
    products, known, ids = load_catalog(path)
    bundle = load_seed_bundle()
    definitions = default_definitions()
    results = {}
    for name, request in scenarios().items():
        original = recommend(request, definitions, products, known, rule_bundle=bundle)
        # 먼저 전체 필터 통과 후보를 복원한다. 기존 Top 5만 재정렬하면 안 된다.
        candidates = []
        for i in range(0, len(products), 5):
            candidates.extend(recommend(request, definitions, products[i:i+5], known,
                                        rule_bundle=bundle).recommendations)
        scorable = frozenset(a.code for a in original.assessments
                             if a.needs_improvement and a.code not in original.deferred_metrics)
        baseline = rank_candidates(candidates, "metric_count")
        assert len(baseline) == original.stats.eligible_products
        assert [r.product.product_id for r in baseline[:5]] == [p.product_id for p in original.recommendations]
        base_ranks = {r.product.product_id: r.rank for r in baseline}
        base_top = {r.product.product_id for r in baseline[:5]}
        variants = {"metric_count": baseline, "concern_groups": rank_candidates(candidates, "concern_groups")}
        for priority in sorted(scorable):
            variants["priority_"+priority] = rank_candidates(candidates, "explicit_priority",
                                                           priority=priority, scorable_metrics=scorable)
        report = {}
        for label, ranked in variants.items():
            assert {r.product.product_id for r in ranked} == set(base_ranks)
            changes = sorted((r for r in ranked if r.rank != base_ranks[r.product.product_id]),
                             key=lambda r: (-abs(r.rank-base_ranks[r.product.product_id]), r.product.product_id))
            def item(r):
                p = r.product
                return {"source_product_id": ids[p.product_id], "name": p.product_name,
                        "rank": r.rank, "baseline_rank": base_ranks[p.product_id],
                        "match_count": p.match_count, "group_count": r.group_count,
                        "matched_metrics": [m.metric_code for m in p.matches],
                        "priority_matched": r.priority_matched, "tie_count": r.tie_count,
                        "bundle_suspected": p.bundle_suspected}
            report[label] = {"candidate_count": len(ranked), "changed_ranks": len(changes),
                             "top5_overlap": len(base_top & {r.product.product_id for r in ranked[:5]}),
                             "top5": [item(r) for r in ranked[:5]],
                             "largest_rank_changes": [item(r) for r in changes[:5]]}
        results[name] = {"scores": request.scores.model_dump(), "filters": request.model_dump(exclude={"scores"}),
                         "priorities_are_test_assumptions_not_user_preferences": True,
                         "stats": original.stats.model_dump(), "variants": report}
    with path.open("rb") as f:
        if hashlib.file_digest(f, "sha256").hexdigest() != snapshot.source_file_sha256:
            raise ValueError("분석 중 원본 변경 감지")
    return {"policy_version": POLICY_VERSION, "source_sha256": snapshot.source_file_sha256,
            "rule_fingerprint": bundle.fingerprint(), "default_api_changed": False,
            "scope": "source SQLite and development thresholds; not live PostgreSQL ranking",
            "id_tiebreak": "temporary IDs ordered by source product code",
            "scenarios": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    print(json.dumps(compare(parser.parse_args().source), ensure_ascii=False, indent=2))
