# 함량 표기 해석 v1

## 범위

원본 표기를 읽는 독립 모듈이다. 추천 API, 점수, 배제 정책, DB 스키마와
저장된 관측 기록은 변경하지 않는다. 추천 엔진에 연결하지 않는다.
1학기 프로젝트 코드는 사용하지 않았다.

`app/services/cosmetic_amounts.py`의 `parse_amount`는 문자열 또는 None만 받는다.
원문은 그대로 유지하고 결과는 메모리에서만 반환한다.

| status | 의미 |
| --- | --- |
| missing | None 또는 공백뿐인 문자열. 0을 뜻하지 않음 |
| single | 허용한 단일 숫자·단위 표기 |
| dual | 서로 다른 비율 단위 2개의 병기. 불일치하면 issue 제공 |
| unparsed | 지원하지 않거나 잘못된 표기. 임의 보정 금지 |

허용 단위는 %, ppm, ppb, mg, IU/g다. ASCII 숫자, 정상적인 천 단위 쉼표,
소수점, 단위 앞 공백, 영문 대소문자를 지원한다. 부등호·범위·지수 표기·
설명 문구는 아직 해석하지 않는다. unparsed는 원문 자체가 틀렸다는 단정이 아니다.

숫자는 Decimal로 계산하고 JSON에서는 문자열로 반환한다.
`conditional_percent`는 **동일한 비율 기준을 가정한 산술 환산값**이다.
ppm은 10,000으로, ppb는 10,000,000으로 나눈 수치다.
질량/부피 기준이나 복합 원료 여부는 판정하지 않는다.
모든 결과의 `basis`는 unknown, `concentration_verified`는 false다.
상태가 single이어도 완제품 내 유효 농도나 효과를 검증한 것이 아니다.
mg는 분모가 없고 IU/g는 별도 활성 단위이므로 %로 환산하지 않는다.

`0.75%/ 7,500ppm`는 두 값을 보존하고 같은 기준일 때의 수치 일치만 표시한다.
`1%/7,500ppm`는 dual이지만 inconsistent_dual 경고를 가진다.
`10.020.7%`는 unparsed이며 제품명 등을 근거로 고치지 않는다.
명시된 0은 보존하지만 누락에서 0을 만들어내지 않는다.

## 적용 및 확인 (Windows PowerShell)

이전 observations-v1 패치까지 적용한 작업 트리에서 실행한다.
이 md는 설명서이며 실행하거나 DB에 넣는 파일이 아니다.

```powershell
cd C:\Users\USER\Desktop\BOA-git
git apply --check "$HOME\Downloads\boa-cosmetic-amounts-v1.patch"
git apply "$HOME\Downloads\boa-cosmetic-amounts-v1.patch"
cd backend
docker compose exec api python -m unittest discover -s tests -v
docker compose exec api python scripts/audit_cosmetic_amount_interpretation.py data/beauty_catalog.db
```

각 명령이 실패하면 다음 명령을 실행하지 않는다. Alembic, seed, --apply는 필요 없다.
새 스크립트는 원본 SQLite를 읽기 전용으로 검증한다. PostgreSQL에 접속하지 않으며
보고서는 표준 출력만 사용한다. WAL 동반 원본이나 잘못된 소유 관계 등은 기존
read_snapshot 검증에 따라 중단한다.

## 이번 스냅샷 검증 결과

SHA256: `7096c10e71cde631c9083e8eb351fcb75cd700c542fef23a716e6b7adabb0216`

- 기록: 76,990
- missing: 74,403 / single: 2,585 / dual: 1 / unparsed: 1
- 단일 단위: % 336 / ppm 1,637 / ppb 591 / mg 17 / IU/g 4
- 특수 사례: 23건 (mg 17, IU/g 4, 이중 표기 1, 잘못된 형식 1)
- 이 스냅샷의 허용 형식 비율 값에서는 상한 초과나 명시적 0이 발견되지 않음

원본 파일 해시가 분석 전후 동일함을 확인했다. 로컬 격리 환경의 전체 테스트
92개가 통과했다. 사용자의 PostgreSQL을 직접 검사한 결과는 아니다.

## 다음 판단의 경계

함량 표기 유무를 가점으로 사용하지 않는다. 연구 용량과의 비교는 완제품 내
성분 농도, 제형, 사용 방식, 연구 대상과 지표의 대응을 별도 검토한 뒤 판단한다.
이번 패치는 그 판단에 필요한 원문 해석 단계만 제공한다.
