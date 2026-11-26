# BOA

얼굴 사진 한 장으로 **피부 상태를 분석하고, 맞는 화장품·헤어스타일·메이크업을 추천하고 미리 입혀보는** 웹 서비스

- 개발 기간: 2026.09 – 2026.11
- 형태: 캡스톤 디자인 팀 프로젝트 (4인)
- 사용 환경: 개인 웹 + 행사장 키오스크(공용 태블릿)

## 팀

| 팀원 | 담당 |
|---|---|
| GangJiyeon | 계정·인증 (Google 로그인, 비회원 세션, QR, 키오스크, 탈퇴·만료 정리), AI 헤어 스튜디오 (합성·머리색 변경), 메이크업 스튜디오 |
| Johndoe557 | 피부 분석 (홍조·밝기·트러블·균일도), 피부톤·쿠션 호수 추정, 카메라별 보정 |
| sby09122222 | 화장품 추천 (성분 규칙·순위), 피부 수분 센서 (Arduino) 연동, 프론트 화면 흐름, 피부톤 기반 헤어색 추천 |
| teahoonlee | 얼굴형·코·광대 분석, 얼굴 랜드마크 추출, 헤어스타일 추천·카탈로그 |

하드웨어(수분 센서) 조립은 팀 전체가 함께 진행

## 주요 기능

### 피부 분석
얼굴 사진에서 이마·양볼·턱 등 영역을 나눠 **홍조, 밝기, 트러블, 균일도**를 0~100점으로 산출하고 구간별로 판정. 피부톤은 보정 ITA°로 웜·뉴트럴·쿨과 추정 쿠션 호수를 계산

- 카메라 기종별 색 보정 프로필, 정답 호수 CSV로 현장 보정 스크립트
- 고정 장소 반복 촬영에서 h° ±0.8°, ITA° ±1.3°
- 판정 구간은 DB에서 읽어 코드 수정 없이 조정
- 설계: [피부분석_로직_설계서.docx](피부분석_로직_설계서.docx)

### 피부 수분 측정 (Arduino)
UNO R4 WiFi + 정전용량 센서(FDC2112)를 Bluetooth LE로 웹에 연결해 뺨에 한 번 대면 3초간 측정. 측정값은 화장품 추천의 수분 지표로 연결

- 상대 수분 지표이며 임상 수분율 측정기는 아님
- 문서: [현장 연결 가이드](docs/arduino-integration-guide.md) · [최신 신호 취득(v11)](docs/moisture-v11.md)

### 화장품 추천
피부 지표 5개(수분·홍조·밝기·트러블·균일도)를 받아 DB의 제품 전성분과 **성분 규칙표**를 대조해 최대 5개 추천. 제품마다 어떤 성분이 왜 맞는지 근거와 한계를 함께 표시

- 홍조 유발 성분·직접 지정 성분 제외
- 규칙은 근거·버전 테이블로 관리 (활성 매칭 6, 조건부 배제 8, 보류 6)
- 18개 시나리오로 추천 품질 검수
- 문서: [추천 API](docs/cosmetic-recommendation-preview.md) · [성분 규칙표](docs/cosmetic-ingredient-rulebook.md)

### 헤어스타일 추천
사진 3장에서 MediaPipe 얼굴 랜드마크로 **얼굴형·코·광대 폭**을 분석해 성별별 카탈로그(여 40·남 40종)에서 어울리는 스타일 추천. 피부톤 밝기로 헤어색도 추천

### AI 헤어 스튜디오
내 사진에 카탈로그 스타일을 합성하고 **32가지 머리색**을 즉시 바꿔봄

- 이미지 편집 AI는 합성 시작 때 1번만 호출, 색 변경은 브라우저에서 처리 (추가 AI 비용 없음)
- 얼굴은 원본을 살리고 랜드마크로 AI 결과를 정렬한 뒤 경계를 섞음 (얼굴 형태는 변형하지 않음)
- 얼굴 크기·기울기·좌우 회전이 기준을 넘으면 AI 호출 전에 거부
- 문서: [헤어 스튜디오](docs/hair-studio-v1.md) · [합성 학습 가이드](docs/hair-synthesis-study-guide.md)

### 메이크업 스튜디오
피부톤 분석 결과를 바탕으로 **4가지 상황(데일리·격식·야외·파티) × 룩**을 성별별로 제공하고, 눈썹·속눈썹·아이섀도·블러셔·립을 사진 위에 가상으로 적용

- 얼굴 사진을 외부 AI로 보내지 않고 서버 전처리 + 브라우저 Canvas·Web Worker로 렌더링
- 눈썹 18종, 속눈썹 5종 에셋
- 문서: [메이크업 표현](docs/makeup-eye-shades.md)

### 계정·비회원·키오스크
가입 없이 체험하고, 마음에 들면 가입해서 결과를 이어받는 흐름

- **Google 로그인**: ID 토큰 서명 검증, JWT 액세스 15분 + 리프레시 30일(갱신마다 교체), 모든 토큰은 httpOnly 쿠키
- **비회원**: 촬영 동의 후 7일 세션, 기능별 하루 횟수 + 같은 IP 상한
- **결과 이관**: 가입하거나 QR로 저장하면 비회원 결과가 회원 계정으로 이동
- **키오스크**: 관리자 코드로 등록한 공용 태블릿, 사용자마다 새 세션, 결과는 QR로 폰에서 확인
- **개인정보**: 얼굴 원본 미저장, IP는 HMAC, 탈퇴 시 전체 결과 삭제, 매일 만료 데이터 정리
- 문서: [설계 결정](docs/account-decisions.md) · [API·데이터](docs/account-api.md)

## 기술 스택

| 영역 | 사용 기술 |
|---|---|
| 프론트엔드 | React 19, Vite 8, TypeScript, Canvas, Web Worker, Web Bluetooth |
| 백엔드 | FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 17, APScheduler |
| 얼굴·이미지 | MediaPipe, OpenCV, Gemini 이미지 편집 |
| 인증 | Google OAuth, PyJWT |
| 하드웨어 | Arduino UNO R4 WiFi, FDC2112 Moisture click |
| 실행 | Docker (백엔드), 로컬 실행 |

```
frontend/   React 앱
backend/    FastAPI 서버, 분석·추천 로직, 정적 에셋 (헤어·메이크업)
hardware/   Arduino 수분 센서 펌웨어
docs/       기능별 문서
```

## 실행

```sh
# 백엔드 (PostgreSQL 실행 중이어야 함)
cd backend && cp .env.example .env && docker compose up --build   # http://localhost:8000/api/docs

# 프론트엔드
cd frontend && pnpm install && pnpm dev                           # http://localhost:5173
```

처음 설치·DB 생성·문제 해결은 [docs/setup.md](docs/setup.md), 전체 문서 목록은 [docs/README.md](docs/README.md)
