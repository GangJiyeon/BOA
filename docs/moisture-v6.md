# BOA 수분 측정 통합 v6

## 적용
1. 기존 BOA-git 폴더를 백업한 뒤 이 ZIP의 frontend, hardware, docs 폴더를
   BOA-git에 합쳐서 같은 이름의 파일을 덮어씁니다. 다른 프로젝트 파일은 삭제하지 않습니다.
2. hardware/arduino/moisture_sensor/moisture_sensor.ino를 Arduino IDE에서 열고
   UNO R4 WiFi / COM5로 업로드합니다. 업로드는 한 번입니다. ArduinoBLE를 계속 사용합니다.
3. PowerShell에서 아래 명령으로 기존 프론트를 실행합니다.

```powershell
cd C:\Users\USER\Desktop\BOA-git\frontend
npm run dev
```

4. localhost의 Chrome/Edge에서 화장품 추천 화면의 수분 측정기를 엽니다.
   기존 연결을 종료하고 재연결하세요. 새 보정 특성이 안 보이면 브라우저를 재시작하고
   Bluetooth 장치 권한을 제거한 뒤 다시 연결하세요.
5. 측정기 연결 → 손을 떼고 기준값 보정 → 보정 완료 후 손가락 접촉 → 현재값 기록.

추가 npm 패키지/DB 마이그레이션 없음. 측정 패널의 BLE 통신 자체에는 Docker가 필요하지 않습니다.
서버 전달 확인 및 프로젝트의 다른 API 기능에는 기존 백엔드가 필요합니다.
Git 커밋/푸시는 수행하지 않았습니다.

## 동작
- 기존 moisture_sensor에 직접 적용. Qwiic Wire1 및 제조사 참고 초기 설정 유지.
- 전원 켜기/센서 자동 재연결 시 임의 보정하지 않음. 화면에서 명시적으로 보정.
- 보정 대기 3초간 BLE polling 유지. 보정 중 손을 떼어야 합니다.
- 상대 % = max(0, 기준 평균 - 현재 평균) * 100 / 기준 평균, 정수 표시.
- 제조사처럼 16회 레지스터 읽기의 평균. 모두 서로 다른 변환이라는 의미는 아닙니다.
- 보정 중 0/경고/I2C 실패는 거부. 실패하면 보정 버튼으로 다시 시작.
- 기준값 부근/변화 감지는 신호 변화 안내이며, 접촉을 확정하는 별도 센서는 없습니다.
- 진폭 경고는 참고 %를 표시하되 기록을 막음. 통신 오류는 %를 표시하지 않음.
- 마지막 수신에서 3초 초과 시 이전 %를 숨기고 새 기록을 막음.
- 현재값 기록은 화면 내 순간값 1개 보관. DB 저장 아님. 재보정/연결 종료/화면 이탈로 초기화.
- 절대 피부 수분 함량, 건성/지성, 임상 기준 및 추천 점수는 산출하지 않음.
- 시리얼 명령도 유지: c=보정, r=센서 재초기화 후 보정. 115200 baud.
- 사용자 화면의 Mock 버튼 제거. 내부 Mock 어댑터/테스트는 유지.

## 호환성
- 기존 서비스와 0001 characteristic은 12바이트 원시값 v1 유지.
- 0002 characteristic은 20바이트 v2; 0003은 1바이트 보정 명령(1).
- 새 프론트는 v2를 우선 사용하고 구버전 센서에는 v1 원시값 표시로 대체.
- 백엔드 요청은 기존 v1 원시값 스키마로 명시적으로 변환하므로 상대 %가 점수에 섞이지 않음.

v2: 바이트 0=2, 1=simulation(0/1), 2=status(0 정상/1 오류/2 준비 안 됨),
3=calibration(0 미보정/1 진행 중/2 완료/3 실패), 4~5=정상 raw 또는 65535,
6~7=순번, 8~11=uptime, 12~13=기준값, 14~15=참고 평균,
16~17=상대 %, 18~19=DATA 상위 오류 비트 OR. 모든 다바이트 숫자는 little endian.
기준값/평균/%의 없음 값은 65535. 진폭 경고 시 status=1, raw=65535,
평균/%는 참고로 존재 가능. watchdog 등 다른 오류 시 % 없음.
UUID 공통 suffix: -e8f2-537e-4f6c-d104768a1214. prefix는 98b10000(서비스),
98b10001(v1), 98b10002(v2), 98b10003(명령).

## 검증
- npm run build 통과.
- node frontend/scripts/test-moisture.mjs (frontend에서 실행: node scripts/test-moisture.mjs) 통과.
  v1/v2 디코딩, 잘못된 값 거부, 구버전 대체, 보정 쓰기, 연결 취소,
  disconnect, Mock 제한, 기존 서버 스키마 변환 확인.
- C++ 호스트 모의 테스트 통과: BLE 보정 명령, 보정/오류/복구 상태,
  507→293의 42%, 진폭 경고와 v1/v2 패킷 구분, 0/경고 보정 거부.
- UNO R4 타깃 컴파일/실물 업로드 미실행.
- 브라우저 실행 파일 다운로드 실패로 브라우저 클릭 테스트 미실행.

공식 원본: https://github.com/MikroElektronika/Moisture_click
원본 라이선스: hardware/arduino/moisture_sensor/NOTICE.txt
