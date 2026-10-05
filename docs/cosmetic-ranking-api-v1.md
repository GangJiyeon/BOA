# 추천 API 순위 정책 연결

엔진 cosmetic-preview-v3.3 / 순위 정책 cosmetic-ranking-v1

## 변경

기존 비교용 순위 함수를 실제 POST `/api/cosmetics/recommendations/preview`에 연결했다. DB의 지표 구간·성분 규칙으로 후보를 선정하고, 전체 후보를 요청한 정책으로 정렬한 다음 최대 5개를 반환한다. 후보 필터와 사용자 배제는 모든 순위 정책에 선행한다.

| 요청 ranking_policy | 순서 |
|---|---|
| metric_count (생략 시 기본) | 매칭 지표 수 → 세트 의심 후순위 → ID |
| concern_groups | 매칭 고민 그룹 수 → 세트 의심 후순위 → ID |
| explicit_priority | 지정 고민 매칭 여부 → 그룹 수 → 세트 의심 후순위 → ID |

그룹은 수분, 붉은기, 색소 관련(밝기·균일도), 트러블로 구분한다. 현재 규칙에서 밝기·균일도가 공유하는 근거의 중복 집계를 줄이는 프로젝트 가설이다. 두 지표의 임상적 동등성이나 우수한 추천 품질을 입증한 것이 아니다. 향후 규칙이 바뀌면 그룹 정의와 정책 버전도 검토해야 한다. 기존 동작을 임의로 교체하지 않도록 기본 정책은 유지했다.

explicit_priority는 priority_metric을 필수로 받는다. 다른 정책에서 priority_metric을 보내거나, 알 수 없는 정책을 보내면 422다. 우선 고민은 측정값이 있고 개선 필요이며 활성 매칭 규칙이 있는 지표여야 한다. 미측정 수분, 정상 지표, 현재 가점 보류 중인 붉은기는 422다. 후보가 비어 있어도 입력 검증을 생략하지 않는다.

우선 고민 규칙이 있어도 제품 필터 결과 해당 고민 매칭 제품이 없을 수 있다. 이때 배제된 제품을 복구하지 않고, 남은 그룹 기준으로 정렬하며 notices에 해당 사실을 반환한다.

## 응답

- ranking_policy / ranking_policy_version / ranking_basis / priority_metric: 사용한 정렬 정책을 재현할 정보
- 제품별 match_count: 기존 매칭 지표 수, 의미와 값 유지
- 제품별 matched_group_count: 밝기·균일도를 한 그룹으로 계산한 매칭 수
- 제품별 priority_matched: 지정 고민 충족 여부
- 제품별 ranking_tie_count: 해당 정책의 정렬 키(ID 제외)가 같은 전체 후보 수, 본인 포함

명시적 우선 고민 정렬은 단일 점수로 환산하지 않는다. 임의 가중치, 농도 점수, 미측정값 추정도 추가하지 않는다. ID는 동점 표시 순서일 뿐 품질 점수가 아니다. 그룹 정책으로도 동점은 남는다.

기존 프론트는 새 요청 필드를 보내지 않으므로 기존 정책을 사용한다. 이번 패치는 UI를 변경하지 않는다. 향후 UI에서 대안 정책을 선택하게 하면 match_count만을 순위 점수처럼 표시해서는 안 되며 ranking_basis와 matched_group_count를 사용해야 한다.

## 사용자 PC에서 API 확인

```powershell
$body = @{
  scores = @{ moisture=20; redness=80; brightness=20; trouble=80; uniformity=20 }
  ranking_policy = "explicit_priority"
  priority_metric = "moisture"
} | ConvertTo-Json -Depth 5

$result = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/cosmetics/recommendations/preview" -ContentType "application/json" -Body $body
$result | Select-Object engine_version, ranking_policy, ranking_basis, priority_metric
$result.recommendations | Select-Object rank, product_name, match_count, matched_group_count, priority_matched, ranking_tie_count
```

조회 API이며 DB 저장은 없다. API에 해당 필드가 없다는 422가 나오거나 엔진이 v3.3이 아니면 실행 중인 API에 패치가 반영됐는지 확인한다.

## 검증

로컬 전체 테스트 144개 통과. 신규 11개는 기본 순서, 그룹 중복 집계, 우선 고민, 전체 후보 정렬, 사용자 배제, 미측정·정상·규칙 없음 검증, 422 응답, 응답 직렬화, API의 SELECT 전용 동작을 검사한다. DB 통합 테스트는 임시 SQLite를 사용했고 사용자 PostgreSQL에 직접 접속하지 않았다.

사용자 직전 125개에 이번 11개가 추가되므로 동일 구성이라면 136개를 예상한다. 원본 카탈로그 18개 시나리오에서 기존 기본 Top 5와 후보 통계가 보존되는지도 별도 확인했다. 대안 정책의 후보 통계 역시 같다.

DB 마이그레이션, 성분 규칙 시드, 프론트 수정은 없다. 연구 근거 재검증이나 지표 의미 확정은 이번 작업에 포함되지 않는다. 추천 알고리즘의 최종 품질 검증 완료를 뜻하지 않는다.
