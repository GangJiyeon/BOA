"""수집 SQLite의 함량 원문을 읽기 전용으로 집계한다. 농도/효능 판정 도구가 아니다.

실행: python scripts/audit_cosmetic_amounts.py SOURCE.db
표준 라이브러리만 사용. PostgreSQL 접속, INSERT/UPDATE, 단위 환산, 원본 파일 저장 없음.
행 수와 제품-성분 고유 연결 수를 구별한다. 기존 import가 합치는 반복 표기도 보존해 집계한다.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3


FOCUS = (
    "글리세린", "판테놀", "하이알루로닉애씨드", "나이아신아마이드", "살리실릭애씨드",
    "우레아", "소듐하이알루로네이트", "세라마이드엔피", "알란토인",
)


def audit(path: Path):
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        product_count = conn.execute("SELECT COUNT(*) FROM cosmetics").fetchone()[0]
        rows = conn.execute("""
            SELECT pf.cosmetic_id, pf.formula_id, fi.ingredient_id, i.name,
                   fi.position, fi.raw_token, fi.amount_text
            FROM primary_formulas pf
            JOIN formula_ingredients fi ON fi.formula_id=pf.formula_id
            JOIN ingredients i ON i.id=fi.ingredient_id
            ORDER BY pf.cosmetic_id, fi.position, fi.ingredient_id
        """).fetchall()
    finally:
        conn.close()
    pairs = Counter((r["cosmetic_id"], r["ingredient_id"]) for r in rows)
    amounts = [r for r in rows if (r["amount_text"] or "").strip()]
    by_pair = defaultdict(set)
    for row in amounts:
        by_pair[(row["cosmetic_id"], row["ingredient_id"])].add(row["amount_text"].strip())
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {
        "scope": "source snapshot read-only; raw declared amounts, not verified concentrations",
        "source_sha256": digest,
        "product_count": product_count,
        "primary_formula_rows": len(rows),
        "unique_product_ingredient_pairs": len(pairs),
        "repeated_rows_beyond_unique_pairs": len(rows) - len(pairs),
        "rows_with_amount_text": len(amounts),
        "pairs_with_amount_text": len(by_pair),
        "products_with_any_amount_text": len({r["cosmetic_id"] for r in amounts}),
        "conflicting_raw_amounts": [
            {"source_product_id": p, "source_ingredient_id": i, "amount_texts": sorted(values)}
            for (p, i), values in sorted(by_pair.items()) if len(values) > 1
        ],
        "focus_ingredients": [{
            "ingredient": name,
            "linked_products": len({r["cosmetic_id"] for r in rows if r["name"] == name}),
            "products_with_amount_text": len({r["cosmetic_id"] for r in amounts if r["name"] == name}),
        } for name in FOCUS],
        "salicylic_and_urea_observations": [
            {"source_product_id": r["cosmetic_id"], "source_formula_id": r["formula_id"],
             "ingredient": r["name"], "amount_text": r["amount_text"], "raw_token": r["raw_token"]}
            for r in amounts if r["name"] in {"살리실릭애씨드", "우레아"}
        ],
        "limitations": [
            "함량 문자열의 존재는 제조사 검증 또는 완제품 내 유효 성분 농도 확정을 뜻하지 않는다.",
            "빈 값은 0%가 아니다. 단위·질량/부피 기준·복합 원료 함량을 추정하지 않는다.",
            "원본 상품/성분 ID는 PostgreSQL의 숫자 ID와 동일하지 않다.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.source), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
