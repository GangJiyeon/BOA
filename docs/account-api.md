# 계정 모듈 API·데이터

담당: GangJiyeon · 기준: 2026-11-26 코드

계정 모듈의 테이블, 쿠키, API, 다른 파트 연결 방법, 환경변수. 결정 이유는 [account-decisions.md](account-decisions.md)

## 담당 범위

| 영역 | 기능 |
|---|---|
| 인증 | Google 로그인, 토큰 갱신, 로그아웃 |
| 가입 | 국적·거주 여부 입력, 약관 동의, 비회원 결과 이관 |
| 계정 | 내 정보, 선택 동의 변경, 내 분석 이력, 회원 탈퇴 |
| 비회원 | 촬영 전 동의 + 비회원 세션, 기능별 하루 횟수·IP 상한 |
| QR | 결과 조회, 내 계정에 저장 |
| 키오스크 | 기기 등록·해제, 사용자별 세션 |
| 공통 | 요청자 판별 `get_actor()`, 횟수 체크 `check_quota()`, 매일 정리 배치 |

## 요청 흐름

```text
Google 인증 ─┬─ 기존 회원 → 로그인 → 인증 쿠키
            └─ 신규 → 가입 토큰(10분) → 가입 정보 + 약관 동의
                                        → 회원 생성 + 동의 이력 + 비회원 결과 이관 → 자동 로그인

비회원: 촬영 전 동의 → 비회원 세션(7일) → 분석(하루 횟수 제한) → QR → 가입 or QR 저장으로 이관
키오스크: 관리자 코드로 기기 등록 → 사용자마다 새 세션 → 종료 → QR로 폰에서 확인·저장
```

## 요청자 판별 `get_actor()`

FastAPI `Depends`로 쓰는 함수. 위에서부터 처음 맞는 결과를 반환

1. `kiosk_token`이 유효하고 해제 전 → **키오스크** (+ 이 기기에서 시작한 비회원 세션)
2. `access_token`이 유효하고 회원이 DB에 있음 → **회원**. 토큰이 있는데 만료·위조·탈퇴면 401
3. `guest_id` 쿠키의 세션이 만료 전 → **비회원**
4. 모두 아님 → **익명**

| 요청자 | 결과 `user_id` | 결과 `guest_id` | 횟수 제한 |
|---|---|---|---|
| 회원 | user_id | NULL | 없음 |
| 비회원 | NULL | guest_id | 기능별 하루 + IP 상한 |
| 키오스크 | NULL | guest_id | 없음 |
| 익명 | 분석 거부 (403, 촬영 동의 먼저) | | |

다른 파트 연결 예

```python
from app.api.deps import Actor, require_analysis_actor
from app.services.quota import check_quota

@router.post("/analyses")
def create(..., actor: Actor = Depends(require_analysis_actor), db: Session = Depends(get_db)):
    check_quota(db, actor, "skin")   # 비회원이 한도를 넘으면 429
    ...  # actor.user_id / actor.guest_id 로 저장
```

`check_quota` 종류: `skin`(피부 분석), `hair`(헤어 추천, 요청 1번 = 사진 3장 = 1회), `studio`(AI 헤어 합성, 실패는 안 셈)

## 테이블

| 테이블 | 칼럼 |
|---|---|
| `users` | id, google_sub(UQ), email(UQ, 소문자), nationality char(2), resides_in_korea, created_at, last_login_at |
| `terms` | id, type, version, required, effective_at — UQ(type, version) |
| `consent_histories` | id, user_id → users CASCADE, terms_id → terms, action(AGREE/WITHDRAW), created_at |
| `refresh_tokens` | id, user_id → users CASCADE, token_hash(UQ), expires_at |
| `kiosks` | id, token_hash(UQ), registered_at, revoked_at |
| `guest_sessions` | id uuid(쿠키 `guest_id` 값), user_id → users CASCADE, kiosk_id → kiosks, ip_hash, qr_token_hash(UQ), expires_at, face_terms_id → terms |

