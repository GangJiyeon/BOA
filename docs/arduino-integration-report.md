# Arduino 사전 연동 구현 보고서 (2026-10-22)

## 최신 사용자 코드 통합 결과

이번 산출물은 사용자 커밋 `e9db010f5f75f3c58834dd1a5eada499294c991f`의 ZIP 기준입니다. BOA-current.zip과 BOA-current(1).zip은 SHA-256이 동일했습니다. 초기 GitHub 기준 패치를 그대로 전달하지 않고 최신 코드 위에서 재통합했습니다.

CosmeticPreview의 충돌 두 곳을 수동으로 해결하여 최신 폼 클래스, 수분 입력 접기 UI, 분석 시작 버튼, 개발 도구 위치를 보존했습니다. 기존 파일 중 변경은 config.py/main.py/CosmeticPreview.tsx/HomePage.tsx 네 파일뿐입니다. 나머지 기존 파일(추천 알고리즘, CSS, 최신 daily-care 기능 포함)은 업로드 원본과 동일합니다.

통합본 검증: **백엔드 unittest 179개 통과**, TypeScript/Vite 빌드 통과, moisture 테스트 및 API client 16개 검사 통과. 최초 테스트 명령은 루트에서 실행해 테스트 디렉터리를 찾지 못했으며 backend에서 재실행해 정상 통과했습니다. 하드웨어/화면 자동검증 제한은 아래와 같습니다. 이번 턴에서는 이미 확인된 환경 제한을 재시도하지 않았습니다.

아래 GitHub 상태와 165개 테스트 기록은 **초기 구현 시점 기록**입니다. 이번 적용 기준은 위 사용자 커밋입니다. 사용자 ZIP에는 Git 객체 이력이 없어 로컬 검증 저장소의 base는 별도 snapshot 커밋입니다. 따라서 그 저장소 이력을 사용자에게 bundle로 이식하지 않고 e9db010 파일에 직접 적용 가능한 diff를 제공합니다.

## 초기 GitHub 기준 코드와 불일치

- 기본 브랜치 main: `b3c10c9e44f7448c4c9ae36a1614bbcac574fc05`.
- 기존 추천 브랜치: `88fb279fca668e1b68127de4dd7c2f98c3f12b8f`. main에 포함되어 있고 2커밋 뒤입니다.
- frontend-scaffold: `fab6877`, main에 포함되어 있고 1커밋 뒤입니다.
- 새로운 `feature/arduino-moisture-integration`을 main에서 분기했습니다. 기존 작업 브랜치/팀원 브랜치는 수정하지 않았습니다.
- 새로 clone한 작업 폴더는 변경 없음 상태였고 AGENTS.md는 없었습니다.
- 실제 최신 프론트는 HomePage의 hash navigation, 숨겨진 채 유지되는 CosmeticPreview입니다. 따라서 숨김만으로 BLE가 종료되지 않으며 active prop으로 센서 패널을 unmount하도록 연결했습니다.
- 실제 분석 흐름: CosmeticPreview → analyzeSkinPhoto → `/skin/analyses/debug` → SkinAnalysis/SkinScore 저장 → 응답 scores → cosmetic preview API. 이 경로는 그대로 유지합니다.
- 기존 센서 함수는 0..1023 ADC를 점수로 바꾸는 구형 계약입니다. FDC2112의 12-bit count와 호환되지 않습니다. 새 기능은 이 함수를 호출하지 않습니다. 기존 외부 클라이언트 호환성을 위해 함수 자체는 변경하지 않았습니다.
- 실제 마이그레이션에는 hair/cosmetic merge head `e0710a1b2c3d`가 있습니다. 예전 d0610a1b2c3d 설명을 기준으로 DB를 변경하지 않았습니다.
- 실제 docker-compose.yml은 PostgreSQL 컨테이너를 생성하지 않고 호스트 5432를 사용합니다.
- 기존 BLE/Arduino 구현은 없었습니다.
- 첨부 ERD는 설계 자료이며 첨부 SQLite는 cosmetics/formulas/observations 등 수집 카탈로그 구조입니다. 실제 PostgreSQL ORM과 동일한 DB가 아니므로 읽기만 했고 수정/적재하지 않았습니다.

## 파일과 역할

