#pragma once
#include <ArduinoBLE.h>

class MoistureBle {
 public:
  BLEService service{"98b10000-e8f2-537e-4f6c-d104768a1214"};
  BLECharacteristic measurement{"98b10001-e8f2-537e-4f6c-d104768a1214", BLERead | BLENotify, 12, true};
  bool begin(bool simulation) {
    if (!BLE.begin()) return false;
    BLE.setLocalName(simulation ? "BOA-Moisture-SIM" : "BOA-Moisture");
    BLE.setAdvertisedService(service);
    service.addCharacteristic(measurement); BLE.addService(service);
    publish(simulation, 2, 0xFFFF, 0, millis());
    BLE.advertise(); return true;
  }
  void poll() { BLE.poll(); }
  void publish(bool simulation, uint8_t status, uint16_t raw, uint16_t sequence, uint32_t uptime) {
    uint8_t data[12] = {1, uint8_t(simulation), status, 0};
    data[4] = uint8_t(raw); data[5] = uint8_t(raw >> 8);
    data[6] = uint8_t(sequence); data[7] = uint8_t(sequence >> 8);
    for (uint8_t i=0; i<4; ++i) data[8+i] = uint8_t(uptime >> (8*i));
    measurement.writeValue(data, sizeof(data));
  }
};
