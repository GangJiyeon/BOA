# Arduino 피부 수분 측정기 현장 연결 가이드

## 이번 버전의 범위

원시값 수신 → 화면 표시 → FastAPI 입력 검증까지 구현했습니다. **피부 수분 % 측정기 또는 보정 완료 제품이 아닙니다.** 원시값을 기존 수분 점수 입력란에 넣지 마세요. 사진 분석과 추천은 기존대로 동작하며 센서값은 점수를 덮어쓰지 않습니다.

`POST /api/skin/moisture/validate`는 요청 단위의 검증/수신 확인입니다. 분석 ID가 있으면 DB에서 존재를 확인하지만 원시값을 DB에 저장하지 않습니다. 새 테이블·마이그레이션은 없습니다. 새로고침·메뉴 이동·계정 세션 변경 시 측정을 새로 시작합니다. 영구 보관, 분석 소유자 권한 및 보정 모델은 후속 작업입니다.

## 1. 준비물과 Git

- 정품 UNO R4 **WiFi**, MIKROE-3084 Moisture click (FDC2112), USB-C **데이터** 케이블
- Bluetooth LE가 가능한 Windows 노트북, Chrome 또는 Edge
- Qwiic JST SH 4핀 1.0mm → 개별선 브레이크아웃 케이블, 센서 헤더에 맞는 점퍼선
- 헤더가 납땜되어 있지 않다면 납땜 도구/담당자. 손으로 접촉시키는 임시 배선은 피합니다.
- 전압 확인용 멀티미터 권장

이번 전달본은 사용자가 올린 `BOA-current.zip`의 `e9db010f5f75f3c58834dd1a5eada499294c991f`를 기준으로 합친 패치입니다. **처음 전달한 bundle/패치는 사용하지 않습니다.** 기존 작업 폴더 옆에 별도 폴더를 만들므로 기존 frontend-scaffold 브랜치와 작업 폴더를 보존합니다.

ZIP을 바탕화면 `BOA-arduino-merged` 폴더에 풀었다는 기준입니다. PowerShell에서 각 명령이 성공한 뒤 다음 명령으로 진행하세요.

```powershell
cd C:\Users\USER\Desktop\BOA-git
git rev-parse HEAD
git status --short
```

HEAD가 위 e9db010 전체 SHA와 같고, 변경은 이전에 확인한 untracked `tatus --short --branch`뿐인 상태에서 진행합니다. 새 변경이 있으면 중단하고 먼저 확인합니다.

```powershell
git apply --check "$env:USERPROFILE\Desktop\BOA-arduino-merged\arduino-integration.patch"
git worktree add -b feature/arduino-moisture-integration ..\BOA-arduino HEAD
git -C ..\BOA-arduino apply --index "$env:USERPROFILE\Desktop\BOA-arduino-merged\arduino-integration.patch"
git -C ..\BOA-arduino commit -m "Integrate Arduino moisture with current frontend"
```

`apply --check`는 적용 가능 여부만 확인하며 성공하면 아무 출력이 없을 수 있습니다. 동일 브랜치나 BOA-arduino 폴더가 이미 있으면 덮어쓰지 말고 중단하세요. 실제 적용은 새 worktree에만 합니다. 마지막 커밋 SHA는 PC에서 새로 생성됩니다. ZIP/패치 파일 자체를 Git에 추가할 필요는 없습니다.

GitHub 쓰기 권한 문제로 원격 브랜치와 PR은 아직 없습니다. 나중에 본인 계정으로 새 폴더에서 `git push -u origin feature/arduino-moisture-integration`을 실행할 수 있습니다.

## 2. 센서 없이 소프트웨어 확인

기존 개발 환경의 `.env`는 새 worktree에 자동 복사되지 않습니다. 기존 backend `.env`를 새 backend에 **로컬로만** 복사하고 Git에 추가하지 마세요. 기존 DB를 그대로 사용합니다. DB 초기화/시드 재적재는 하지 않습니다.