| 파일 | 역할 |
|---|---|
| hardware/arduino/moisture_sensor/moisture_sensor.ino | IDE 진입점, SIM/실제 모드, 500ms 송신, 시리얼/재시도 |
| hardware/arduino/moisture_sensor/Fdc2112.h | Wire1 주소·ID 검사, 설정 읽기 검증, CH0 및 오류 읽기 |
| hardware/arduino/moisture_sensor/MoistureBle.h | BLE 서비스/특성, 12바이트 패킷 인코딩 |
| frontend/src/moisture/protocol.ts | 공통 측정 모델, 엄격한 패킷 디코더 |
| frontend/src/moisture/adapters.ts | BLE/Mock 공통 인터페이스, 중복 연결·취소·리스너 정리 |
| frontend/src/hooks/useMoisture.ts | React 상태/수신/오류 및 unmount 정리 |
| frontend/src/components/MoisturePanel.tsx | 연결/종료/가상 표시/수신 시각/지연/서버 전달 UI |
| frontend/src/api/moisture.ts | 기존 API client를 사용하는 HTTP 검증 요청 |
| frontend/src/components/CosmeticPreview.tsx | 피부 흐름에 패널 추가, 원시값 직접 점수 입력 방지 안내 |
| frontend/src/pages/HomePage.tsx | 활성 화면 상태 전달; 기존 분석 흐름 보존 |
| backend/app/schemas/moisture.py | 출처/상태/원시값/시간 검증 및 응답 |
| backend/app/api/routes/moisture.py | 무저장 검증 API, 분석 ID 존재 확인 |
| backend/app/core/config.py | 가상 측정 수신 기본 금지 설정 |
| backend/app/main.py | 새 라우터 등록 |
| backend/tests/test_moisture.py | 범위·형식·가상값 차단·분석 연결·추천 불변성 |
| frontend/scripts/test-moisture.mjs | 패킷·BLE 대역·연결 취소·Mock·HTTP payload 검증 |
| docs/moisture-protocol.md | 송수신 계약과 공식 근거 |
| docs/arduino-integration-guide.md | 초보자용 Windows/IDE/배선/현장 절차 |
| docs/arduino-integration-report.md | 이 보고서 |

## 검증 결과

- 기존 백엔드 159개, 신규 포함 **165개 unittest 통과**. SQLite 격리 DB를 사용하며 실제 사용자 DB에 연결/수정하지 않았습니다.
- 프론트 `pnpm build`: TypeScript + Vite 통과.
- `node scripts/test-api-client.mjs`: 기존 16개 검사 통과.
- `node scripts/test-moisture.mjs`: 정상/비정상 패킷, 출처, 중복 연결, 구독 정리, 재연결, 연결 선택 중 취소, 권한 오류, 미지원 환경, Mock 운영 차단, API payload 통과. BLE 장치는 대역입니다.
- lint: 오류 없음. 신규 lifecycle 효과 관련 경고 2건(현재 adapter를 cleanup에서 정리, 분석/연결 변경 시 진행 요청 취소와 메시지 초기화)은 의도된 동작입니다.
- git diff --check 통과.
- 처음 TypeScript 검사는 parameter property 문법 때문에 실패했으며 프로젝트의 erasableSyntaxOnly에 맞게 수정 후 빌드 통과.
- 실제 화면 자동검증은 Chromium 미설치 및 다운로드 파일 오류로 실행하지 못했습니다. Mock 데이터 생성/상태와 API payload는 자동검증했지만 DOM 표시/레이아웃/클릭→실제 HTTP 통합은 현장 확인이 필요합니다.
- Arduino CLI 1.5.2-rc.1 실행 확인. core index 다운로드가 network unreachable로 실패하여 보드 코어 설치와 컴파일은 수행하지 못했습니다. 코어 버전은 검증되지 않았습니다.
- ArduinoBLE 공식 메타데이터 2.1.0에서 UNO R4 WiFi 지원을 확인했습니다. 실제 설치/컴파일 조합 검증과 연결 모듈 펌웨어 버전 기록은 현장 필요.
- 실물 배선, I²C, 센서 반응, BLE 무선 연결, 보정 정확도, Windows 실제 브라우저는 미검증.

## 현장 완료 조건과 남은 범위

1. 브라우저 Mock 표시와 API 200.
2. Arduino IDE Verify 후 SIM 업로드, SIM BLE 표시와 API 200.
3. 전원을 끄고 Qwiic 3.3V 배선 확인.
4. BOA_SIMULATION=0 Verify/업로드 → ID·레지스터 검사 성공.
5. raw 변화, 오류/전원 해제/재연결, API ble_sensor 확인.

기존 추천 계산/DB/스코어는 변경하지 않았습니다. 원시값은 화면 메모리에 있고 서버는 수신 검증 응답만 반환합니다. 분석 ID 연결은 요청 단위의 존재 확인이며 영구 보관·소유권 검증을 제공하지 않습니다. 보정 데이터 수집·보정 모델·권한을 갖춘 영구 보관은 별도 범위입니다. 물리 측정값의 신뢰성은 전송 source 문자열만으로 인증되지 않습니다.

## Git 전달 상태

GitHub 플러그인의 tree 생성 요청이 403 Resource not accessible by integration으로 거부되었습니다. 원격 신규 브랜치/커밋/PR 생성은 하지 못했고 main/기존 원격 브랜치는 변경되지 않았습니다. 최신 사용자 코드 기준 패치로 전달합니다. 사용자 PC에서는 별도 worktree 브랜치에 적용하고 로컬 커밋합니다.
