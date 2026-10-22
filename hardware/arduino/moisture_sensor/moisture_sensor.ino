#include "Fdc2112.h"
#include "MoistureBle.h"

// First upload: no sensor required. Change to 0 ONLY after checking wiring.
#ifndef BOA_SIMULATION
#define BOA_SIMULATION 1
#endif
Fdc2112 sensor;
MoistureBle transport;
bool sensorReady = false, bleReady = false;
uint32_t lastSample = 0, lastRetry = 0;
uint16_t sequence = 0;

void onConnect(BLEDevice central) { Serial.println("BLE connected"); }
void onDisconnect(BLEDevice central) { Serial.println("BLE disconnected; advertising"); BLE.advertise(); }
void initializeSensor() {
  sensorReady = sensor.begin();
  Serial.print(sensorReady ? "FDC2112 ready address=0x" : "FDC2112 init failed address=0x");
  Serial.println(sensor.address, HEX);
}
void setup() {
  Serial.begin(115200);
  const uint32_t start = millis();
  while (!Serial && millis() - start < 3000) {}
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
  const uint32_t now = millis();
  if (!BOA_SIMULATION && !sensorReady && now - lastRetry >= 5000) {
    lastRetry = now; initializeSensor();
  }
  if (now - lastSample < 500) return;
  lastSample = now;
  uint16_t raw = 0xFFFF;
  uint8_t status = 1;
  if (BOA_SIMULATION) { raw = 1100 + sequence % 40; status = 0; }
  else if (sensorReady) { status = sensor.sample(raw); if (status == 1) sensorReady = false; }
  if (bleReady) transport.publish(BOA_SIMULATION, status, raw, sequence, now);
  Serial.print(BOA_SIMULATION ? "SIM " : "SENSOR ");
  Serial.print("seq="); Serial.print(sequence++);
  Serial.print(" status="); Serial.print(status);
  Serial.print(" raw="); Serial.println(raw);
}