비밀번호 칼럼 없음. 분석 결과 테이블(`skin_analyses`, `face_analysis`, `hair_rec_run`, `hair_renders`)은 `user_id`·`guest_id` 칼럼만 있고 FK가 없어서, 탈퇴·만료 정리 때 계정 모듈이 직접 삭제

## 쿠키

| 이름 | 내용 | 수명 |
|---|---|---|
| `access_token` | `user_id`가 든 JWT (httpOnly) | 토큰 15분, 쿠키 30일 (만료 토큰에 401을 주려고) |
| `refresh_token` | 무작위 문자열, DB에는 SHA-256 (httpOnly, path `/api/auth`) | 30일, 갱신마다 교체 |
| `guest_id` | 비회원 세션 UUID (httpOnly) | 세션 만료(7일)까지 |
| `kiosk_token` | 무작위 문자열, DB에는 SHA-256 (httpOnly) | 400일, 해제 전까지 |

모두 `SameSite=Lax`. `Secure`는 `COOKIE_SECURE`로 켬

## API

### 요청자·약관

- `GET /api/actor` → `{ kind: member | guest | kiosk | anonymous }`
- `GET /api/terms/current` → 종류별 현재 약관 (`effective_at <= now` 중 최신)

### 인증

- `POST /api/auth/google` `{ code }` → 기존 회원이면 로그인, 처음이면 `{ signup_required: true, signup_token }`
  - ID 토큰 서명·발급자·대상 앱·만료·`email_verified` 검증 실패 401, 다른 Google 계정과 연결된 이메일 409, 설정 없으면 503
- `POST /api/auth/signup` `{ signup_token, nationality: "KR", resides_in_korea, agreed_terms_ids }` → 201 `{ user_id }`
  - 가입 토큰 만료 401, 필수 약관 누락·옛 버전 400, 중복 가입 409, 이미 로그인 상태 400
  - 비회원 세션이 있으면 결과 이관 후 `guest_id` 쿠키 삭제
- `POST /api/auth/refresh` → 204. 예전·만료 토큰은 401 + 인증 쿠키 삭제
- `POST /api/auth/logout` → 204. `guest_id`는 유지
- 개발용 (`DEV_LOGIN=true`일 때만): `POST /api/auth/dev-login`, `GET /api/auth/google/dev-start` → `dev-callback`

### 계정 (로그인 필요)

- `GET /api/me` → `{ email, nationality, resides_in_korea, google_linked }`
- `GET /api/me/consents` → 종류별 `{ type, required, agreed, version, updated_at }`
- `POST /api/me/consents` `{ type, action: AGREE | WITHDRAW }` → 선택 약관만, 필수 약관은 400
- `GET /api/me/analyses?kind=all|skin|hair&limit=20&offset=0` → 피부 분석·헤어 추천 기록 최신순
- `DELETE /api/me` → 204. 분석 결과 → 회원(CASCADE) → 인증 쿠키 순으로 삭제

### 비회원

- `POST /api/guest/session` `{ face_terms_id, age_confirmed: true }` → 201 `{ qr_token, expires_at }`
  - 현재 FACE_IMAGE 약관이 아니면 400, 회원이면 400. 유효한 세션이 있으면 이어 쓰고 QR만 재발급
- `GET /api/guest/quota` → 기능별 `{ limit, used, remaining }`. 회원·키오스크·익명은 `null`
- 한도 초과 429 `code`: `GUEST_DAILY_LIMIT`(가입 안내) / `IP_DAILY_LIMIT`

### QR

- `GET /api/qr/{token}` → 로그인 불필요, `{ expires_at, skin: [...] }` (사진 id는 비움)
- `POST /api/qr/{token}/claim` → 로그인 필요, 결과 이관 후 같은 QR 만료. `{ skin_count }`
- 없는·만료·이관된 링크 모두 404 "만료된 링크입니다"

