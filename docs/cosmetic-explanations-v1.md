# 추천 설명 분리 v1

현재 BOA 추천 API/화면의 설명 변경이다. 점수·필터·정렬·규칙 시드·DB 스키마는 변경하지 않는다.
1학기 프로젝트 코드는 사용하지 않는다.

## API 추가 필드

- 응답 `explanation_version`: cosmetic-explanations-v1
- 매칭별 `interpretation`: 성분표 매칭 사실, 개발용 지표 연결 가정, 미확인 정보
- 제품별 `shared_evidence_groups`: 동일 근거 URL이 두 개 이상 매칭 지표에 연결된 경우

`product_efficacy_verified`는 false이며 지표 가정은 development_assumption이다.
함량 관측 테이블이나 파서 결과는 이번 추천에서 조회/사용하지 않는다.
함량이 없다고 단정하지 않고 '연구 농도와의 대응을 평가하지 않음'으로 표현한다.
공유 근거는 실제 매칭 결과의 URL로 묶는다. 이름에 나이아신아마이드가 있다는 이유만으로
공유라고 표시하지 않는다. 서로 다른 URL이라고 독립적인 연구/효과임을 보증하지도 않는다.

수분은 센서 검증이 끝난 값으로, 홍조는 진단으로 오인하지 않도록 설명한다.
밝기/균일도는 색소 관련 지표라는 가정, 트러블은 여드름/모공 막힘 관련 가정을 표시한다.
이는 가정의 노출이지 팀의 지표 계약 확정이나 새 임상 검증이 아니다.
회의에서 의미가 확정되면 설명뿐 아니라 실제 매칭 규칙의 적용 가능성도 함께 검토해야 한다.

## 화면

제품 카드에서 성분표 매칭과 완제품 효과 미검증을 표시한다.
근거가 공유되면 이를 접지 않은 본문에도 표시한다.
세부 설명을 펼치면 1) 성분 함유 매칭 2) 지표 연결 가정 3) 미확인 정보와
기존 DB의 연구/안내 요약·한계·링크가 보인다.
이전 API 응답에는 상세 설명이 없다는 안내를 표시하며 화면 오류가 나지 않도록 한다.

## 검증

- 신규 테스트 8개: 가정/미검증 상태, 공유 근거 동적 구성, 중복 가점 없음,
  빈 결과, API SELECT-only, 관측 테이블 없이도 실행 가능 등.
- 로컬 전체 108개 통과 (정책 비교 테스트 8개 포함).
- 프론트 TypeScript/Vite build, oxlint 통과.
- 첨부 SQLite의 18개 시나리오에서 새 필드를 제거한 기존 응답 전체가 변경 전과 동일.
  응답 집합 SHA256: `9b07f345daf3b11ab9a7cf1d7aaba25600d07ab468b808d23b081301aca69476`.
- 사용자 PC/브라우저 화면을 직접 확인한 것은 아니다. 실제 브라우저 시각 검수는 미완료.

## 적용 (PowerShell)

이 패치는 함량 해석 v1까지 적용한 상태를 기준으로 한다.
별도 policy-review-v1 패치를 적용했든 하지 않았든 이번 패치와 파일이 겹치지 않는다.
설명서(md)는 읽는 문서다. DB에 넣거나 별도로 실행하지 않는다.

```powershell
cd C:\Users\USER\Desktop\BOA-git
git apply --check "$HOME\Downloads\boa-cosmetic-explanations-v1.patch"
git apply "$HOME\Downloads\boa-cosmetic-explanations-v1.patch"
cd backend
docker compose exec api python -m unittest discover -s tests -v
cd ..\frontend
pnpm build
pnpm lint
```

명령 하나라도 실패하면 다음 명령을 실행하지 않는다.
정책 비교 패치를 미적용했다면 100개, 적용했다면 108개 테스트가 예상된다.
DB 마이그레이션, seed, import, --apply는 필요 없다. Git 커밋/푸시는 수행하지 않았다.
기존 개발 화면을 새로고침해 추천을 조회하고 제품 카드의 '왜 매칭됐나요?'를 펼쳐 확인한다.
