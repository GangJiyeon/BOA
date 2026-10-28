#pragma once
#include <Arduino.h>
#include <Wire.h>

// Wire1 only: UNO R4 WiFi's 3.3 V Qwiic bus. No 5 V GPIO used.
class Fdc2112 {
 public:
  uint8_t address = 0;
  enum Fault { NONE, I2C_ERROR, NOT_READY, WATCHDOG, AMPLITUDE_WARNING, CONFIG_ERROR, RANGE_ERROR };
  Fault fault = NONE;
  // Keep gain and offset fixed for the existing BLE/API capacitance ratio.
  // The reference divider cancels in a ratio taken within ONE configuration.
  static constexpr uint16_t OFFSET = 170;
  uint16_t referenceDivider = 11;
  // Selected in air once at boot, then frozen through calibration and contact.
  // Do not change drive mid-contact and compare against an old air baseline.
  uint8_t driveCode = 15;
  uint8_t driveCandidatesTested = 0;
  uint16_t coarseMin = 0, coarseMax = 0;
  static bool hasHeadroom(uint16_t lo, uint16_t hi) {
    // Gain=1 reports the upper 12 bits. Account for all 16 possible hidden
    // low bits BEFORE selecting gain=16. Never infer safety from a wrapped
    // gain=16 value. Leave upper headroom for positive frequency drift.
    return lo <= hi && uint32_t(lo) * 16 >= OFFSET + 64 &&
      (uint32_t(hi) + 1) * 16 <= OFFSET + 3584;
  }
  uint16_t lastStatus = 0, lastData = 0;
  bool hasData = false;
  uint8_t ioFailures = 0;
  uint16_t baseline = 0, averageCount = 0, windowFlags = 0;
  bool calibrated = false;
  bool referenceAvailable = false;
  unsigned int relativePercent() const {
    if (!calibrated || !baseline) return 0;
    const uint16_t bounded = averageCount > baseline ? baseline : averageCount;
    return uint32_t(baseline - bounded) * 100UL / baseline;
  }
  // TI equation 8, current configured gain=16 and offset=170.
  // Total circuit capacitance change, not absolute skin hydration.
  float capacitanceChangePercent() const {
    if (!calibrated || !baseline) return 0.0f;
    const float ratio = (baseline + 170.0f) / (averageCount + 170.0f);
    return (ratio * ratio - 1.0f) * 100.0f;
  }
  bool needsReconnect() const { return ioFailures >= 3; }
  const char *faultName() const {
    switch (fault) {
      case RANGE_ERROR: return "output_range";
      case CONFIG_ERROR: return "configuration_mismatch";
      case I2C_ERROR: return "i2c_error";
      case NOT_READY: return "not_ready";
      case WATCHDOG: return "watchdog";
      case AMPLITUDE_WARNING:
        if ((lastStatus & 0x0600) == 0x0200) return "amplitude_low";
        if ((lastStatus & 0x0600) == 0x0400) return "amplitude_high";
        return "amplitude_warning";
      default: return "none";
    }
  }
  bool begin() {
    ioFailures = 0; calibrated = false; referenceAvailable = false;
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
    if (!selectAirDrive()) return false;
    // Measure with gain=1 and zero offset first: the previous fixed gain=16
    // configuration could hide the most significant bits. Select the widest
    // safe reference-divider profile, then freeze it until reinitialization.
    // D=44: worst-case conversion+settling <88 ms at fCLK=35 MHz; publish=100 ms.
    const uint16_t dividers[] = {44, 22, 11};
    for (uint8_t i=0; i<3; ++i) {
      referenceDivider = dividers[i];
      if (!configure(0x0000, 0, referenceDivider) || !survey()) return false;
      Serial.print("ACQUISITION divider="); Serial.print(referenceDivider);
      Serial.print(" coarse_min="); Serial.print(coarseMin);
      Serial.print(" coarse_max="); Serial.print(coarseMax);
      Serial.print(" headroom_ok="); Serial.println(hasHeadroom(coarseMin, coarseMax));
      if (!hasHeadroom(coarseMin, coarseMax)) continue;
      if (!configure(0x0600, OFFSET, referenceDivider)) return false;
      // Discard startup settling, so the first published sample belongs to
      // the verified final gain/offset profile, not to the coarse survey.
      delay(100);
      return verifyConfiguration();
    }
    fault = RANGE_ERROR;
    return false;
  }
  // Read back stable writable fields, excluding reserved/self-clearing bits.
  // Never infer configuration from successful I2C acknowledgement alone.
  bool verifyConfiguration() {
    const uint8_t regs[] = {0x1C,0x0C,0x14,0x10,0x08,0x1E,0x19,0x1B,0x1A};
    const uint16_t expected[] = {0x0600,OFFSET,uint16_t(0x2000 | referenceDivider),0x0100,0x1000,uint16_t(driveCode << 11),0x3801,0x0209,0x1401};
    const uint16_t masks[] = {0x0600,0xFFFF,0x33FF,0xFFFF,0xFFFF,0xF800,0x3821,0xFFFF,0xFFFF};
    bool ok = true;
    for (uint8_t i=0; i<sizeof(regs); ++i) {
      uint16_t actual = 0;
      const bool readOK = readWord(regs[i], actual);
      Serial.print("CONFIG reg=0x"); Serial.print(regs[i], HEX);
      Serial.print(" expected=0x"); Serial.print(expected[i], HEX);
      Serial.print(" actual=0x"); Serial.print(actual, HEX);
      Serial.print(" read_ok="); Serial.println(readOK);
      if (!readOK || (actual & masks[i]) != (expected[i] & masks[i])) ok = false;
    }
    fault = ok ? NONE : CONFIG_ERROR;
    Serial.print("CONFIG verified="); Serial.println(ok);
    return ok;
  }
  // Protocol status: 0 valid, 1 error, 2 no fresh conversion.
  uint8_t sample(uint16_t &raw) {
    raw = 0xFFFF;
    hasData = false; referenceAvailable = false;
    lastStatus = 0; lastData = 0; windowFlags = 0; fault = NONE;
    uint16_t status, data;
    if (!readWord(0x18, status)) return ioError();
    lastStatus = status;
    // TI STATUS bit 3: CH0_UNREADCONV. Read DATA only once per fresh conversion.
    if (!(status & 0x0008)) { ioFailures = 0; fault = NOT_READY; return 2; }
    if (!readWord(0x00, data)) return ioError();
    lastData = data; hasData = true; windowFlags = data & 0xF000;
    ioFailures = 0; averageCount = data & 0x0FFF;
    if (windowFlags & 0xE000) { fault = WATCHDOG; return 1; }
    if (windowFlags & 0x1000) { fault = AMPLITUDE_WARNING; return 1; }
    // Do not let a range-edge conversion seed calibration or a result.
    if (averageCount < 64 || averageCount > 3584) { fault = RANGE_ERROR; return 1; }
    referenceAvailable = true;
    raw = averageCount;
    return 0;
  }

