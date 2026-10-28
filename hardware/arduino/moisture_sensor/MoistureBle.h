#pragma once
#include <ArduinoBLE.h>

class MoistureBle {
 public:
  BLEService service{"98b10000-e8f2-537e-4f6c-d104768a1214"};
  BLECharacteristic measurement{"98b10001-e8f2-537e-4f6c-d104768a1214", BLERead | BLENotify, 12, true};
  // v1 stays available for existing clients; v2 is a separate 20-byte value.
  BLECharacteristic reference{"98b10002-e8f2-537e-4f6c-d104768a1214", BLERead | BLENotify, 20, true};
  BLECharacteristic fresh{"98b10004-e8f2-537e-4f6c-d104768a1214", BLERead | BLENotify, 20, true};
  BLECharacteristic profiled{"98b10005-e8f2-537e-4f6c-d104768a1214", BLERead | BLENotify, 20, true};
  BLECharacteristic driven{"98b10006-e8f2-537e-4f6c-d104768a1214", BLERead | BLENotify, 20, true};
  BLECharacteristic command{"98b10003-e8f2-537e-4f6c-d104768a1214", BLEWrite, 1, true};
  bool takeCalibrationRequest() {
    uint8_t value = 0;
    return command.written() && command.readValue(value) == 1 && value == 1;
  }
  bool begin(bool simulation) {
    if (!BLE.begin()) return false;
    BLE.setLocalName(simulation ? "BOA-Moisture-SIM" : "BOA-Moisture");
    BLE.setAdvertisedService(service);
    service.addCharacteristic(measurement);
    service.addCharacteristic(reference); service.addCharacteristic(fresh); service.addCharacteristic(profiled); service.addCharacteristic(driven); service.addCharacteristic(command); BLE.addService(service);
    publish(simulation, 2, 0xFFFF, 0, millis());
    BLE.advertise(); return true;
  }
  void poll() { BLE.poll(); }
  void publish(bool simulation, uint8_t status, uint16_t raw, uint16_t sequence, uint32_t uptime,
               uint8_t calibration = 0, uint16_t baseline = 0xFFFF,
               uint16_t average = 0xFFFF, uint16_t percent = 0xFFFF, uint16_t warnings = 0,
               uint16_t verifiedDivider = 0, uint16_t driveCode = 0xFFFF, uint16_t sensorStatus = 0) {
    uint8_t data[12] = {1, uint8_t(simulation), status, 0};
    data[4] = uint8_t(raw); data[5] = uint8_t(raw >> 8);
    data[6] = uint8_t(sequence); data[7] = uint8_t(sequence >> 8);
    for (uint8_t i=0; i<4; ++i) data[8+i] = uint8_t(uptime >> (8*i));
    measurement.writeValue(data, sizeof(data));
    uint8_t extended[20];
    for (uint8_t i=0; i<12; ++i) extended[i] = data[i];
    extended[0] = 2; extended[3] = calibration;
    const uint16_t extras[] = {baseline, average, percent, warnings};
    for (uint8_t i=0; i<4; ++i) {
      extended[12+2*i] = uint8_t(extras[i]); extended[13+2*i] = uint8_t(extras[i] >> 8);
    }
    reference.writeValue(extended, sizeof(extended));
    extended[0] = 3; fresh.writeValue(extended, sizeof(extended));
    // v4 retains all error bits and reports the verified, frozen gain16 /
    // offset170 / FIN2 profile. Never infer the divider from air raw counts.
    extended[0] = 4;
    const uint16_t metadata = (warnings & 0xF000) |
      (verifiedDivider && !simulation ? (0x0400 | verifiedDivider) : 0);
    extended[18] = uint8_t(metadata); extended[19] = uint8_t(metadata >> 8);
    profiled.writeValue(extended, sizeof(extended));
    // v5 replaces the redundant percent field with fixed drive + directional
    // warning status. Baseline, raw diagnostics and all DATA error bits survive.
    extended[0] = 5;
    const uint16_t driveInfo = verifiedDivider && driveCode<=31 && !simulation
      ? uint16_t(driveCode | (sensorStatus & 0x0600)) : 0xFFFF;
    extended[16] = uint8_t(driveInfo); extended[17] = uint8_t(driveInfo >> 8);
    driven.writeValue(extended, sizeof(extended));
  }
};
