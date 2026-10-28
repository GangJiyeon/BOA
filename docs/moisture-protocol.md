# BOA moisture protocol v1

장치 이름: 실제 `BOA-Moisture`, 보드 시뮬레이션 `BOA-Moisture-SIM`.
서비스 `98b10000-e8f2-537e-4f6c-d104768a1214`, 읽기/Notify Characteristic `98b10001-e8f2-537e-4f6c-d104768a1214`.

12바이트 고정 길이, 다중 바이트는 little endian. ATT 기본 payload 범위 내입니다.

| Offset | 타입 | 의미 |
|---|---|---|
| 0 | uint8 | 버전 1 |
| 1 | uint8 | 0 실제 센서 / 1 보드 SIM; 그 외 거부 |
| 2 | uint8 | 0 valid / 1 sensor_error / 2 not_ready |
| 3 | uint8 | 예약 0 |
| 4–5 | uint16 LE | FDC2112 CH0 count 0..4095; 오류/미준비는 0xFFFF |
| 6–7 | uint16 LE | 순번; 65535 뒤 0 |
| 8–11 | uint32 LE | 장치 millis(); 재부팅 시 초기화, 약 49.7일에 wrap |

주기 500ms. 단위 `fdc2112_count`이며 %·pF·피부 점수가 아닙니다. 보드 시계는 절대 측정 시각이 아닙니다. 브라우저 `received_at`은 수신 UTC, API `server_received_at`은 서버 수신 UTC입니다. 순번은 진단용이며 영구 식별자가 아닙니다.

유효 패킷 예: `01 00 00 00 B0 04 2A 00 40 E2 01 00` → 실제 센서, raw=1200, seq=42, uptime=123456.
오류는 raw null로 변환합니다. 불명확한 버전/길이/플래그/범위를 거부하며 직전 정상값을 전송하지 않습니다.

연결 직후 구독부터 시작하고 다음 Notify를 기다립니다(과거 characteristic 값을 읽어 신규값으로 사용하지 않음). 연결 해제 시 값/리스너를 비우고, 보드는 다시 광고하며 브라우저는 사용자 클릭으로 재선택합니다. 화면 이동 시 adapter를 해제합니다. 3초 이상 새 데이터가 없으면 전송 불가입니다.

POST `/api/skin/moisture/validate`: `{analysis_id: number|null, measurement: {...}}`. 출처는 ble_sensor / ble_simulation / mock. 유효 상태만 raw 정수를 갖고 나머지는 null. 서버는 가상값을 기본 거부합니다. 응답 persisted=false, used_for_scoring=false, calibration_status=uncalibrated. 영구저장/보정 단계의 대체가 아닙니다.

## 센서 설정의 근거와 제한

드라이버는 Arduino Wire1을 직접 사용합니다. mikroSDK HAL 라이브러리를 Arduino 호환이라고 주장하거나 설치하지 않습니다. 제조사 드라이버의 시작 설정을 검토했으며 TI 데이터시트의 reserved bit 조건을 반영해 레지스터를 설정·읽기 검증합니다. CH0, 내부 기준 클럭, gain x16, offset 0x00AA, 분주 설정 0x200B입니다. 설정이 바뀌면 원시값도 달라지므로 이후 보정 데이터에 설정 버전을 함께 보관해야 합니다. 진폭/포화 및 피부 적합성은 현장에서 검증해야 합니다. 제조사 예제의 백분율 계산은 사용하지 않습니다.

공식 출처:
- https://www.ti.com/lit/ds/symlink/fdc2112.pdf (register map, FDC2112 12-bit, device ID)
- https://github.com/MikroElektronika/mikrosdk_click_v2/tree/master/clicks/moisture/lib_moisture (설정 참고; Arduino API 아님)
- https://github.com/arduino-libraries/ArduinoBLE/blob/master/library.properties (UNO R4 WiFi 지원 명시, 확인 시 2.1.0)
- https://github.com/arduino/docs-content/blob/main/content/hardware/uno/boards/uno-r4-wifi/datasheet/datasheet.md (Wire1)
- https://developer.chrome.com/docs/capabilities/bluetooth (보안 컨텍스트/사용자 제스처/GATT)
