# BOA 문서

기능별로 **먼저 읽을 문서**와 개발 중 남긴 **이력 문서**를 나눴어요. 이력 문서는 당시 실험·결정 기록이라 현재 코드와 다를 수 있어요.

## 시작

| 문서 | 내용 |
|---|---|
| [setup.md](setup.md) | 설치·실행·DB·문제 해결 |
| [frontend-scaffold-v1.md](frontend-scaffold-v1.md) | 프론트엔드 구조 |

## 피부 분석 — Johndoe557

| 문서 | 내용 |
|---|---|
| [피부분석_로직_설계서.docx](../피부분석_로직_설계서.docx) | 지표별 측정 영역·점수 산출 설계 |
| [cosmetic-skin-contract-v1.md](cosmetic-skin-contract-v1.md) | 피부 분석 결과 → 추천 입력 계약 |

## 피부 수분 측정 (Arduino) — sby09122222

| 문서 | 내용 |
|---|---|
| [arduino-integration-guide.md](arduino-integration-guide.md) | 준비물·배선·현장 연결 |
| [moisture-protocol.md](moisture-protocol.md) | 센서 ↔ 웹 통신 규약 |
| [moisture-v11.md](moisture-v11.md) | 최신 신호 취득 방식과 외부 근거 검토 |
| [sensor-hydration-criteria-review.md](sensor-hydration-criteria-review.md) | 센서 신호 → 수분 상태 판정 기준 검토 |

<details>
<summary>이력</summary>

[arduino-integration-report](arduino-integration-report.md) · [moisture-v6](moisture-v6.md) · [v7](moisture-v7.md) · [v7.1](moisture-v7.1.md) · [left-cheek-v8](moisture-left-cheek-v8.md) · [v9](moisture-v9.md) · [v10](moisture-v10.md) · [acquisition](moisture-acquisition.md) · [acquisition-and-policy](moisture-acquisition-and-policy.md) · [confirmed-only](moisture-confirmed-only.md) · [contact-response](moisture-contact-response.md) · [drive-and-display](moisture-drive-and-display.md) · [fixed-3s](moisture-fixed-3s.md) · [latest-audit](moisture-latest-audit.md) · [quality-fix](moisture-quality-fix.md) · [score60-linear-v1](moisture-score60-linear-v1.md) · [hydration-estimator](hydration-estimator.md) · [hydration-recommendation-policy](hydration-recommendation-policy.md)

</details>

## 화장품 추천 — sby09122222

| 문서 | 내용 |
|---|---|
| [cosmetic-recommendation-preview.md](cosmetic-recommendation-preview.md) | 추천 API 입력·순서·응답 |
| [cosmetic-ingredient-rulebook.md](cosmetic-ingredient-rulebook.md) | 성분 규칙표·근거·DB 설계 |
| [cosmetic-quality-audit.md](cosmetic-quality-audit.md) | 18개 시나리오 품질 검수 |
| [cosmetic-care-context-v1.md](cosmetic-care-context-v1.md) | 5개 지표 기반 관리 선택 |

<details>
<summary>이력</summary>

[backend-scope-v1](cosmetic-backend-scope-v1.md) · [daily-care-v1](cosmetic-daily-care-v1.md) · [explanations-v1](cosmetic-explanations-v1.md) · [amount-interpretation](cosmetic-amount-interpretation.md) · [observation-import](cosmetic-observation-import.md) · [evidence-reassessment](cosmetic-evidence-reassessment.md) · [rule-review-decision](cosmetic-rule-review-decision-20261005.md) · [ranking-api-v1](cosmetic-ranking-api-v1.md) · [ranking-comparison-v1](cosmetic-ranking-comparison-v1.md) · [tie-pagination-v1](cosmetic-tie-pagination-v1.md) · [integration-debug-v1](boa-integration-debug-v1.md)

</details>

## 헤어 — teahoonlee · GangJiyeon

| 문서 | 내용 |
|---|---|
| [hair-studio-v1.md](hair-studio-v1.md) | AI 헤어 합성 흐름·API·실패 조건 |
| [hair-synthesis-study-guide.md](hair-synthesis-study-guide.md) | 합성 코드 함수별 설명 |

## 메이크업 — GangJiyeon

| 문서 | 내용 |
|---|---|
| [makeup-eye-shades.md](makeup-eye-shades.md) | 현재 렌더링 동작·에셋·변경 기록 |

## 계정 — GangJiyeon

| 문서 | 내용 |
|---|---|
| [account-decisions.md](account-decisions.md) | 설계 결정과 이유 |
| [account-api.md](account-api.md) | 테이블·쿠키·API·환경변수·배포 체크 |
| [account-study-guide.md](account-study-guide.md) | 요청 → API → 서비스 → DB 흐름 설명 |

<details>
<summary>이력</summary>

[integration-step1 (결과 소유자·접근 제한)](account-integration-step1.md) · [step2 (선택 동의·탈퇴 화면)](account-integration-step2.md) · [step3 (내 분석 이력)](account-integration-step3.md)

</details>