### 키오스크

- `POST /api/kiosk/register` `{ admin_code }` → 201, `kiosk_token` 쿠키. 틀리면 403, `ADMIN_CODE` 없으면 503
- `POST /api/kiosk/revoke` `{ admin_code, kiosk_id }` → 없거나 이미 해제면 404
- `GET /api/kiosk/me` → `{ kiosk_id, registered_at, session_active }`
- `POST /api/kiosk/session` → 촬영 전 동의 + 항상 새 세션 `{ qr_token, expires_at }`
- `DELETE /api/kiosk/session` → 세션 쿠키만 삭제 (결과는 QR로 계속 조회)

## 결과 이관 `transfer_to_user()`

가입·QR 저장 공통, 한 트랜잭션

1. 비회원 세션: `user_id = 회원`, `qr_token_hash = NULL`, `expires_at = NULL`
2. 세션의 결과(`skin_analyses`, `face_analysis`, `hair_rec_run`, `hair_renders`): `user_id = 회원`

## 매일 정리 배치

`services/cleanup.py`, 매일 04:00 KST (APScheduler) + `scripts/cleanup_expired.py` 수동 실행

1. 만료됐고 이관 안 된 비회원 세션의 분석 결과 삭제
2. 보관 기간(7일) 지난 AI 합성 이미지 삭제
3. 그 비회원 세션 삭제
4. 만료된 리프레시 토큰 삭제

## 환경변수

| 이름 | 용도 | 기본값 |
|---|---|---|
| `JWT_SECRET` | 액세스·가입 토큰 서명 | 개발용 값, 배포 시 변경 |
| `IP_HASH_SECRET` | `ip_hash` HMAC | 개발용 값, 배포 시 변경 |
| `COOKIE_SECURE` | 쿠키 Secure | 로컬 false, 배포 true |
| `ACCESS_TOKEN_MINUTES` / `REFRESH_TOKEN_DAYS` / `SIGNUP_TOKEN_MINUTES` | 토큰 수명 | 15 / 30 / 10 |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | Google OAuth (비우면 503) | — / — / `postmessage` |
| `GUEST_DAILY_LIMIT_SKIN` / `_HAIR` / `_STUDIO` | 비회원 하루 횟수, 0이면 없음 | 3 / 3 / 2 |
| `IP_DAILY_LIMIT` | 같은 IP 합산 상한, 0이면 끔 | 30 (행사장은 0) |
| `ADMIN_CODE` | 키오스크 등록·해제 (비우면 503) | 빈 값 |
| `DEV_LOGIN` | 개발용 로그인 API | false |

## 배포 전 체크

- `JWT_SECRET`, `IP_HASH_SECRET`, `ADMIN_CODE`를 길고 무작위인 값으로, `COOKIE_SECURE=true`, `DEV_LOGIN=false`
- 행사장: `IP_DAILY_LIMIT=0`, 태블릿에서 키오스크 등록 후 `GET /api/kiosk/me`로 번호 메모
- Google OAuth 동의 화면을 "프로덕션으로 게시" (테스트 모드는 테스트 사용자만 로그인)
- 프록시 뒤라면 uvicorn `--proxy-headers`
- 위 값을 잊어도 서버가 경고 없이 켜지므로 직접 확인

## Google 콘솔 설정 (로컬 테스트)

1. console.cloud.google.com → 프로젝트 → OAuth 동의 화면(외부, 범위 기본 email·openid, 테스트 사용자에 내 계정)
2. 사용자 인증 정보 → OAuth 클라이언트 ID → 웹 애플리케이션
   - JavaScript 원본: `http://localhost:5173`, `http://localhost:8000`
   - 리디렉션 URI: `http://localhost:8000/api/auth/google/dev-callback`
3. 클라이언트 ID·보안 비밀을 `backend/.env`에 → 서버 재시작 → `http://localhost:8000/api/auth/google/dev-start`
