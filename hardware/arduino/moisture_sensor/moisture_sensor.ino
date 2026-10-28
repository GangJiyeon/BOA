#include "Fdc2112.h"
#include "MoistureBle.h"
#include "MoistureScore60.h"

// Real sensor mode. Set to 1 explicitly for a sensor-free simulation.
#ifndef BOA_SIMULATION
#define BOA_SIMULATION 0
#endif
Fdc2112 sensor;
MoistureBle transport;
bool sensorReady = false, bleReady = false;
uint32_t lastSample = 0, lastRetry = 0;
uint16_t sequence = 0;
bool calibrationPending = false, calibrationFailed = false;
uint32_t calibrationStart = 0, calibrationSum = 0;
uint16_t calibrationMin = 4095, calibrationMax = 0;
uint16_t calibrationFirst = 0, calibrationLast = 0;
uint32_t calibrationLastTime = 0;
uint8_t calibrationCount = 0;
// Experimental repeatability gate, not a clinical calibration specification.
const uint8_t CALIBRATION_SAMPLES = 20;

void onConnect(BLEDevice) { Serial.println("BLE connected"); }
void onDisconnect(BLEDevice) { Serial.println("BLE disconnected; advertising"); BLE.advertise(); }
void scheduleCalibration() {
  sensor.calibrated = false; calibrationFailed = false;
  calibrationPending = true; calibrationStart = millis();
  calibrationSum = 0; calibrationCount = 0; calibrationMin = 4095; calibrationMax = 0;
  calibrationFirst = 0; calibrationLast = 0; calibrationLastTime = 0;
  Serial.println("CALIBRATION: keep skin and hands away from sensor; starting in 3 seconds.");
}
void initializeSensor() {
  calibrationPending = false;
  sensorReady = sensor.begin();
  Serial.print(sensorReady ? "FDC2112 ready address=0x" : "FDC2112 init failed address=0x");
  Serial.println(sensor.address, HEX);
  calibrationFailed = false;
  Serial.println("Keep sensor in air and press Calibrate in the app (or send c).");
}
void handleSerial() {
  while (Serial.available()) {
    const char command = char(Serial.read());
    if (BOA_SIMULATION) continue;
    if (command == 'r' || command == 'R') { initializeSensor(); if (sensorReady) scheduleCalibration(); }
    else if ((command == 'c' || command == 'C') && sensorReady) scheduleCalibration();
  }
}
void setup() {
  Serial.begin(115200);
  const uint32_t start = millis();
  while (!Serial && millis() - start < 3000) {}
  Serial.println("BOA firmware: moisture-score60-sqrt-v17");
  Serial.println("Serial commands: c=air calibration, r=initialize and calibrate");
  Serial.println(BOA_SIMULATION ? "BOA SIMULATION - NOT SKIN DATA" : "BOA FDC2112 RAW - UNCALIBRATED");
  if (!BOA_SIMULATION) initializeSensor();
  bleReady = transport.begin(BOA_SIMULATION);
  if (bleReady) {
    BLE.setEventHandler(BLEConnected, onConnect);
    BLE.setEventHandler(BLEDisconnected, onDisconnect);
    Serial.println("BLE advertising");
  } else Serial.println("BLE init failed; check connectivity firmware and reset");
}
void loop() {
  if (bleReady) transport.poll();
  handleSerial();
  if (bleReady && transport.takeCalibrationRequest() && !BOA_SIMULATION && sensorReady && !calibrationPending) scheduleCalibration();
  const uint32_t now = millis();
  if (!BOA_SIMULATION && !sensorReady && now - lastRetry >= 5000) {
    lastRetry = now; initializeSensor();
  }
  if (now - lastSample < 100) return;
  lastSample = now;
  if (calibrationPending && sensorReady && millis() - calibrationStart >= 3000) {
    uint16_t calibrationRaw;
    uint8_t outcome = sensor.sample(calibrationRaw);
    if (outcome == 0 && calibrationRaw > 0) {
      // Never combine disconnected time fragments into one air reference.
      if (calibrationCount && now - calibrationLastTime > 350) {
        calibrationSum = 0; calibrationCount = 0; calibrationMin = 4095; calibrationMax = 0;
        calibrationFirst = 0; calibrationLast = 0;
      }
      calibrationLastTime = now;
      if (calibrationCount < 5) calibrationFirst += calibrationRaw;
      if (calibrationCount >= CALIBRATION_SAMPLES - 5) calibrationLast += calibrationRaw;
      calibrationSum += calibrationRaw; ++calibrationCount;
      if (calibrationRaw < calibrationMin) calibrationMin = calibrationRaw;
      if (calibrationRaw > calibrationMax) calibrationMax = calibrationRaw;
      if (calibrationCount >= CALIBRATION_SAMPLES) {
        uint16_t mean = (calibrationSum + calibrationCount / 2) / calibrationCount;
        const uint16_t profileScale = sensor.referenceDivider / 11;
        uint16_t allowed = mean / 50; if (allowed < 4 * profileScale) allowed = 4 * profileScale;
        calibrationPending = false;
        uint16_t drift = calibrationFirst > calibrationLast ? calibrationFirst - calibrationLast : calibrationLast - calibrationFirst;
        calibrationFailed = calibrationMax - calibrationMin > allowed || drift > 10 * profileScale;
        Serial.print("CAL_QC range="); Serial.print(calibrationMax - calibrationMin);
        Serial.print(" first_last_sum_delta="); Serial.println(drift);
        if (!calibrationFailed) {
          sensor.baseline = mean; sensor.calibrated = true;
          Serial.print("CAL_OK baseline="); Serial.println(sensor.baseline);
        }
      }
    } else if (outcome == 1 || (outcome == 0 && calibrationRaw == 0)) {
      calibrationPending = false; calibrationFailed = true;
    }
    if (calibrationPending && millis() - calibrationStart > 8000) {
      calibrationPending = false; calibrationFailed = true;
    }
    // Do not consume a second conversion immediately after the calibration read.
    // Publish the calibration state now; normal sampling resumes next tick.
    if (bleReady) transport.publish(false, 2, 0xFFFF, sequence++, millis(),
      calibrationPending ? 1 : sensor.calibrated ? 2 : 3,
      sensor.calibrated ? sensor.baseline : 0xFFFF, 0xFFFF, 0xFFFF, 0,
      sensorReady ? sensor.referenceDivider : 0, sensor.driveCode, 0);
    return;
  }
  uint16_t raw = 0xFFFF;
  uint8_t status = calibrationPending ? 2 : 1;
  if (BOA_SIMULATION) { raw = 1100 + sequence % 40; status = 0; }
  else if (sensorReady && !calibrationPending) {
    status = sensor.sample(raw);
    if (sensor.needsReconnect()) {
      sensorReady = false; sensor.calibrated = false;
      lastRetry = now; // Wait five seconds after repeated I2C failures.
    }
  }
  const uint8_t calibration = calibrationPending ? 1 : sensor.calibrated ? 2 : calibrationFailed ? 3 : 0;
  const bool referenceOK = !BOA_SIMULATION && sensorReady && !calibrationPending && sensor.referenceAvailable;
  if (bleReady) transport.publish(BOA_SIMULATION, status, raw, sequence, now,
    calibration, sensor.calibrated ? sensor.baseline : 0xFFFF,
    !BOA_SIMULATION && sensorReady && !calibrationPending && sensor.hasData ? sensor.averageCount : 0xFFFF,
    referenceOK && sensor.calibrated ? sensor.relativePercent() : 0xFFFF,
    !calibrationPending && sensorReady ? sensor.windowFlags : 0,
    !BOA_SIMULATION && sensorReady ? sensor.referenceDivider : 0, sensor.driveCode, sensor.lastStatus);
  Serial.print(BOA_SIMULATION ? "SIM " : "SENSOR ");
  Serial.print("seq="); Serial.print(sequence++);
  Serial.print(" status="); Serial.print(status);
  Serial.print(" raw=");
  if (status == 0) Serial.print(raw); else Serial.print("NA");
  if (!BOA_SIMULATION) {
    Serial.print(" baseline=");
    if (sensor.calibrated) Serial.print(sensor.baseline); else Serial.print("NA");
    Serial.print(" drive_code="); Serial.print(sensor.driveCode);
    Serial.print(" ref_divider="); Serial.print(sensor.referenceDivider);
    Serial.print(" relative_pct=");
    if (sensorReady && !calibrationPending && sensor.calibrated && sensor.referenceAvailable)
      Serial.print(sensor.relativePercent());
    else Serial.print("NA");
    Serial.print(" capacitance_change_pct=");
    if (status == 0 && sensor.calibrated) Serial.print(sensor.capacitanceChangePercent()); else Serial.print("NA");
    Serial.print(" average_count=");
    if (sensor.referenceAvailable && !calibrationPending && sensorReady) Serial.print(sensor.averageCount); else Serial.print("NA");
    // Raw BLE samples remain authoritative; never turn an error into score zero.
    const int liveScore = status == 0 && sensorReady && sensor.calibrated && !calibrationPending
      ? BoaMoisture60::instantaneousScore(sensor.baseline,raw,sensor.referenceDivider) : -1;
    Serial.print(" instant_score60=");
    if(liveScore>=0) Serial.print(liveScore); else Serial.print("NA");
    Serial.print(" instant_level6=");
    if(liveScore>=0) Serial.print(BoaMoisture60::levelFromScore(liveScore)); else Serial.print("NA");
    Serial.print(" quality=");
    Serial.print(calibrationPending ? "calibrating" :
      !sensor.calibrated ? "uncalibrated" :
      sensor.fault == Fdc2112::AMPLITUDE_WARNING ? "amplitude_warning_reference_only" :
      status == 0 ? "no_data_warning" : "unavailable");
    Serial.print(" reason="); Serial.print(sensorReady ? sensor.faultName() : "sensor_offline");
    Serial.print(" STATUS=0x"); Serial.print(sensor.lastStatus, HEX);
    if (sensor.hasData) {
      Serial.print(" DATA=0x"); Serial.print(sensor.lastData, HEX);
      Serial.print(" diagnostic_count="); Serial.print(sensor.lastData & 0x0FFF);
    }
  }
  Serial.println();
}
