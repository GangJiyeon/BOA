# 회원 연동 3단계 — 내 분석 이력

2026-11-14. 로컬 구현. 배포·운영 DB 변경·마이그레이션 없이 기존 테이블로 조회한다.

## 사용자 흐름

1. 시작하기·계정 화면에서 로그인한다.
2. 내 분석 이력에 서버에 저장된 피부 분석·헤어 추천이 최신순으로 나온다.
3. 전체·피부 분석·헤어 추천 필터, 20개 단위 이전·다음 이동을 사용할 수 있다.
4. 결과 보기를 누르면 같은 화면에서 기존 피부 지표 또는 헤어 추천 상세를 확인한다.
5. 새로고침·재로그인 후에도 서버의 본인 기록을 다시 조회한다. 이번 분석 결과 화면에도 계정 이력으로 가는 링크를 추가했다.

## API와 구현 이유

`GET /api/me/analyses?kind=all&limit=20&offset=0`

```json
{
  "items": [{ "kind": "skin", "id": 12, "created_at": "2026-11-14T01:00:00Z" }],
  "limit": 20,
  "offset": 0,
  "has_more": false
}
```

- 회원 인증과 DB 회원 존재 검사를 거친다. 회원 번호는 요청값이 아닌 인증된 actor에서 가져온다.
- SkinAnalysis와 HairRecRun 각각에 user_id 필터를 적용한 뒤 UNION ALL로 합친다. 타인·비회원·소유자 없는 결과는 제외된다.
- 시간 내림차순, 종류 오름차순, ID 내림차순으로 정렬한다. 피부·헤어 테이블에 같은 ID가 있어도 별개 기록으로 표시한다.
- DB에서 offset과 limit을 적용해 전체 기록을 메모리에 올리지 않는다. limit+1개 조회로 다음 페이지 여부를 판단하고 COUNT 쿼리를 줄인다. limit은 1~50으로 제한한다.
- 목록은 종류·번호·시각만 제공한다. 상세는 기존 소유자 검사 API를 재사용해 점수·수분·헤어 응답 변환을 중복 구현하지 않는다.
- 프론트는 메모리의 이번 결과와 서버 이력을 분리한다. 상세를 열어도 새 분석 실행이나 이번 결과 덮어쓰기는 일어나지 않는다.
- 요청 취소·취소된 응답 무시로 필터 변경이나 화면 이탈 후 오래된 결과 표시를 막는다. 빈 상태·오류·재시도를 제공한다.

## 범위와 제약

- 포함: 회원 피부 분석, 완료된 헤어 추천 실행, 가입·QR 이관으로 회원 소유가 된 해당 기록.
- 제외: 추천 실행 전의 얼굴형 분석만 있는 기록, AI 스튜디오 합성 이력, 저장하지 않은 화장품 추천 응답.
- 과거 소유자가 비어 있던 결과를 임의로 특정 회원에게 붙이지 않는다.
- OFFSET 페이지 방식이라 조회 중 다른 탭에서 새 기록을 추가하면 페이지 사이 항목이 이동할 수 있다. 고정된 데이터에서 같은 시각의 정렬 순서는 일정하다.
- 로그인된 기존 회원에게 비회원 결과를 자동 이관하는 새 정책은 추가하지 않았다.

## 검증

- 새 백엔드 이력 테스트 6개 통과: 빈 목록·회원 인증, 타인/비회원 제외, 결합 정렬·페이지 분할, 필터·입력 범위, 비회원 결과 이관 후 실제 JWT 쿠키 조회·상세 열기, 삭제된 회원 접근 거절.
- 기존 소유자 회귀 테스트 10개 통과.
- 새 이력 화면 DOM 테스트 통과: 목록·필터·페이지 이동·한국 시간·피부/헤어 상세·오류 재시도·빈 상태·재마운트 재조회·늦은 응답 및 화면 이탈 취소.
- 기존 동의·탈퇴 화면 테스트와 API 클라이언트 테스트 통과.
- TypeScript 검사와 프로덕션 빌드 통과.
- API 테스트는 SQLite와 실제 라우트·DB 쿼리를 사용한다. UI 테스트는 실제 React 컴포넌트를 jsdom에서 조작하며 HTTP 응답은 대역이다. 실제 Google 로그인·운영 PostgreSQL·사용자 브라우저 실사용은 이번 검증에 포함하지 않았다.

실행 명령:

```sh
# backend 폴더
.venv/bin/python -m unittest discover -s tests -p test_account_history.py -v
.venv/bin/python -m unittest discover -s tests -p test_analysis_ownership.py -v

# frontend 폴더
node_modules/.bin/tsc -p tsconfig.app.json --noEmit
node_modules/.bin/vite build
node scripts/test-api-client.mjs
BOA_TEST_MODULES=/tmp/boa-account-dom/node_modules node scripts/test-account-history-dom.cjs
BOA_TEST_MODULES=/tmp/boa-account-dom/node_modules node scripts/test-account-dom.cjs
```

DOM 테스트 도구는 이전 단계의 임시 폴더를 사용하며 프로젝트 의존성은 변경하지 않았다.
