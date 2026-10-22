#pragma once
#include <Arduino.h>
#include <Wire.h>

// Wire1 only: UNO R4 WiFi's 3.3 V Qwiic bus. No 5 V GPIO used.
class Fdc2112 {
 public:
  uint8_t address = 0;
  bool begin() {
    Wire1.begin();
    Wire1.setClock(100000);
    address = 0;
    for (uint8_t candidate = 0x2A; candidate <= 0x2B; ++candidate) {
      address = candidate;
      uint16_t manufacturer, device;
      if (readWord(0x7E, manufacturer) && readWord(0x7F, device) &&
          manufacturer == 0x5449 && device == 0x3054) break;
      address = 0;
    }
    if (!address || !writeWord(0x1C, 0x8000)) return false;
    delay(10);
    // Bench starting configuration, not a skin calibration.
    // Manufacturer timing/gain/offset starting points, TI reserved bits retained.
    const uint8_t regs[] = {0x1C,0x10,0x08,0x0C,0x14,0x1E,0x19,0x1B,0x1A};
    const uint16_t values[] = {0x0600,0x0064,0x010F,0x00AA,0x200B,0x7800,0x3820,0x020F,0x1481};
    for (uint8_t i=0; i<sizeof(regs); ++i) {
      uint16_t actual;
      if (!writeWord(regs[i], values[i]) || !readWord(regs[i], actual) || actual != values[i]) return false;
    }
    return true;
  }
  // Protocol status: 0 valid, 1 error, 2 no fresh conversion.
  uint8_t sample(uint16_t &raw) {
    raw = 0xFFFF;
    uint16_t status, data;
    if (!readWord(0x18, status)) return 1;
    if (!(status & 0x0008)) return (status & 0x0E00) ? 1 : 2;
    if (!readWord(0x00, data)) return 1;
    if ((status & 0x0E00) || (data & 0x3000)) return 1;
    raw = data & 0x0FFF;
    return 0;
  }
 private:
  bool writeWord(uint8_t reg, uint16_t value) {
    Wire1.beginTransmission(address); Wire1.write(reg);
    Wire1.write(uint8_t(value >> 8)); Wire1.write(uint8_t(value));
    return Wire1.endTransmission() == 0;
  }
  bool readWord(uint8_t reg, uint16_t &value) {
    Wire1.beginTransmission(address); Wire1.write(reg);
    if (Wire1.endTransmission(false) != 0) return false;
    if (Wire1.requestFrom(address, uint8_t(2)) != 2) return false;
    value = uint16_t(Wire1.read()) << 8; value |= uint8_t(Wire1.read());
    return true;
  }
};
