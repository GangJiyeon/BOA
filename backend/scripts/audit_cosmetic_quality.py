"""실제 수집 스냅샷에 대한 재현 가능한 추천 품질 진단 (임상 검증 아님).

실행: python scripts/audit_cosmetic_quality.py SOURCE.db
원본은 읽기 전용. PostgreSQL 연결/파일 저장/시드 실행 없음. JSON은 stdout으로 출력.
판정 구간은 임시 기본값, 규칙은 배포용 시드이므로 운영 DB 검수와 구분한다.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.cosmetic import CosmeticPreviewRequest
from app.services.cosmetic_recommendation import recommend
from app.services.cosmetic_rule_types import load_seed_bundle
from app.services.cosmetic_rules import ENGINE_VERSION, METRICS, normalize_name
from scripts.preview_cosmetics_from_sqlite import default_definitions, load_catalog


GOOD = dict(moisture=80, redness=10, brightness=80, trouble=10, uniformity=80)
CONCERNS = dict(moisture=25, redness=75, brightness=30, trouble=75, uniformity=30)


def scenarios():
    cases = {"all_good": {"scores": GOOD}}
    for metric in METRICS:
        cases[f"{metric}_only"] = {"scores": GOOD | {metric: CONCERNS[metric]}}
    cases.update({
        "five_concerns": {"scores": CONCERNS},
        "redness_filter_off": {"scores": CONCERNS, "avoid_redness_triggers": False},
        "moisture_redness": {"scores": GOOD | {"moisture": 25, "redness": 75}},
        "brightness_uniformity": {"scores": GOOD | {"brightness": 30, "uniformity": 30}},
        "missing_moisture": {"scores": CONCERNS | {"moisture": None}},
        "user_excludes_niacinamide": {"scores": CONCERNS, "excluded_ingredients": ["나이아신아마이드"]},
        "concern_boundary": {"scores": {m: 33 if d else 67 for m, (_, d) in METRICS.items()}},
        "normal_boundary": {"scores": {m: 34 if d else 66 for m, (_, d) in METRICS.items()}},
        "extreme_concerns": {"scores": {m: 0 if d else 100 for m, (_, d) in METRICS.items()}},
    })
    for category in ("moisturizer", "serum", "toner"):
        cases[f"category_{category}"] = {"scores": CONCERNS, "category": category}
    return {name: CosmeticPreviewRequest.model_validate(body | {"score_semantics": "development_assumption"}) for name, body in cases.items()}


def audit_scenario(request, products, known, source_ids, bundle):
    definitions = default_definitions()
    result = recommend(request, definitions, products, known, rule_bundle=bundle)
    # 5개씩 처리하면 상위 5개 제한으로 후보가 사라지지 않는다. 필터는 실제 엔진을 재사용한다.
    eligible = []
    for start in range(0, len(products), 5):
        eligible.extend(recommend(request, definitions, products[start:start + 5], known,
                                  rule_bundle=bundle).recommendations)
    eligible.sort(key=lambda p: (-p.match_count, p.bundle_suspected, p.product_id))
    if len(eligible) != result.stats.eligible_products:
        raise AssertionError("후보 집계와 실제 엔진의 결과가 다릅니다.")
    if [p.product_id for p in eligible[:5]] != [p.product_id for p in result.recommendations]:
        raise AssertionError("전체 후보 재구성과 상위 5개 결과가 다릅니다.")
    histogram = Counter(p.match_count for p in eligible)
    ties = Counter((p.match_count, p.bundle_suspected) for p in eligible)
    shared_evidence_products = 0
    for product in eligible:
        evidence_metrics = defaultdict(set)
        for match in product.matches:
            for url in match.evidence_urls:
                evidence_metrics[url].add(match.metric_code)
        shared_evidence_products += any(len(metrics) > 1 for metrics in evidence_metrics.values())
    return {
        "request": request.model_dump(),
        "target_count": result.target_count,
        "scorable_target_count": result.scorable_target_count,
        "deferred_metrics": result.deferred_metrics,
        "missing_metrics": result.missing_metrics,
        "stats": result.stats.model_dump(),
        "score_histogram": dict(sorted(histogram.items())),
        "ranking_groups": [{"match_count": count, "bundle_suspected": bundle_flag, "products": size}
                           for (count, bundle_flag), size in sorted(ties.items(), key=lambda x: (-x[0][0], x[0][1]))],
        "shared_evidence_multi_metric_products": shared_evidence_products,
        "top5": [{"source_product_id": source_ids[p.product_id], "name": p.product_name,
                  "match_count": p.match_count, "ranking_tie_count": ties[(p.match_count, p.bundle_suspected)],
                  "matched_metrics": [m.metric_code for m in p.matches],
                  "matched_ingredients": sorted({n for m in p.matches for n in m.ingredients})}
                 for p in result.recommendations],
        "empty_reason": result.empty_reason,
    }


def audit_rules(products, known, bundle):
    # exact-name matching과 동일한 정규화. 제품별 한 번만 집계.
    counts = Counter(n for p in products for n in {normalize_name(n) for n in p.ingredients})
    rules_by_name = defaultdict(list)
    for rule in bundle.rules:
        rules_by_name[normalize_name(rule.ingredient)].append(rule)
    rows = []
    for normalized, rules in sorted(rules_by_name.items()):
        rows.append({"ingredient": rules[0].ingredient, "linked_products_before_filters": counts[normalized],
                     "rules": [{"metric": r.metric, "effect": r.effect, "status": r.status,
                                "evidence_code": r.evidence_code, "condition": r.condition} for r in rules]})
    names = {normalize_name(n): n for n in sorted(known)}
    return {
        "known_ingredient_count": len(known), "rule_ingredient_count": len(rules_by_name),
        "active_match_ingredient_count": len({normalize_name(r.ingredient) for r in bundle.rules
                                              if r.effect == "match" and r.status == "active"}),
        "ingredients": rows,
        "unreviewed_frequent_ingredients": [
            {"ingredient": names[n], "linked_products_before_filters": count}
            for n, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            if n not in rules_by_name and n in names
        ][:20],
        "warning": "빈도는 효능·안전성·규칙 추가의 근거가 아니다. 미등록 성분은 미검토다.",
    }


def build_report(path):
    products, known, source_ids = load_catalog(path)
    bundle = load_seed_bundle()
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {
        "scope": "첨부 SQLite 읽기 전용; PostgreSQL 미접속; 임상 적합도 정답 데이터 없음",
        "source_sha256": digest, "engine_version": ENGINE_VERSION,
        "rule_version": bundle.version, "rule_fingerprint": bundle.fingerprint(),
        "thresholds": [{"metric": d.code, "higher_is_better": d.higher_is_better,
                        "categories": d.categories} for d in default_definitions()],
        "rules": audit_rules(products, known, bundle),
        "scenarios": {name: audit_scenario(request, products, known, source_ids, bundle)
                      for name, request in scenarios().items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    print(json.dumps(build_report(args.source), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
