"""
hair_styles_80.csv 를 읽어 hair_style_catalog 테이블에 upsert한다.


CSV의 face_fit 컬럼에 이미 {"계란형": 0.95, "둥근형": 0.40, ...} 형태의
JSON 문자열로 들어있으므로 그대로 파싱해서 저장한다.


실행 (backend/ 에서, 컨테이너 안):
    docker compose exec -e PYTHONPATH=/app api python scripts/import_hair_styles.py hair_styles_80.csv
"""

import csv
import json
import sys

from app.db.session import SessionLocal
from app.models.hair import HairStyleCatalog, Sex

REQUIRED_COLUMNS = {
    "style_id", "name", "sex", "length", "texture",
    "face_fit", "asset_id", "image", "image_credit", "guide",
}


def main(csv_path: str) -> None:
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("CSV에 데이터가 없습니다.")
        return

    missing = REQUIRED_COLUMNS - set(rows[0].keys())
    if missing:
        print(f"CSV에 다음 컬럼이 없습니다: {missing}")
        sys.exit(1)

    db = SessionLocal()
    try:
        for row in rows:
            try:
                sex = Sex(row["sex"])
            except ValueError:
                print(f"[스킵] {row['style_id']}: 알 수 없는 sex 값 '{row['sex']}'")
                continue

            face_fit = json.loads(row["face_fit"])

            existing = db.get(HairStyleCatalog, row["style_id"])
            if existing:
                existing.name = row["name"]
                existing.sex = sex
                existing.length = row["length"]
                existing.texture = row["texture"]
                existing.face_fit = face_fit
                existing.asset_id = row.get("asset_id") or None
                existing.image = row.get("image") or None
                existing.image_credit = row.get("image_credit") or None
                existing.guide = row.get("guide") or None
                action = "수정"
            else:
                db.add(HairStyleCatalog(
                    style_id=row["style_id"],
                    name=row["name"],
                    sex=sex,
                    length=row["length"],
                    texture=row["texture"],
                    face_fit=face_fit,
                    asset_id=row.get("asset_id") or None,
                    image=row.get("image") or None,
                    image_credit=row.get("image_credit") or None,
                    guide=row.get("guide") or None,
                ))
                action = "신규"

            print(f"[{action}] {row['style_id']} ({row['sex']}) {row['name']}")

        db.commit()
        print(f"\n완료: {len(rows)}개 스타일 반영됨")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python scripts/import_hair_styles.py <csv경로>")
        sys.exit(1)
    main(sys.argv[1])