"""Replay 15 metric states and combined concerns through the recommendation API.

Use --api http://localhost:8000 with the local database, or --sqlite PATH for
an offline read-only catalog replay using the project's default thresholds.
"""
import argparse
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.cosmetic import CosmeticPreviewRequest
from app.services.cosmetic_rule_types import DEFAULT_RULE_VERSION


GOOD = dict(moisture=80, redness=10, brightness=80, trouble=10, uniformity=80)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--api", help="Local API base URL")
    source.add_argument("--sqlite", type=Path, help="Read-only catalog snapshot")
    args = parser.parse_args()
    if args.sqlite:
        from scripts.preview_cosmetics_from_sqlite import default_definitions, load_catalog
        from app.services.cosmetic_recommendation import recommend
        from app.services.cosmetic_rule_types import load_seed_bundle
        products, known, _ = load_catalog(args.sqlite)
        definitions, bundle = default_definitions(), load_seed_bundle()

    cases = []
    for metric in GOOD:
        values = (80, 50, 10) if metric in ("redness", "trouble") else (20, 50, 80)
        for value in values:
            cases.append((f"{metric}={value}", GOOD | {metric: value}))
    cases.append(("combined", dict(moisture=20, redness=80, brightness=20, trouble=80, uniformity=20)))
    print(f"Expected rules: {DEFAULT_RULE_VERSION}; ranking: care_context", flush=True)
    for name, scores in cases:
        body = CosmeticPreviewRequest(scores=scores, ranking_policy="care_context")
        if args.api:
            request = Request(
                args.api.rstrip("/") + "/api/cosmetics/recommendations/preview",
                data=body.model_dump_json().encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urlopen(request, timeout=60) as response:
                result = json.load(response)
        else:
            result = recommend(body, definitions, products, known, rule_bundle=bundle).model_dump(mode="json")
        if result["rule_version"] != DEFAULT_RULE_VERSION:
            raise RuntimeError(f"{name}: expected {DEFAULT_RULE_VERSION}, got {result['rule_version']}")
        if result["deferred_metrics"] or result["target_count"] != result["scorable_target_count"]:
            raise RuntimeError(f"{name}: some concern metrics did not reach ingredient matching")
        targets = {a["code"] for a in result["assessments"] if a["needs_improvement"]}
        if any(m["metric_code"] not in targets for p in result["recommendations"] for m in p["matches"]):
            raise RuntimeError(f"{name}: a normal or good metric received an improvement match")
        print(json.dumps(dict(
            case=name, mode=result["recommendation_mode"], targets=result["target_count"],
            scorable=result["scorable_target_count"], candidates=result["stats"]["eligible_products"],
            top5=[p["product_id"] for p in result["recommendations"]],
            first_group_size=result["tie_groups"][0]["total"] if result["tie_groups"] else 0,
        ), ensure_ascii=False), flush=True)
        if name in ("brightness=20", "trouble=80", "combined"):
            for item in result["recommendations"][:2]:
                print(json.dumps(dict(
                    product_id=item["product_id"], name=item["product_name"],
                    matches={m["metric_code"]: m["ingredients"] for m in item["matches"]},
                    product_name_claims=item.get("product_name_claims", {}),
                    context_cautions=item.get("context_cautions", []),
                ), ensure_ascii=False), flush=True)
    print("PASS: 16 API/engine scenarios completed. Product efficacy was not evaluated.")


if __name__ == "__main__":
    main()