브라우저 Mock 또는 보드 SIM을 서버까지 시험할 때만 `backend/.env`에 다음 줄을 추가합니다.

```dotenv
MOISTURE_ALLOW_SIMULATION=true
```

운영 환경은 생략하거나 `false`로 두세요. 프론트 Mock 버튼은 Vite 개발 모드에서만 나타납니다. 서버는 기본값으로 mock/ble_simulation을 403 거부합니다.

Docker Desktop을 켠 뒤 새 PowerShell 창:

```powershell
cd C:\Users\USER\Desktop\BOA-arduino\backend
docker compose up --build -d
docker compose logs --tail 50 api
```

경로는 실제 worktree 위치에 맞추세요. 현재 compose는 **API만** 실행하고 Windows 호스트의 PostgreSQL 5432에 연결합니다. 기존 DB가 다른 방식으로 구동된다면 기존의 정상 연결 설정을 유지하세요. `.env`의 DATABASE_URL보다 compose의 environment 설정이 우선합니다.

다른 PowerShell 창(Node 24 / pnpm):

```powershell
cd C:\Users\USER\Desktop\BOA-arduino\frontend
pnpm install --frozen-lockfile
pnpm dev
```

1. `http://localhost:5173/#/skin` → **개발용 Mock 시작** 클릭.
2. `가상 데이터 · 실제 측정 아님: 1100…` 및 수신 시각이 갱신되는지 확인.
3. **현재 측정값 서버 전달 확인** → `서버 검증 완료 … DB 저장/점수 반영 없음` 확인.
4. **측정 종료** → `수신한 측정값이 없습니다.` 확인.
5. 다시 시작하고 다른 메뉴로 이동했다 돌아오면 종료된 상태인지 확인.
6. 사진 분석이 성공한 뒤 서버 전달을 누르면 `분석 #번호 연결 확인`이 표시됩니다. 사진 없이도 수신 확인은 가능합니다.

## 3. Arduino IDE와 첫 업로드 (센서 없이)

