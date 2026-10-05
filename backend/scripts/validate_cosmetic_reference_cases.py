"""고정된 실제 카탈로그 사례 검수. 원본 읽기 전용, PostgreSQL 접속 없음.

기대 결과는 규칙 동작에 대한 검수 기준이며 임상 효능의 정답이 아니다.
다른 원본 버전은 기준을 재검토해야 한다. 이 스크립트의 중단이 API 중단을 뜻하지 않는다.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.cosmetic import CosmeticPreviewRequest
from app.services.cosmetic_observation_import import read_snapshot
from app.services.cosmetic_recommendation import recommend
from app.services.cosmetic_rule_types import load_seed_bundle
from app.services.cosmetic_rules import ENGINE_VERSION
from scripts.audit_cosmetic_quality import scenarios
from scripts.preview_cosmetics_from_sqlite import load_catalog, default_definitions

CASES_PATH = Path(__file__).resolve().parent.parent / "tests/fixtures/cosmetic_reference_cases_v1.json"


def check_case(case, products, known, bundle):
    request = scenarios()[case["scenario"]].model_dump()
    request.update(case.get("request_overrides", {}))
    product = products[case["product"]]
    result = recommend(CosmeticPreviewRequest.model_validate(request), default_definitions(),
                       [product], known, rule_bundle=bundle)
    item = result.recommendations[0] if result.recommendations else None
    actual = {
        "metrics": sorted(m.metric_code for m in item.matches) if item else [],
        "groups": item.matched_group_count if item else 0,
        "ingredients": sorted({n for m in item.matches for n in m.ingredients}) if item else [],
        "blocked_by": next((k for k, v in result.stats.model_dump().items()
                            if k not in {"total_products", "eligible_products"} and v), None),
    }
    expected = {k: sorted(case[k]) if isinstance(case[k], list) else case[k] for k in actual}
    return {"id": case["id"], "source_product_id": case["product"], "name": product.product_name,
            "reason": case["reason"], "passed": actual == expected,
            "expected": expected, "actual": actual,
            "product_efficacy_verified": False}


def validate(path):
    criteria = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    snapshot = read_snapshot(path)
    bundle = load_seed_bundle()
    if snapshot.source_file_sha256 != criteria["source_sha256"]:
        raise ValueError("원본 버전이 달라 고정 사례 기준 재검토가 필요합니다. 운영 API에는 영향 없습니다.")
    if bundle.fingerprint() != criteria["rule_fingerprint"] or ENGINE_VERSION != criteria["engine_version"]:
        raise ValueError("규칙 또는 엔진 버전이 달라 기대 결과를 재검토해야 합니다.")
    rows, known, ids = load_catalog(path)
    products = {ids[p.product_id]: p for p in rows}
    cases = criteria["cases"]
    if len({c["id"] for c in cases}) != len(cases) or any(c["product"] not in products for c in cases):
        raise ValueError("중복 사례 또는 원본 제품 누락")
    results = [check_case(c, products, known, bundle) for c in cases]
    with path.open("rb") as f:
        if hashlib.file_digest(f, "sha256").hexdigest() != criteria["source_sha256"]:
            raise ValueError("검수 도중 원본이 변경됐습니다.")
    return {"source_sha256": snapshot.source_file_sha256, "engine_version": ENGINE_VERSION,
            "rule_fingerprint": bundle.fingerprint(), "cases": len(results),
            "passed": sum(r["passed"] for r in results), "failed": sum(not r["passed"] for r in results),
            "clinical_validation": False, "database_writes": 0, "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    report = validate(parser.parse_args().source)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if report["failed"] else 0)
