# v11 신호 취득 개선과 외부 근거 검토

목표: UNO R4 WiFi + FDC2112 Moisture click만 사용. 한 번 피부 접촉 안에서 안정화 및 3초 표본 수집. 분리 접촉 3회를 요구하지 않는다. 완료 후 명시적인 다시 측정으로만 재시작한다.

## 외부 자료 검토 결과
- MIKROE 제품 페이지는 피부 정전용량 기반 수분 측정 용도임을 명시한다. 최신 LibStock 예제는 상대 수분 측정(relative moisture measurement)이라고 설명한다. 제조사 용도 설명은 임상적으로 검증된 절대 수분율 변환식과 동일하지 않다.
- TI FDC2x1x Rev B 식 8, gain/offset 표를 대조했다. 현재 gain16/offset170/FIN2/FREF_DIV11에서 주파수 복원식 및 (B+170)/(x+170)의 제곱 비율은 유지한다. 30 counts를 지수100으로 두는 표시 범위의 피부 생리학적 근거는 확보하지 못했다.
- TI는 gain 사용 시 상위 비트 소실을 경고한다. 현재 비율 계산은 원시값이 같은 유효 gain 구간에 있다는 조건을 갖는다. 실제 장치에서 상위 비트 alias 유무까지 검증한 것은 아니다.
- Clarys 등 2011 연구는 접촉 압력에 따른 수분 측정값 차이를 보고한다. 일정한 신호만으로 압력이 적절하다고 판정할 수는 없다. 이 보드에 해당 연구의 보정계수를 이식하지 않는다.
- Annals of Dermatology 2024 연구는 Corneometer와 conductance probe의 재현성 및 관계를 비교한다. 그 장비의 임의단위(AU)나 판정 경계는 Moisture click 표시값과 동등하지 않다.
- PNJ 학위논문 부록에도 Moisture click/공기 보정/퍼센트 구간 분류 사례가 있다. 공개된 해당 부록만으로 경계값의 검증 근거를 확인할 수 없어 채택하지 않았다.
- 현재 검토 범위에서 이 보드와 우리 설정에 바로 적용 가능한 검증된 0~100 피부 수분 변환식과 3단계 경계값을 찾지 못했다. 자료가 존재하지 않는다는 뜻은 아니다. 피지량 분류인 지성을 수분 상한 범주로 사용하지 않는다.

## 적용한 변경
- Fdc2112.h: TI 표 7-37~39의 예약 비트 요구값 반영. ERROR_CONFIG 0x3801, MUX_CONFIG 0x020F, CONFIG 0x1401. 설정은 sleep 상태에서 쓰고 CONFIG를 마지막에 써서 변환 시작.
- DRIVE_CURRENT_CH0: 기존 0x7C00에서 예약 비트를 제거한 0x7800. 유효 drive 필드15는 유지. 진폭 최적화 완료를 의미하지 않는다.
- RCOUNT 0x010F -> 0x1000. 명목 클록43.4MHz/11 기준 변환 시간 약1.1ms ->16.6ms. 변환시간을 늘려 잡음 감소를 기대하는 설계이며 실제 개선량 미측정.
- SETTLECOUNT 0x0064 ->0x0100. 명목 안정화 약0.4ms ->1.0ms. 100ms 발행 주기 내 유지.
- gain/offset/divider와 출력 프로토콜 유지. 33MHz deglitch 대역은 유지하며 현재 실측 주파수와 alias 확인 없이 최저 대역으로 변경하지 않는다.
- 설정 readback에 CONFIG/MUX/drive/error까지 추가.
- 공기 기준20표본: 범위 검사 외에 처음5개/마지막5개 합 차이10 counts 이하 검사(평균 차이2 counts). 350ms 초과 간격이면 이전 부분 구간 폐기. 평균은 버림 대신 반올림.
- 위 공기 보정 허용치는 초기 공학 설정이며 임상 기준이 아니다. 실패율/로그 확인 후 조정할 대상이다.
- 표시식과 추천 판정은 변경하지 않았다. 근거 없는 건조/보통/충분 경계값을 새로 만들지 않았다.

## 적용 순서
1. v10 또는 v10.1을 적용한 프로젝트 루트에 이 ZIP을 덮어쓴다. frontend에는 v10.1의 단일 완료 수정도 포함한다.
2. Arduino IDE에서 hardware/arduino/moisture_sensor/moisture_sensor.ino를 열고 UNO R4 WiFi와 해당 포트 선택 후 업로드한다. 세 파일은 같은 스케치이므로 한 번만 업로드한다.
3. 시리얼 모니터115200에서 BOA firmware: moisture-single-contact-v11 및 CONFIG verified=1을 확인한다. 확인 후 시리얼 모니터를 닫고 웹을 새로고침한다.
4. 웹에서 연결 후 센서 면을 피부/손에서 떼고 기준값 보정. 피부에 한 번 대고 완료될 때까지 유지한다. 다시 접촉하거나 완료 버튼을 누를 필요 없다.
5. 1회 결과와 전체 측정 로그를 내려받는다. 이 로그로 공기 잡음/표본 구간/경고/변동을 확인할 수 있다. 로그 없이 정확도 개선을 단정하지 않는다.

## 검증과 다음 판단
실제 ino를 포함한 C++ 호스트 테스트 통과: 설정값 및 readback 실패, 신선한 표본, 보정, BLE 발행, 경고, 연결 실패, 보정 드리프트 거부, 반올림, 수신 간격 초기화.
프론트 자동측정 회귀 및 DOM 통합 테스트, 빌드 검증. 실제 UNO 대상 빌드/업로드와 피부 측정은 이 환경에서 수행하지 않았다.

다음에 확인할 것: CONFIG verified, CAL_QC range/first_last_sum_delta, 실제 공기 기준, 한 번 접촉한 완료 표본과 경고 기록. 단일 접촉 내 신호 품질을 확인하는 단계이며 정확한 피부 수분 함량 검증과는 구분한다.
기존 데이터의 site=left_cheek 필드는 아직 유지되어 있다. 부위 일반화는 DB/API 호환을 포함해 별도 수정이 필요하다. 이번 패치는 모든 부위에 대한 기준을 검증한 버전이 아니다.

## 출처
https://www.ti.com/lit/ds/symlink/fdc2112.pdf
https://www.mikroe.com/moisture-click
https://libstock.mikroe.com/projects/view/3139/moisture-click
https://pubmed.ncbi.nlm.nih.gov/21338409/
https://pc.anndermatol.org/pdf/10.5021/ad.23.103
https://repository.pnj.ac.id/id/eprint/14177/2/Halaman%20Identitas%20Skripsi.pdf