 private:
  bool selectAirDrive() {
    // Only normal-current mode (0..31); HIGH_CURRENT_DRV remains disabled.
    // Prefer the strongest drive that actually passes fresh-conversion checks
    // in air. This provides more loading headroom than the old fixed code 15,
    // without assuming that an unknown amplitude warning means "too low".
    // It is NOT an oscilloscope measurement or a guarantee of skin accuracy.
    driveCandidatesTested = 0;
    bool sawFresh = false, sawWarning = false;
    for (int candidate = 31; candidate >= 0; --candidate) {
      driveCode = uint8_t(candidate); ++driveCandidatesTested;
      if (!configure(0, 0, 11)) return false;
      uint8_t accepted = 0;
      const uint32_t started = millis();
      while (millis() - started < 250) {
        uint16_t status = 0, data = 0;
        if (!readWord(0x18, status)) { ioError(); return false; }
        if (status & 8) {
          if (!readWord(0, data)) { ioError(); return false; }
          sawFresh = true; lastStatus = status; lastData = data;
          // Include latched watchdog/high/low status, not just DATA's combined AW.
          if ((data & 0xF000) || (status & 0x0E00)) { sawWarning = true; break; }
          if (!(data & 0x0FFF) || (data & 0x0FFF)==4095) break;
          if (++accepted == 8) {
            Serial.print("DRIVE selected_code="); Serial.print(driveCode);
            Serial.print(" candidates_tested="); Serial.println(driveCandidatesTested);
            return true;
          }
        }
        delay(5);
      }
    }
    fault = !sawFresh ? NOT_READY : sawWarning ? AMPLITUDE_WARNING : RANGE_ERROR;
    return false;
  }
  bool configure(uint16_t gain, uint16_t offset, uint16_t divider) {
    // Enter sleep before changing gain or divider. CONFIG is written last.
    if (!writeWord(0x1A, 0x3401)) return false;
    uint16_t discarded;
    if (!readWord(0x00, discarded)) return false; // clear an old unread conversion
    const uint8_t regs[] = {0x1C,0x10,0x08,0x0C,0x14,0x1E,0x19,0x1B,0x1A};
    // Verified final coarse code is <=233: even with fCLK=55 MHz, FIN=2,
    // and D=11, fSENSOR <572 kHz. TI recommends the lowest filter bandwidth
    // above fSENSOR, so select 1 MHz instead of the old 33 MHz default.
    // Survey with the wide filter first so out-of-band signals cannot be
    // mistaken for low frequencies before their frequency has been checked.
    const uint16_t mux = gain ? 0x0209 : 0x020F;
    const uint16_t values[] = {gain,0x0100,0x1000,offset,uint16_t(0x2000 | divider),uint16_t(driveCode << 11),0x3801,mux,0x1401};
    for (uint8_t i=0; i<sizeof(regs); ++i)
      if (!writeWord(regs[i], values[i])) return false;
    // The gain=1 survey must itself be verified: an acknowledged write does
    // not prove that upper bits are visible. No range decision on bad config.
    const uint16_t masks[] = {0x0600,0xFFFF,0xFFFF,0xFFFF,0x33FF,0xF800,0x3821,0xFFFF,0xFFFF};
    for (uint8_t i=0; i<sizeof(regs); ++i) {
      uint16_t actual;
      if (!readWord(regs[i], actual) || (actual & masks[i]) != (values[i] & masks[i])) {
        fault = CONFIG_ERROR;
        return false;
      }
    }
    return true;
  }
  bool survey() {
    coarseMin = 4095; coarseMax = 0;
    uint8_t n = 0;
    const uint32_t start = millis();
    while (millis() - start < 1500) {
      uint16_t status, data;
      if (!readWord(0x18, status)) { ioError(); return false; }
      if (status & 8) {
        if (!readWord(0x00, data)) { ioError(); return false; }
        // Coarse survey is NOT a skin measurement or a calibration baseline.
        if (data & 0xF000) { fault = (data & 0x1000) ? AMPLITUDE_WARNING : WATCHDOG; return false; }
        const uint16_t code = data & 0x0FFF;
        if (code < coarseMin) coarseMin = code;
        if (code > coarseMax) coarseMax = code;
        if (++n == 8) return true;
      }
      delay(10);
    }
    fault = NOT_READY;
    return false;
  }
  uint8_t ioError() {
    fault = I2C_ERROR;
    if (ioFailures < 255) ++ioFailures;
    return 1;
  }
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
