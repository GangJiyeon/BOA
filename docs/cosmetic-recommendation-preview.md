# 화장품 추천 미리보기 v3.1

피부 점수를 입력하면 DB 제품·성분과 버전별 규칙을 SELECT해 최대 5개를 반환한다.
입력값과 추천 결과는 저장하지 않는다. 실제 분석 결과 연결은 후속 범위다.

## 규칙과 적용 방법

[성분 규칙표·근거·DB 설계·적용 명령](cosmetic-ingredient-rulebook.md)을 기준으로 한다.

[현재 품질 검수·18개 시나리오·증분 패치 적용](cosmetic-quality-audit.md).
v3.1은 판정 구간 방향 검증, 전체 후보의 동점 규모, 평가 가능 지표 표시를 보완했다.
DB 규칙 v1 및 스키마는 유지하며 이미 v1을 적용했다면 마이그레이션/시드를 다시 실행하지 않는다.

- v2에서 v3으로 변경: 하드코딩된 성분 규칙을 `category_ingredients`와 근거/버전 테이블로 이전.
- 활성 매칭 6건, 조건부 배제 8건, 보류 6건. 코드 engine_version과 DB rule_version을 별도로 반환.
- 기존 `products`, `ingredients`, 피부 구간 데이터를 재이관하거나 수정하지 않는다.
- 새 테이블용 마이그레이션과 시드를 설치해야 API가 작동한다. 미설치/규칙 손상 시 503으로 명시하며 파일 규칙으로 대체하지 않는다.
- 기존 헤어 라우터 등록 순서 수정은 유지한다.

## API 계약

`POST /api/cosmetics/recommendations/preview`

```json
{
  "scores": {"moisture": 25, "redness": 75, "brightness": 30, "trouble": 75, "uniformity": 30},
  "category": null,
  "avoid_redness_triggers": true,
  "excluded_ingredients": []
}
```

점수는 0~100 정수이며 수분만 null/생략 가능하다. category는 null/moisturizer/serum/toner.
직접 제외 성분은 DB 성분명과 정확히 매칭한다(Unicode·공백·대소문자만 정규화).
잘못된 입력이나 알 수 없는 제외 성분은 422다.

응답은 판정, 개선 대상 개수, 가점 가능 개수, 보류 지표, 적용 제외 목록·근거,
추천 제품·이미지·제품 URL·성분별 사유·근거·적용 한계·규칙 코드, 단계별 통계를 포함한다.

순서는 종류 → 전성분 정규화 확인 → 사용 방식 → 배제 → 지표별 매칭 → 정렬이다.
같은 지표에 여러 성분이 있어도 최대 1점. 동점은 기획/세트 의심 후순위 → 제품 ID 순이다.
제품 ID는 품질 순위가 아니다. 서로 다른 ID의 용량별 상품 중복 처리는 아직 없다.

## 실행 및 검증

```sh
# backend. 테스트는 독립 메모리 SQLite 사용
python -m unittest discover -s tests -v
# 수집 스냅샷 읽기 전용 / 사용자 PostgreSQL 접속 없음
python scripts/verify_cosmetic_rule_catalog.py data/beauty_catalog.db
# frontend
pnpm build
pnpm lint
pnpm dev
```

새 DB 규칙을 추가하기 전 `seed_skin_metrics.py`는 이미 적용되어 있어야 한다.
사용자 환경에는 앞서 5개 지표·15개 구간이 준비되었다는 실행 로그가 있다.
인증, 추천 이력, 실측 보정, 전문가 효능 검증, 공개 운영 최적화는 현재 범위 밖이다.