1. [Arduino Software](https://www.arduino.cc/en/software/)에서 IDE 2 설치.
2. USB-C로 보드 연결. IDE 왼쪽 **Boards Manager / 보드 매니저**에서 `Arduino UNO R4 Boards` 검색 → 설치. 설치된 버전을 현장 기록에 적으세요.
3. **Tools → Board → Arduino UNO R4 Boards → Arduino UNO R4 WiFi** 선택. Minima가 아닙니다.
4. **Tools → Port**에서 연결한 보드의 COM 포트 선택. 나타나지 않으면 데이터 케이블/USB 포트를 확인.
5. 왼쪽 **Library Manager / 라이브러리 매니저** → `ArduinoBLE` (Arduino 제작) 설치. 준비 시 공식 메타데이터 버전은 **2.1.0**이며 의존성도 함께 설치합니다. `Wire`는 보드 패키지에 포함됩니다.
6. **File → Open** → `hardware/arduino/moisture_sensor/moisture_sensor.ino` 열기. 두 `.h` 파일은 같은 폴더에 있어야 합니다.
7. `#define BOA_SIMULATION 1`을 유지하고 상단 **✓ Verify / 확인** 클릭. 컴파일 오류가 없어야 다음으로 진행합니다.
8. **→ Upload / 업로드** 클릭. 완료되면 **Tools → Serial Monitor** → **115200 baud** 선택.
9. 필요시 보드 RESET 버튼을 한 번 누릅니다. 예상 출력:

```text
BOA SIMULATION - NOT SKIN DATA
BLE advertising
SIM seq=0 status=0 raw=1100
SIM seq=1 status=0 raw=1101
```

BLE 초기화가 실패하면 시리얼 모니터를 닫고 **Tools → Firmware Updater**에서 UNO R4 WiFi 연결 모듈 펌웨어를 갱신한 뒤 이 스케치를 다시 업로드합니다. 공식 절차: https://support.arduino.cc/hc/en-us/articles/9670986058780

## 4. BLE 통신만 먼저 확인

1. Windows Bluetooth 켜기. 다른 BLE 앱이 보드에 연결되어 있으면 해제.
2. BOA에서 Mock이 실행 중이면 **측정 종료**.
3. **측정기 연결 / 재연결** 클릭 → 브라우저 장치 선택창에서 `BOA-Moisture-SIM` 선택 → 연결.
4. 시리얼의 `BLE connected`, 웹의 `연결됨`, **가상 데이터** 표시를 확인.
5. 서버 전달 버튼으로 SIM 수신도 확인. Windows 설정에서 페어링만 하는 것으로는 구독이 시작되지 않습니다.
6. 보드 전원을 끄면 웹 연결 해제/값 초기화를 확인. 전원을 다시 켜고 연결 버튼으로 재선택합니다. 자동 재접속은 하지 않습니다.

## 5. 전원을 끄고 실제 센서 배선

**USB를 뽑은 상태에서 배선하세요. 기본 경로는 Qwiic 3.3V/Wire1입니다. A4/A5 또는 일반 SDA/SCL의 5V 버스를 센서에 직접 연결하지 마세요.** Qwiic 케이블이 없으면 현장에서 즉흥적으로 대체하지 말고, 양방향 I²C 레벨 변환 회로를 별도로 검증한 후 코드의 버스 선택까지 수정해야 합니다. 이 버전은 Wire1 전용입니다.

센서 **보드의 인쇄 라벨**을 기준으로 연결합니다. 커넥터를 보는 방향에 따라 좌우가 뒤집히므로 선 색/사진 방향만으로 연결하지 않습니다.

| UNO R4 WiFi Qwiic 신호 | Moisture click mikroBUS 헤더 라벨 |
|---|---|
| 3.3V | +3.3V |
| GND | GND (공통 접지) |
| SDA | SDA |
| SCL | SCL |

- 센서의 `+5V` 핀에는 연결하지 않습니다.
- `INT`는 이 코드에서 미사용(상태 레지스터 polling). 다른 헤더 핀도 연결하지 않습니다.
- 회로도 v100에서 SD와 CLKIN은 보드 내부 GND에 연결되어 있습니다. 별도 Arduino 5V GPIO를 연결하지 않습니다.
- `ADDR SEL` 점퍼가 선택한 주소는 0x2A 또는 0x2B입니다. 코드는 두 주소에서 제조사/장치 ID를 확인하므로 점퍼를 옮길 필요가 없습니다.
- 실제 PCB가 MIKROE-3084/v100과 다르거나 라벨이 불명확하면 전원을 넣기 전에 해당 리비전의 회로도를 다시 확인하세요.
- 케이블만 보드에 연결한 상태에서 3.3V/GND를 확인한 뒤 전원을 빼고 센서를 연결하는 순서가 좋습니다.

근거: [Moisture click 공식 회로도](https://download.mikroe.com/documents/add-on-boards/click/moisture/moisture-click-schematic-v100.pdf), [UNO R4 WiFi 공식 핀맵](https://docs.arduino.cc/resources/pinouts/ABX00087-full-pinout.pdf), [Qwiic 설명](https://support.arduino.cc/hc/en-us/articles/27742264847260-About-Qwiic).

## 6. 실제 센서 업로드와 확인

1. 배선 확인 후 USB 연결.
2. 스케치에서 `#define BOA_SIMULATION 0`으로 변경 → **✓ 확인 → → 업로드**.
3. 시리얼 모니터 115200에서 다음 형태를 확인:

```text
BOA FDC2112 RAW - UNCALIBRATED
FDC2112 ready address=0x2A
BLE advertising
SENSOR seq=0 status=0 raw=<0~4095 정수>
```

0x2B도 정상 주소입니다. `ready`는 ID 및 설정 레지스터 읽기 확인이며 피부 측정 정확도를 뜻하지 않습니다.

4. BOA에서 **측정 종료 → 측정기 연결 / 재연결 → BOA-Moisture** 선택.
5. `센서 원시값`, `status=valid`, 수신 시각 갱신 확인. SIM/Mock 표시가 남아 있으면 실제 센서 확인이 아닙니다.
6. 현재 값 서버 전달 → 개발자 도구 **F12 → Network → moisture/validate**의 HTTP 200과 요청 출처 `ble_sensor` 확인.
7. 같은 대상에 반복 접촉/비접촉하며 원시값 변화를 기록합니다. 접촉 압력/위치/시간을 일정하게 하고 숫자의 방향이나 임계값으로 건성·지성을 판정하지 않습니다.

## 7. 오류별 점검

| 증상 | 점검 |
|---|---|
| COM 포트 없음 | USB 데이터 케이블, 다른 USB 포트, WiFi 보드 선택 |
| FDC2112 init failed | 전원 끈 뒤 3.3V/GND/SDA/SCL, Qwiic 포트, 센서 모델 확인. 5초마다 재시도 |
| status=1 / raw=65535 | I²C 실패 또는 watchdog/진폭 경고. 무효값이며 서버 JSON은 null. 배선·센서 진동 조건 확인 |
| status=2 | 새 변환 없음. 계속되면 전원/설정 확인 |
| raw가 0/4095에 고정 | 숫자 범위만 정상일 수 있음. 접촉 상태, gain/offset/drive 설정 검토. 측정 성공으로 간주하지 않음 |
| BLE init failed | ArduinoBLE와 보드 패키지 버전, 연결 모듈 Firmware Updater 확인 후 재업로드 |
| 장치 목록 없음 | 보드 광고 출력, OS Bluetooth, 다른 앱 연결, 올바른 서비스 UUID. Chrome/Edge localhost 사용 |
| 선택 취소/권한 거부 | 다시 연결 버튼 클릭. 사이트 Bluetooth 권한 확인 |
| 수신 지연 | 마지막 데이터가 3초 이상 오래되면 서버 전송 차단. 보드 전원/거리 확인 후 재연결 |
| HTTP 403 | 가상값 서버 전송 시 MOISTURE_ALLOW_SIMULATION=true 설정 후 API 컨테이너 재생성 |
| HTTP 404 | 현재 분석 ID가 DB에 없거나 구버전 API 실행 중. 서버 재시작/분석 재실행 |
| HTTP 422 | 패킷 버전·범위·시간대·source/status/raw 일치 확인 |

## 8. 개발 검증 명령과 현장 기록

```powershell
cd frontend
pnpm build
node scripts/test-api-client.mjs
node scripts/test-moisture.mjs
cd ..\backend
docker compose exec api python -m unittest discover -s tests
```

Arduino CLI가 있는 PC에서는:

```powershell
arduino-cli core update-index
arduino-cli core install arduino:renesas_uno
arduino-cli lib install "ArduinoBLE@2.1.0"
arduino-cli compile --fqbn arduino:renesas_uno:unor4wifi hardware/arduino/moisture_sensor
```

실제 모드와 SIM 모드 각각 컴파일/업로드하세요. 원격 개발 환경에서는 CLI 실행까지만 확인했고 보드 인덱스 다운로드가 네트워크 제한으로 실패했습니다. **실제 보드 컴파일·업로드·센서·무선 동작은 미검증입니다.**

현장 기록: IDE 버전 / Arduino UNO R4 Boards 버전 / ArduinoBLE 버전 / 연결 모듈 펌웨어 버전 / PCB 리비전 / 발견 주소 / SIM 성공 여부 / 실제 원시값 변화 / 연결 해제·재연결 / API 응답을 남깁니다.
