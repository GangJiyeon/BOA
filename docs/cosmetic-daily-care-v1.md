# 일상 관리용 화장품 제안 v1

개선 필요 지표가 없는 사용자에게 제품이 전혀 나오지 않던 문제를 해결한다.
개선 목적의 성분 매칭과 일상 관리용 제품 탐색을 별도 응답 모드로 구분한다.

## 변경 범위

- 화장품 추천 엔진·응답 계약·검수 도구와 해당 프론트 결과 화면.
- 피부 분석, 사진 품질 기준, 헤어·인증 등 다른 파트의 동작은 변경하지 않는다.
- DB 스키마·내용 변경 없음. 마이그레이션·재시드·재수집 불필요.
- 기존 DB 활성 규칙을 읽으며, 보류된 성분 규칙을 다시 활성화하지 않는다.

## 모드 선택

| 조건 | 응답 |
| --- | --- |
| 개선 필요 지표에 적용 가능한 활성 매칭 규칙 존재 | `improvement`: 기존 개선 성분 매칭과 순위 유지 |
| 개선 필요 지표 없음 | `daily_care`, 사유 `no_improvement_targets` |
| 개선 필요 지표가 있지만 적용 가능한 활성 매칭 규칙 없음 | `daily_care`, 사유 `no_supported_matching_rules`; 보류 지표는 그대로 공개 |

제품 수가 아니라 지표에 적용할 매칭 규칙의 유무로 모드를 결정한다.
개선 규칙이 존재하지만 제품이 제외되거나 해당 종류에 후보가 없는 경우에는
기존 빈 결과를 유지한다. 이때 일상 관리 제품으로 빈자리를 채우지 않는다.
명시적 우선 고민은 기존처럼 평가 가능한 개선 지표여야 하며, 잘못된 지정은 422다.

## 일상 관리 후보의 선정 기준

1. 기존 전성분 정규화·제품 종류·사용 방식 검사를 통과해야 한다.
2. 사용자 제외 성분 및 홍조 조건부 배제를 동일하게 적용한다.
3. DB 활성 수분 매칭 규칙(`moisture`, `개선 필요`, `match`, `always`)의
   성분을 전성분표에서 정확히 확인한다. 현재 시드 기준 글리세린·판테놀·하이알루로닉애씨드다.
4. 이 함유 확인은 일상 관리 후보를 찾는 프로젝트 정책이며,
   해당 사용자의 수분 부족이나 개선 효과를 추정하는 용도가 아니다.
5. 성분 수로 가점하지 않는다. 기획·세트 의심 제품을 후순위로 하고,
   같은 조건은 제품 ID로 안정적으로 표시한다. 효능·인기도·개인 적합도 순위가 아니다.
6. 기존 5개 조회·동점 그룹 더보기·스냅샷 검증을 유지한다.

수분이 미측정이면 계속 미측정으로 남으며, 양호·건조로 대체하지 않는다.
활성 보습 성분 규칙이 없거나 필터를 통과하는 제품이 없으면 사유와 함께 빈 결과를 반환한다.
현재는 사용감·가격·사용자 선호를 반영한 일상 제품 순위가 아니다.

## 응답 필드

- `recommendation_mode`: `improvement` 또는 `daily_care`.
- `daily_care_reason`: 일상 관리 모드 선택 사유; 개선 모드는 `null`.
- `recommendation_notice`: 모드와 미측정 상태에 대한 사용자 안내.
- `ranking_policy`: 요청한 기존 개선 순위 정책. 일상 모드의 실제 표시 기준은
  `ranking_basis`와 `ranking_policy_version=cosmetic-daily-care-v1`로 구분한다.
- 일상 관리 제품은 `match_count=0`, `matches=[]`, `matched_group_count=0`.
- `daily_care_ingredients`와 `daily_care_rules`에 함유 성분 및 기존 연구의 적용 한계를 별도 제공한다.
- `stats.no_daily_care_ingredient`는 일상 관리 성분 기준에서 탈락한 수다.
  나머지 통계와 함께 전체 카탈로그를 중복 없이 분할한다.

프론트는 일상 모드에서 ‘일상 관리용 제품 제안’과 함유 근거를 표시하고
‘0/0점’ 또는 ‘개선 효과’로 표현하지 않는다. 종류 필터 및 더보기는 같은 모드를 유지한다.
이전 API 응답에 새 필드가 없어도 기존 개선 결과 화면은 표시할 수 있다.
정확한 새 결과 표시를 위해 백엔드와 프론트 패치를 함께 적용한다.

## 적용 및 확인 (Windows PowerShell)

프론트 v5가 적용된 BOA-git 루트에서 내려받은 패치 경로를 지정한다.

```powershell
$patch = "$env:USERPROFILE\Downloads\boa-cosmetic-daily-care-v1.patch"
git apply --check $patch
if ($LASTEXITCODE -eq 0) { git apply $patch }
```

확인 단계에서 오류가 있으면 강제 적용하지 않는다. 정상 적용 후:

```powershell
cd backend
docker compose restart api
docker compose exec api python -m unittest discover -s tests
cd ..\frontend
pnpm build
pnpm lint
node scripts/test-api-client.mjs
cd ..
git diff --check
```

브라우저 새로고침 후 같은 사진으로 다시 분석·추천하거나,
개발용 분석 JSON 입력에 수분 없는 홍조 6·밝기 68·트러블 9·균일도 100 결과를 넣는다.
일상 관리 후보와 미측정 안내가 함께 나와야 한다.
수분 20을 별도 입력한 경우에는 기존 수분 개선 매칭으로 전환되어야 한다.
GitHub push/merge는 이 패치에 포함하지 않는다.
