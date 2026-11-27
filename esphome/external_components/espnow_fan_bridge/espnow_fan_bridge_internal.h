#pragma once

#include "espnow_fan_bridge.h"

#ifdef USE_ESP32

#include <esp_random.h>

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"

namespace esphome {
namespace espnow_fan_bridge {

static const char *const TAG = "espnow_fan_bridge";
static constexpr uint8_t BROADCAST_MAC[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

inline int clamp_int(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }

inline const std::string *find_data_value(const std::vector<std::pair<std::string, std::string>> &data,
                                          const char *key) {
  for (const auto &kv : data) {
    if (kv.first == key) return &kv.second;
  }
  return nullptr;
}

inline uint32_t compute_fan_key(const std::string &fan_entity_id, const std::string &light_entity_id,
                                const std::string &name) {
  if (!fan_entity_id.empty()) return fnv1a_32(fan_entity_id);
  if (!light_entity_id.empty()) return fnv1a_32(light_entity_id);
  return fnv1a_32(name);
}

}  // namespace espnow_fan_bridge
}  // namespace esphome

#endif  // USE_ESP32
