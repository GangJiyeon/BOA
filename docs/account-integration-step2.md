# 회원 연동 2단계 — 선택 동의와 회원 탈퇴 화면

2026-11-14. 기존 백엔드 API를 프론트 계정 화면에 연결했다. 운영 계정 삭제·배포·DB 마이그레이션은 수행하지 않았다.

## 변경

- `src/api/account.ts`: ConsentStatus 타입, 동의 조회·변경·회원 삭제 호출 추가.
- `components/AccountPreferences.tsx`: 회원 분기에서 현재 약관 동의를 조회하고 표시. 필수 약관은 변경 불가, 선택 약관만 변경 가능.
- 동의 조회 실패 시 오류와 재조회 버튼 제공. 언마운트 시 조회 취소.
- 동의 변경은 서버가 돌려준 상태로 반영. 요청 실패 시 체크 상태 유지.
- 탈퇴는 삭제 안내 → 확인 체크 → 최종 버튼 순서. 취소하면 확인 체크 초기화. 최종 버튼 전에는 DELETE를 보내지 않음.
- 탈퇴 성공 후에만 AccountPage의 회원·인증 입력·가입 토큰·동의 입력을 비우고, 기존 onLogout 콜백으로 상위 화면의 사진·분석 결과를 초기화. actor·quota도 기존 조회 흐름으로 갱신.
- 실패 시 회원·분석 결과를 유지하고 오류 표시. 화면 작업들은 같은 useTask를 공유해 동의 저장·로그아웃·언어 저장·탈퇴가 겹치지 않게 처리.

## 구현 이유

동의를 미리 체크한 뒤 서버 실패 때 되돌리는 방식 대신 성공 응답을 받은 후 바꾼다. 화면이 실제 저장 상태와 달라지는 경우를 줄이기 위해서다.

탈퇴 성공 전에는 화면 데이터를 지우지 않는다. 삭제 실패를 곧바로 로그아웃으로 표시하면 실제 계정 상태와 화면이 달라지고, 사용자가 진행 중인 결과도 잃기 때문이다.

탈퇴의 삭제 대상은 기존 백엔드 로직을 따른다. 여기서 새 파일 삭제나 재인증 정책을 추가한 것은 아니다. 사진 보관 동의 철회 후 실제 파일 삭제는 기존 서버 TODO로 남아 있으며, 공식 약관 본문 연결도 후속 작업이다.

## 검증

- TypeScript: `node_modules/.bin/tsc -p tsconfig.app.json --noEmit` 통과.
- 프로덕션 빌드: `node_modules/.bin/vite build` 통과.
- 기존 API 클라이언트 테스트 통과: 인증 갱신·204 빈 응답 처리 포함.
- 새 `scripts/test-account-dom.cjs` 통과: 실제 AccountPage를 React + jsdom에 렌더링하고 클릭 이벤트로 동작 확인. API 응답은 대역이다.
- 필수 약관 비활성화, 선택 동의 AGREE/WITHDRAW 전송, 저장 실패 시 기존 상태 유지, 조회 실패 후 재시도 확인.
- 확인 전 삭제 요청 없음, 탈퇴 취소 시 체크 초기화, 삭제 실패 시 계정·결과 유지, 처리 중 중복 요청 차단 확인.
- 삭제 성공 204 이후 초기화 콜백·actor 재조회 호출, 회원 정보 숨김·완료 안내 확인.

프론트 폴더에서 실행:

```sh
node_modules/.bin/tsc -p tsconfig.app.json --noEmit
node_modules/.bin/vite build
node scripts/test-api-client.mjs
BOA_TEST_MODULES=/tmp/boa-account-dom/node_modules node scripts/test-account-dom.cjs
```

마지막 명령에는 esbuild·jsdom이 설치된 테스트 도구 폴더가 필요하다. 이번 실행은 임시 폴더에 설치했으며 프로젝트 package.json·lockfile에 테스트 의존성을 추가하지 않았다. 실제 서버 쿠키·DB 삭제·외부 발송은 별도 통합 확인이 필요하다.
