"""원본 SQLite 표기 해석 감사. PostgreSQL 미접속, 파일/DB 쓰기 없음."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.cosmetic_amounts import PARSER_VERSION, parse_amount
from app.services.cosmetic_observation_import import read_snapshot


def audit(path: Path):
    source = read_snapshot(path)
    names = {i["id"]: i["name"] for i in source.ingredients}
    statuses, units, issues = Counter(), Counter(), Counter()
    examples = []
    for row in source.observations:
        result = parse_amount(row["amount_text"])
        statuses[result.status] += 1
        if result.status == "single":
            units[result.declarations[0].unit] += 1
        if result.issue:
            issues[result.issue] += 1
        if result.issue or result.status == "dual":
            examples.append({"source_product_id": row["source_product_id"],
                             "source_formula_id": row["source_formula_id"],
                             "source_position": row["source_position"],
                             "ingredient": names[row["source_ingredient_id"]],
                             "raw_token": row["raw_token"], **result.to_dict()})
    return {"parser_version": PARSER_VERSION, "source_file_sha256": source.source_file_sha256,
            "scope": "source SQLite only; no PostgreSQL connection or writes",
            "observations": len(source.observations), "statuses": dict(sorted(statuses.items())),
            "single_units": dict(sorted(units.items())), "issues": dict(sorted(issues.items())),
            "special_cases": examples, "recommendation_rules_changed": False,
            "warning": "conditional_percent is arithmetic only: basis and finished-product concentration remain unverified"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    print(json.dumps(audit(parser.parse_args().source), ensure_ascii=False, indent=2))
