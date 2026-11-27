#pragma once

#include "tuya_ble_fan.h"

#ifdef USE_ESP32

#include <esp_bt.h>
#include <esp_random.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

#include "esphome/components/esp32_ble/ble.h"
#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"
#include "esphome/core/log.h"

namespace esphome {
namespace tuya_ble_fan {

static const char *const TAG = "tuya_ble_fan";

static constexpr float MIN_MIREDS = 153.846f;  // 6500K (cool, DP 23 = 1000)
static constexpr float MAX_MIREDS = 370.370f;  // 2700K (warm, DP 23 = 0)
static constexpr uint32_t SCAN_DURATION_MS = 15000;
static constexpr uint32_t HANDSHAKE_TIMEOUT_MS = 12000;

inline std::string preset_to_string(const char *s) { return s ? std::string(s) : std::string(); }
inline std::string preset_to_string(const std::string &s) { return s; }

inline void mac_u64_to_bda(uint64_t mac, esp_bd_addr_t bda) {
  bda[0] = (mac >> 40) & 0xFF;
  bda[1] = (mac >> 32) & 0xFF;
  bda[2] = (mac >> 24) & 0xFF;
  bda[3] = (mac >> 16) & 0xFF;
  bda[4] = (mac >> 8) & 0xFF;
  bda[5] = mac & 0xFF;
}

inline std::string mac_u64_to_str(uint64_t mac) {
  char buf[18];
  snprintf(buf, sizeof(buf), "%02X:%02X:%02X:%02X:%02X:%02X",
           static_cast<unsigned>((mac >> 40) & 0xFF),
           static_cast<unsigned>((mac >> 32) & 0xFF),
           static_cast<unsigned>((mac >> 24) & 0xFF),
           static_cast<unsigned>((mac >> 16) & 0xFF),
           static_cast<unsigned>((mac >> 8) & 0xFF),
           static_cast<unsigned>(mac & 0xFF));
  return std::string(buf);
}

inline uint64_t parse_mac_str(const std::string &mac_str) {
  uint64_t out = 0;
  int hex_count = 0;
  for (char c : mac_str) {
    uint8_t nibble = 0;
    if (c >= '0' && c <= '9') nibble = static_cast<uint8_t>(c - '0');
    else if (c >= 'a' && c <= 'f') nibble = static_cast<uint8_t>(10 + c - 'a');
    else if (c >= 'A' && c <= 'F') nibble = static_cast<uint8_t>(10 + c - 'A');
    else continue;
    out = (out << 4) | nibble;
    hex_count++;
  }
  return hex_count == 12 ? out : 0;
}

inline uint32_t fnv1a_hash(const std::string &s) {
  uint32_t h = 2166136261u;
  for (unsigned char c : s) {
    h ^= c;
    h *= 16777619u;
  }
  return h;
}

inline int mireds_to_tuya_ct(float mireds) {
  float clamped = std::max(MIN_MIREDS, std::min(MAX_MIREDS, mireds));
  float ratio = (MAX_MIREDS - clamped) / (MAX_MIREDS - MIN_MIREDS);
  return std::max(0, std::min(1000, static_cast<int>(std::round(ratio * 1000.0f))));
}

inline float tuya_ct_to_mireds(int ct) {
  int clamped = std::max(0, std::min(1000, ct));
  float ratio = static_cast<float>(clamped) / 1000.0f;
  return MAX_MIREDS - ratio * (MAX_MIREDS - MIN_MIREDS);
}

inline int brightness_float_to_tuya(float b) {
  float clamped = std::max(0.0f, std::min(1.0f, b));
  return std::max(10, std::min(1000, static_cast<int>(std::round(10.0f + clamped * 990.0f))));
}

inline float tuya_brightness_to_float(int b) {
  int clamped = std::max(10, std::min(1000, b));
  return std::max(0.01f, std::min(1.0f, static_cast<float>(clamped - 10) / 990.0f));
}

}  // namespace tuya_ble_fan
}  // namespace esphome

#endif  // USE_ESP32
