#include "tuya_ble_fan.h"

#ifdef USE_ESP32

#include <esp_bt.h>
#include <esp_random.h>

#include <algorithm>
#include <cmath>
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

namespace {

std::string preset_to_string(const char *s) { return s ? std::string(s) : std::string(); }
std::string preset_to_string(const std::string &s) { return s; }

void mac_u64_to_bda(uint64_t mac, esp_bd_addr_t bda) {
  bda[0] = (mac >> 40) & 0xFF;
  bda[1] = (mac >> 32) & 0xFF;
  bda[2] = (mac >> 24) & 0xFF;
  bda[3] = (mac >> 16) & 0xFF;
  bda[4] = (mac >> 8) & 0xFF;
  bda[5] = mac & 0xFF;
}

std::string mac_u64_to_str(uint64_t mac) {
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

uint64_t parse_mac_str(const std::string &mac_str) {
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

uint32_t fnv1a_hash(const std::string &s) {
  uint32_t h = 2166136261u;
  for (unsigned char c : s) {
    h ^= c;
    h *= 16777619u;
  }
  return h;
}

int mireds_to_tuya_ct(float mireds) {
  float clamped = std::max(MIN_MIREDS, std::min(MAX_MIREDS, mireds));
  float ratio = (MAX_MIREDS - clamped) / (MAX_MIREDS - MIN_MIREDS);
  return std::max(0, std::min(1000, static_cast<int>(std::round(ratio * 1000.0f))));
}

float tuya_ct_to_mireds(int ct) {
  int clamped = std::max(0, std::min(1000, ct));
  float ratio = static_cast<float>(clamped) / 1000.0f;
  return MAX_MIREDS - ratio * (MAX_MIREDS - MIN_MIREDS);
}

int brightness_float_to_tuya(float b) {
  float clamped = std::max(0.0f, std::min(1.0f, b));
  return std::max(10, std::min(1000, static_cast<int>(std::round(10.0f + clamped * 990.0f))));
}

float tuya_brightness_to_float(int b) {
  int clamped = std::max(10, std::min(1000, b));
  return std::max(0.01f, std::min(1.0f, static_cast<float>(clamped - 10) / 990.0f));
}

}  // namespace

// ============================================================================
// TuyaBleFanRegistry
// ============================================================================

bool TuyaBleFanRegistry::get_connection_status(const std::string &entity_or_key,
                                               BleConnStatus &out) const {
  const std::string base = base_entity(entity_or_key);
  auto fan_it = fan_entities_.find(base);
  if (fan_it != fan_entities_.end() && fan_it->second != nullptr) {
    out = fan_it->second->conn_status();
    return true;
  }
  auto light_it = light_entities_.find(base);
  if (light_it != light_entities_.end() && light_it->second != nullptr) {
    out = light_it->second->conn_status();
    return true;
  }
  return false;
}

bool TuyaBleFanRegistry::get_text_state(const std::string &key, std::string &out) const {
  const std::string base = base_entity(key);
  const std::string attr = attr_name(key);

  auto fan_it = fan_entities_.find(base);
  if (fan_it != fan_entities_.end()) {
    const TuyaBleFanDevice *dev = fan_it->second;
    if (attr.empty()) {
      out = dev->fan_on() ? "on" : "off";
      return true;
    }
    if (attr == "percentage") {
      out = std::to_string(dev->fan_percentage());
      return true;
    }
    if (attr == "percentage_step") {
      out = "16.6667";
      return true;
    }
    if (attr == "direction") {
      out = dev->fan_reverse() ? "reverse" : "forward";
      return true;
    }
    if (attr == "preset_mode") {
      out = dev->fan_preset() == 1 ? "nature" : "fresh";
      return true;
    }
    if (attr == "supported_features") {
      // bit 0 = SET_SPEED (1), bit 2 = DIRECTION (4), bit 3 = PRESET_MODE (8)
      out = "13";
      return true;
    }
    out = "";
    return true;
  }

  auto light_it = light_entities_.find(base);
  if (light_it != light_entities_.end()) {
    const TuyaBleFanDevice *dev = light_it->second;
    if (attr.empty()) {
      out = dev->light_on() ? "on" : "off";
      return true;
    }
    if (attr == "brightness") {
      int b255 = static_cast<int>(std::round(tuya_brightness_to_float(dev->light_brightness()) * 255.0f));
      out = std::to_string(b255);
      return true;
    }
    out = "";
    return true;
  }

  return false;
}

bool TuyaBleFanRegistry::get_binary_state(const std::string &key, bool &out) const {
  const std::string base = base_entity(key);
  auto light_it = light_entities_.find(base);
  if (light_it != light_entities_.end()) {
    out = light_it->second->light_on();
    return true;
  }
  auto fan_it = fan_entities_.find(base);
  if (fan_it != fan_entities_.end()) {
    out = fan_it->second->fan_on();
    return true;
  }
  return false;
}

bool TuyaBleFanRegistry::handle_action(const std::string &entity_id, const std::string &action,
                                       const std::vector<std::pair<std::string, std::string>> &data) const {
  const std::string base = base_entity(entity_id);
  // Strip optional domain prefix from action (e.g. "fan.turn_on" -> "turn_on")
  size_t dot = action.find('.');
  const std::string act = (dot == std::string::npos) ? action : action.substr(dot + 1);

  auto find_data = [&data](const std::string &k) -> const std::string * {
    for (const auto &kv : data) {
      if (kv.first == k) return &kv.second;
    }
    return nullptr;
  };

  auto fan_it = fan_entities_.find(base);
  if (fan_it != fan_entities_.end()) {
    TuyaBleFanDevice *dev = fan_it->second;
    if (act == "turn_on") {
      if (const std::string *pct = find_data("percentage")) {
        dev->set_fan_percentage(std::atoi(pct->c_str()));
      } else {
        dev->set_fan_power(true);
      }
      return true;
    }
    if (act == "turn_off") {
      dev->set_fan_power(false);
      return true;
    }
    if (act == "toggle") {
      dev->set_fan_power(!dev->fan_on());
      return true;
    }
    if (act == "set_percentage") {
      if (const std::string *pct = find_data("percentage")) {
        dev->set_fan_percentage(std::atoi(pct->c_str()));
      }
      return true;
    }
    if (act == "set_direction") {
      if (const std::string *dir = find_data("direction")) {
        dev->set_fan_direction(*dir == "reverse");
      }
      return true;
    }
    if (act == "set_preset_mode") {
      if (const std::string *preset = find_data("preset_mode")) {
        dev->set_fan_preset(*preset == "nature" ? 1 : 0);
      }
      return true;
    }
    return true;
  }

  auto light_it = light_entities_.find(base);
  if (light_it != light_entities_.end()) {
    TuyaBleFanDevice *dev = light_it->second;
    if (act == "turn_on") {
      int brightness = dev->light_brightness();
      int ct = dev->light_color_temp();
      bool has_extra = false;
      if (const std::string *b = find_data("brightness")) {
        float bf = std::max(0.0f, std::min(1.0f, static_cast<float>(std::atof(b->c_str())) / 255.0f));
        brightness = brightness_float_to_tuya(bf);
        has_extra = true;
      } else if (const std::string *bp = find_data("brightness_pct")) {
        float bf = std::max(0.0f, std::min(1.0f, static_cast<float>(std::atof(bp->c_str())) / 100.0f));
        brightness = brightness_float_to_tuya(bf);
        has_extra = true;
      }
      if (const std::string *m = find_data("color_temp")) {
        ct = mireds_to_tuya_ct(static_cast<float>(std::atof(m->c_str())));
        has_extra = true;
      } else if (const std::string *k = find_data("kelvin")) {
        float kv = static_cast<float>(std::atof(k->c_str()));
        if (kv > 0.0f) {
          ct = mireds_to_tuya_ct(1000000.0f / kv);
          has_extra = true;
        }
      }
      if (has_extra) {
        dev->set_light_state(true, brightness, ct);
      } else {
        dev->set_light_power(true);
      }
      return true;
    }
    if (act == "turn_off") {
      dev->set_light_power(false);
      return true;
    }
    if (act == "toggle") {
      dev->set_light_power(!dev->light_on());
      return true;
    }
    return true;
  }

  return false;
}

// ============================================================================
// Native ESPHome Entities
// ============================================================================

fan::FanTraits TuyaBleFanEntity::get_traits() {
  fan::FanTraits traits;
  traits.set_speed(true);
  traits.set_supported_speed_count(6);
  traits.set_direction(true);
  return traits;
}

void TuyaBleFanEntity::control(const fan::FanCall &call) {
  if (call.get_state().has_value()) {
    parent_->set_fan_power(*call.get_state());
  }
  if (call.get_speed().has_value()) {
    parent_->set_fan_speed(*call.get_speed());
  }
  if (call.get_direction().has_value()) {
    parent_->set_fan_direction(*call.get_direction() == fan::FanDirection::REVERSE);
  }
  if (call.has_preset_mode()) {
    std::string p = preset_to_string(call.get_preset_mode());
    if (!p.empty()) {
      parent_->set_fan_preset(p == "nature" ? 1 : 0);
    }
  }
}

void TuyaBleFanEntity::sync_from_device() {
  this->state = parent_->fan_on();
  this->speed = parent_->fan_speed();
  this->direction = parent_->fan_reverse() ? fan::FanDirection::REVERSE : fan::FanDirection::FORWARD;
  this->publish_state();
}

light::LightTraits TuyaBleLightOutput::get_traits() {
  light::LightTraits traits;
  traits.set_supported_color_modes({light::ColorMode::COLOR_TEMPERATURE});
  traits.set_min_mireds(MIN_MIREDS);
  traits.set_max_mireds(MAX_MIREDS);
  return traits;
}

void TuyaBleLightOutput::write_state(light::LightState *state) {
  // Skip the initial boot-time write_state() from LightState::setup() so rebooting
  // the CYD never turns off a running ceiling fan light.
  if (!initial_write_skipped_) {
    initial_write_skipped_ = true;
    return;
  }
  // LightState::make_call().perform() invokes write_state() asynchronously on the
  // next loop() tick, so clear syncing_ here rather than inside sync_from_device().
  if (syncing_) {
    syncing_ = false;
    return;
  }
  in_write_state_ = true;
  bool on = state->current_values.is_on();
  if (!on) {
    parent_->set_light_power(false);
  } else {
    int brightness = brightness_float_to_tuya(state->current_values.get_brightness());
    int ct = mireds_to_tuya_ct(state->current_values.get_color_temperature());
    parent_->set_light_state(true, brightness, ct);
  }
  in_write_state_ = false;
}

void TuyaBleLightOutput::sync_from_device() {
  if (light_state_ == nullptr || in_write_state_) return;

  const bool target_on = parent_->light_on();
  const float target_b = tuya_brightness_to_float(parent_->light_brightness());
  const float target_ct = tuya_ct_to_mireds(parent_->light_color_temp());
  const auto &rv = light_state_->remote_values;
  if (rv.is_on() == target_on &&
      (!target_on ||
       (std::fabs(rv.get_brightness() - target_b) < 0.02f &&
        std::fabs(rv.get_color_temperature() - target_ct) < 5.0f))) {
    return;
  }

  initial_write_skipped_ = true;
  syncing_ = true;
  auto call = light_state_->make_call();
  call.set_state(target_on);
  if (target_on) {
    call.set_brightness(target_b);
    call.set_color_temperature(target_ct);
  }
  call.set_transition_length(0);
  call.perform();
}

void TuyaBleTimerNumber::control(float value) {
  int minutes = std::max(0, std::min(540, static_cast<int>(std::round(value))));
  parent_->set_fan_timer(minutes);
}

void TuyaBleTimerNumber::sync_from_device() {
  this->publish_state(static_cast<float>(parent_->fan_timer()));
}

// ============================================================================
// TuyaBleFanDevice
// ============================================================================

void TuyaBleFanDevice::setup() {
  uint32_t pref_hash = fnv1a_hash("tuya_ble_id_v2:" + device_id_);
  identity_pref_ = global_preferences->make_preference<CachedBleIdentity>(pref_hash);
  CachedBleIdentity cached{};
  if (identity_pref_.load(&cached) && cached.mac != 0) {
    if (mac_address_ == 0 || mac_address_ == cached.mac) {
      mac_address_ = cached.mac;
      if (cached.addr_type <= BLE_ADDR_TYPE_RPA_RANDOM) {
        addr_type_ = static_cast<esp_ble_addr_type_t>(cached.addr_type);
      }
    }
    if (uuid_.empty() && cached.uuid[0] != '\0') {
      cached.uuid[16] = '\0';
      uuid_ = cached.uuid;
    }
    ESP_LOGI(TAG, "[%s] Loaded cached BLE identity: mac=%012llX uuid=%s", name_.c_str(),
             static_cast<unsigned long long>(mac_address_), uuid_.c_str());
  }

  uint32_t state_hash = fnv1a_hash("tuya_ble_state_v1:" + device_id_);
  state_pref_ = global_preferences->make_preference<CachedDeviceState>(state_hash);
  CachedDeviceState saved{};
  if (state_pref_.load(&saved) && saved.magic == 0xA5) {
    fan_on_ = saved.fan_on != 0;
    fan_speed_ = std::max(1, std::min(6, static_cast<int>(saved.fan_speed)));
    fan_reverse_ = saved.fan_reverse != 0;
    fan_preset_ = saved.fan_preset > 0 ? 1 : 0;
    light_on_ = saved.light_on != 0;
    light_brightness_ = std::max(10, std::min(1000, static_cast<int>(saved.light_brightness)));
    light_color_temp_ = std::max(0, std::min(1000, static_cast<int>(saved.light_color_temp)));
    last_saved_state_ = saved;
    ESP_LOGI(TAG, "[%s] Restored cached state: fan=%s (spd=%d), light=%s (bri=%d, ct=%d)",
             name_.c_str(), fan_on_ ? "ON" : "OFF", fan_speed_,
             light_on_ ? "ON" : "OFF", light_brightness_, light_color_temp_);
  }

  TuyaBleFanRegistry::instance().register_fan_entity(fan_entity_id_, this);
  if (!light_entity_id_.empty()) {
    TuyaBleFanRegistry::instance().register_light_entity(light_entity_id_, this);
  }
  if (fan_entity_ != nullptr) {
    fan_entity_->sync_from_device();
  }
  if (light_output_ != nullptr) {
    light_output_->sync_from_device();
  }
  if (ble_connected_sensor_ != nullptr) {
    ble_connected_sensor_->publish_state(false);
  }
}

void TuyaBleFanDevice::update_discovered_mac(uint64_t mac, esp_ble_addr_type_t addr_type) {
  update_discovered_identity(mac, addr_type, uuid_);
}

void TuyaBleFanDevice::update_discovered_identity(uint64_t mac, esp_ble_addr_type_t addr_type,
                                                  const std::string &uuid) {
  if (mac == 0) return;
  bool changed = (mac != mac_address_ || addr_type != addr_type_ || (!uuid.empty() && uuid != uuid_));
  mac_address_ = mac;
  addr_type_ = addr_type;
  if (!uuid.empty()) {
    uuid_ = uuid;
  }
  if (changed) {
    CachedBleIdentity cached{};
    cached.mac = mac;
    cached.addr_type = static_cast<uint8_t>(addr_type);
    std::memset(cached.uuid, 0, sizeof(cached.uuid));
    if (!uuid_.empty()) {
      std::memcpy(cached.uuid, uuid_.data(), std::min<size_t>(uuid_.size(), 16));
    }
    identity_pref_.save(&cached);
    ESP_LOGI(TAG, "[%s] Cached BLE identity: mac=%012llX type=%d uuid=%s", name_.c_str(),
             static_cast<unsigned long long>(mac), static_cast<int>(addr_type), uuid_.c_str());
  }
}

int TuyaBleFanDevice::fan_percentage() const {
  if (!fan_on_) return 0;
  int clamped = std::max(1, std::min(6, fan_speed_));
  return static_cast<int>(std::round(clamped * (100.0f / 6.0f)));
}

void TuyaBleFanDevice::queue_dps(const std::vector<TuyaDp> &dps) {
  for (const auto &dp : dps) {
    bool replaced = false;
    for (auto &existing : pending_dps_) {
      if (existing.id == dp.id) {
        existing = dp;
        replaced = true;
        break;
      }
    }
    if (!replaced) {
      pending_dps_.push_back(dp);
    }
  }
  if (hub_ != nullptr) {
    hub_->request_activity(this);
  }
}

std::vector<TuyaDp> TuyaBleFanDevice::take_pending_dps() {
  std::vector<TuyaDp> out;
  out.swap(pending_dps_);
  return out;
}

std::vector<TuyaDp> TuyaBleFanDevice::take_followup_dps() {
  std::vector<TuyaDp> out;
  out.swap(followup_dps_);
  return out;
}

void TuyaBleFanDevice::set_fan_power(bool on) {
  fan_on_ = on;
  queue_dps({TuyaDp::make_bool(DP_FAN_POWER, on)});
  notify_fan_changed();
}

void TuyaBleFanDevice::set_fan_speed(int speed_1_to_6) {
  int clamped = std::max(1, std::min(6, speed_1_to_6));
  fan_speed_ = clamped;
  std::vector<TuyaDp> dps;
  if (!fan_on_) {
    fan_on_ = true;
    dps.push_back(TuyaDp::make_bool(DP_FAN_POWER, true));
  }
  dps.push_back(TuyaDp::make_int(DP_FAN_SPEED, clamped));
  queue_dps(dps);
  notify_fan_changed();
}

void TuyaBleFanDevice::set_fan_percentage(int pct) {
  if (pct <= 0) {
    set_fan_power(false);
    return;
  }
  int speed = std::max(1, std::min(6, static_cast<int>(std::round((pct / 100.0f) * 6.0f))));
  set_fan_speed(speed);
}

void TuyaBleFanDevice::set_fan_direction(bool reverse) {
  fan_reverse_ = reverse;
  queue_dps({TuyaDp::make_enum(DP_FAN_DIRECTION, reverse ? 1 : 0)});
  notify_fan_changed();
}

void TuyaBleFanDevice::set_fan_preset(uint8_t preset) {
  fan_preset_ = preset > 0 ? 1 : 0;
  queue_dps({TuyaDp::make_enum(DP_FAN_PRESET, fan_preset_)});
  notify_fan_changed();
}

void TuyaBleFanDevice::set_fan_timer(int minutes) {
  fan_timer_ = std::max(0, std::min(540, minutes));
  queue_dps({TuyaDp::make_int(DP_FAN_TIMER, fan_timer_)});
  notify_timer_changed();
}

void TuyaBleFanDevice::set_light_power(bool on) {
  light_on_ = on;
  followup_dps_.clear();
  queue_dps({TuyaDp::make_bool(DP_LIGHT_POWER, on)});
  notify_light_changed();
}

void TuyaBleFanDevice::set_light_brightness(int brightness_10_to_1000) {
  set_light_state(true, brightness_10_to_1000, light_color_temp_);
}

void TuyaBleFanDevice::set_light_color_temp(int color_temp_0_to_1000) {
  light_color_temp_ = std::max(0, std::min(1000, color_temp_0_to_1000));
  queue_dps({TuyaDp::make_int(DP_LIGHT_COLOR_TEMP, light_color_temp_)});
  notify_light_changed();
}

void TuyaBleFanDevice::set_light_state(bool on, int brightness_10_to_1000, int color_temp_0_to_1000) {
  bool was_on = light_on_;
  int clamped_b = std::max(10, std::min(1000, brightness_10_to_1000));
  int clamped_ct = std::max(0, std::min(1000, color_temp_0_to_1000));
  bool b_changed = std::abs(clamped_b - light_brightness_) > 10;
  bool ct_changed = std::abs(clamped_ct - light_color_temp_) > 10;
  light_on_ = on;
  if (b_changed) light_brightness_ = clamped_b;
  if (ct_changed) light_color_temp_ = clamped_ct;
  followup_dps_.clear();
  if (!on) {
    queue_dps({TuyaDp::make_bool(DP_LIGHT_POWER, false)});
  } else if (!was_on) {
    // FlyFan MCU ignores brightness/CT in the same packet as OFF->ON; only send a
    // follow-up packet when brightness or color temperature actually changed so a
    // plain power-on from HA does not trigger a second beep.
    if (b_changed) {
      followup_dps_.push_back(TuyaDp::make_int(DP_LIGHT_BRIGHTNESS, light_brightness_));
    }
    if (ct_changed) {
      followup_dps_.push_back(TuyaDp::make_int(DP_LIGHT_COLOR_TEMP, light_color_temp_));
    }
    queue_dps({TuyaDp::make_bool(DP_LIGHT_POWER, true)});
  } else {
    std::vector<TuyaDp> dps;
    if (b_changed) {
      dps.push_back(TuyaDp::make_int(DP_LIGHT_BRIGHTNESS, light_brightness_));
    }
    if (ct_changed) {
      dps.push_back(TuyaDp::make_int(DP_LIGHT_COLOR_TEMP, light_color_temp_));
    }
    if (!dps.empty()) {
      queue_dps(dps);
    }
  }
  notify_light_changed();
}

void TuyaBleFanDevice::apply_incoming_dps(const std::vector<TuyaDp> &dps) {
  bool fan_changed = false;
  bool light_changed = false;
  bool timer_changed = false;

  for (const auto &dp : dps) {
    switch (dp.id) {
      case DP_LIGHT_POWER:
        light_on_ = dp.as_bool();
        light_changed = true;
        break;
      case DP_LIGHT_BRIGHTNESS:
        light_brightness_ = std::max(10, std::min(1000, static_cast<int>(dp.as_int())));
        light_changed = true;
        break;
      case DP_LIGHT_COLOR_TEMP:
        light_color_temp_ = std::max(0, std::min(1000, static_cast<int>(dp.as_int())));
        light_changed = true;
        break;
      case DP_FAN_POWER:
        fan_on_ = dp.as_bool();
        fan_changed = true;
        break;
      case DP_FAN_PRESET:
        fan_preset_ = dp.as_enum() > 0 ? 1 : 0;
        fan_changed = true;
        break;
      case DP_FAN_SPEED:
        fan_speed_ = std::max(1, std::min(6, static_cast<int>(dp.as_int())));
        fan_changed = true;
        break;
      case DP_FAN_DIRECTION:
        fan_reverse_ = dp.as_enum() != 0;
        fan_changed = true;
        break;
      case DP_FAN_TIMER:
        fan_timer_ = std::max(0, std::min(540, static_cast<int>(dp.as_int())));
        timer_changed = true;
        break;
      default:
        ESP_LOGD(TAG, "[%s] Ignoring unknown DP %u", name_.c_str(), dp.id);
        break;
    }
  }

  if (fan_changed) notify_fan_changed();
  if (light_changed) notify_light_changed();
  if (timer_changed) notify_timer_changed();
}

void TuyaBleFanDevice::save_cached_state() {
  CachedDeviceState cur{};
  cur.magic = 0xA5;
  cur.fan_on = fan_on_ ? 1 : 0;
  cur.fan_speed = static_cast<uint8_t>(std::max(1, std::min(6, fan_speed_)));
  cur.fan_reverse = fan_reverse_ ? 1 : 0;
  cur.fan_preset = fan_preset_ > 0 ? 1 : 0;
  cur.light_on = light_on_ ? 1 : 0;
  cur.light_brightness = static_cast<uint16_t>(std::max(10, std::min(1000, light_brightness_)));
  cur.light_color_temp = static_cast<uint16_t>(std::max(0, std::min(1000, light_color_temp_)));
  if (std::memcmp(&cur, &last_saved_state_, sizeof(cur)) == 0) {
    return;
  }
  last_saved_state_ = cur;
  state_pref_.save(&cur);
}

void TuyaBleFanDevice::notify_fan_changed() {
  save_cached_state();
  if (fan_entity_ != nullptr) {
    fan_entity_->sync_from_device();
  }
  if (!fan_entity_id_.empty()) {
    TuyaBleFanRegistry::instance().notify_state_changed(fan_entity_id_, fan_on_ ? "on" : "off");
    TuyaBleFanRegistry::instance().notify_state_changed(fan_entity_id_ + "|percentage",
                                                        std::to_string(fan_percentage()));
    TuyaBleFanRegistry::instance().notify_state_changed(fan_entity_id_ + "|direction",
                                                        fan_reverse_ ? "reverse" : "forward");
  }
  TuyaBleFanRegistry::instance().notify_device_changed(this);
}

void TuyaBleFanDevice::notify_light_changed() {
  save_cached_state();
  if (light_output_ != nullptr) {
    light_output_->sync_from_device();
  }
  if (!light_entity_id_.empty()) {
    TuyaBleFanRegistry::instance().notify_state_changed(light_entity_id_, light_on_ ? "on" : "off");
  }
  TuyaBleFanRegistry::instance().notify_device_changed(this);
}

void TuyaBleFanDevice::notify_timer_changed() {
  if (timer_number_ != nullptr) {
    timer_number_->sync_from_device();
  }
  TuyaBleFanRegistry::instance().notify_device_changed(this);
}

void TuyaBleFanDevice::publish_rssi(int rssi) {
  last_rssi_ = rssi;
  if (rssi_sensor_ != nullptr) {
    rssi_sensor_->publish_state(static_cast<float>(rssi));
  }
}

void TuyaBleFanDevice::clear_rssi() {
  last_rssi_ = -127;
  if (rssi_sensor_ != nullptr && !std::isnan(rssi_sensor_->state)) {
    rssi_sensor_->publish_state(NAN);
  }
}

void TuyaBleFanDevice::set_conn_status(BleConnStatus status) {
  if (conn_status_ == status) return;
  conn_status_ = status;
  if (ble_connected_sensor_ != nullptr) {
    bool is_conn = (status == BleConnStatus::CONNECTED);
    if (!ble_connected_sensor_->has_state() || ble_connected_sensor_->state != is_conn) {
      ble_connected_sensor_->publish_state(is_conn);
    }
  }
  TuyaBleFanRegistry::instance().notify_state_changed("", "");
  TuyaBleFanRegistry::instance().notify_device_changed(this);
}

// ============================================================================
// TuyaBleFanHub
// ============================================================================

void TuyaBleFanHub::setup() {
  sessions_.assign(max_connections_, FanSession{});
  TuyaBleFanRegistry::instance().set_in_flight_connect_provider(
      [this]() { return this->has_in_flight_connect(); });
  for (auto *fan : fans_) {
    fan->set_hub(this);
    fan->setup();
  }
#ifdef USE_API_CUSTOM_SERVICES
  register_service(&TuyaBleFanHub::on_scan_service, "scan_tuya_ble_fans", {"duration_s"});
  register_service(&TuyaBleFanHub::on_pair_service, "pair_unbound_tuya_fan",
                   {"mac", "addr_type", "uuid", "device_id", "local_key", "blink_confirm"});
#endif
  next_reconnect_ms_ = millis();
}

void TuyaBleFanHub::emit_ha_event(const std::string &event_name,
                                  const std::map<std::string, std::string> &data) {
#if defined(USE_API_CUSTOM_SERVICES) && defined(USE_API_HOMEASSISTANT_SERVICES)
  this->fire_homeassistant_event(event_name, data);
#else
  (void) event_name;
  (void) data;
#endif
}

bool TuyaBleFanHub::has_in_flight_connect() const {
  for (const auto &s : sessions_) {
    if (s.state == SessionState::CONNECTING || s.state == SessionState::DISCOVERING ||
        s.state == SessionState::ENABLING_NOTIFY || s.state == SessionState::HANDSHAKE_DEVICE_INFO ||
        s.state == SessionState::HANDSHAKE_PAIR) {
      return true;
    }
  }
  return false;
}

TuyaBleFanHub::FanSession *TuyaBleFanHub::find_session_by_device(TuyaBleFanDevice *device) {
  if (device == nullptr) return nullptr;
  for (auto &s : sessions_) {
    if (s.state != SessionState::IDLE && s.device == device) {
      return &s;
    }
  }
  return nullptr;
}

TuyaBleFanHub::FanSession *TuyaBleFanHub::find_session_by_conn_id(uint16_t conn_id) {
  for (auto &s : sessions_) {
    if (s.has_conn_id && s.conn_id == conn_id) {
      return &s;
    }
  }
  return nullptr;
}

TuyaBleFanHub::FanSession *TuyaBleFanHub::find_session_by_bda(const esp_bd_addr_t bda,
                                                              SessionState required_state) {
  for (auto &s : sessions_) {
    if (s.state == required_state && std::memcmp(s.remote_bda, bda, 6) == 0) {
      return &s;
    }
  }
  return nullptr;
}

TuyaBleFanHub::FanSession *TuyaBleFanHub::find_idle_session() {
  for (auto &s : sessions_) {
    if (s.state == SessionState::IDLE) {
      return &s;
    }
  }
  return nullptr;
}

TuyaBleFanHub::FanSession *TuyaBleFanHub::find_pair_session() {
  for (auto &s : sessions_) {
    if (s.is_unbound_pair && s.state != SessionState::IDLE) {
      return &s;
    }
  }
  return nullptr;
}

TuyaBleFanHub::FanSession *TuyaBleFanHub::find_evictable_session(uint32_t now) {
  FanSession *best = nullptr;
  for (auto &s : sessions_) {
    if (s.state != SessionState::READY || s.is_unbound_pair) continue;
    if (s.device != nullptr && s.device->has_pending_dps()) continue;
    if (!s.write_queue.empty() || (now - s.last_activity_ms < 150)) continue;
    if (best == nullptr || static_cast<int32_t>(s.last_activity_ms - best->last_activity_ms) < 0) {
      best = &s;
    }
  }
  return best;
}

void TuyaBleFanHub::on_scan_service(int32_t duration_s) {
  if (pair_job_.active) {
    ESP_LOGW(TAG, "Ignoring scan_tuya_ble_fans while unbound pairing is in progress");
    emit_ha_event("esphome.tuya_ble_scan_done", {{"count", "0"}});
    return;
  }
  int32_t clamped = std::max<int32_t>(3, std::min<int32_t>(30, duration_s <= 0 ? 10 : duration_s));
  ESP_LOGI(TAG, "On-demand Tuya BLE scan requested for %ld s", static_cast<long>(clamped));
  discovery_sightings_.clear();
  discovery_scan_active_ = true;
  discovery_scan_end_ms_ = millis() + static_cast<uint32_t>(clamped) * 1000u;
  if (parent_ != nullptr && !scan_active_) {
    scan_active_ = true;
    parent_->start_scan();
  }
}

void TuyaBleFanHub::finish_discovery_scan() {
  if (!discovery_scan_active_) return;
  size_t count = discovery_sightings_.size();
  discovery_scan_active_ = false;
  discovery_sightings_.clear();
  discovery_sightings_.shrink_to_fit();
  if (!hub_scanning_) {
    stop_scan_if_running();
  }
  ESP_LOGI(TAG, "On-demand Tuya BLE scan finished (%u unique Tuya devices seen)",
           static_cast<unsigned>(count));
  emit_ha_event("esphome.tuya_ble_scan_done", {{"count", std::to_string(count)}});
}

void TuyaBleFanHub::on_pair_service(std::string mac, int32_t addr_type, std::string uuid,
                                    std::string device_id, std::string local_key,
                                    bool blink_confirm) {
  uint64_t parsed_mac = parse_mac_str(mac);
  if (parsed_mac == 0 || uuid.empty() || device_id.empty() || local_key.empty()) {
    ESP_LOGW(TAG, "Invalid pair_unbound_tuya_fan parameters (mac=%s)", mac.c_str());
    emit_ha_event("esphome.tuya_ble_fan_paired", {
        {"ok", "false"},
        {"mac", mac},
        {"uuid", uuid},
        {"error", "Invalid mac, uuid, device_id, or local_key"},
    });
    return;
  }
  if (this->gattc_if_ == ESP_GATT_IF_NONE) {
    ESP_LOGW(TAG, "BLE GATTC interface not ready yet for pairing");
    emit_ha_event("esphome.tuya_ble_fan_paired", {
        {"ok", "false"},
        {"mac", mac},
        {"uuid", uuid},
        {"error", "BLE GATTC interface not ready yet"},
    });
    return;
  }

  ESP_LOGI(TAG, "Unbound pairing requested for %s (uuid=%s, blink=%d)",
           mac.c_str(), uuid.c_str(), blink_confirm ? 1 : 0);

  if (discovery_scan_active_) {
    finish_discovery_scan();
  }
  stop_scan_if_running();
  hub_scanning_ = false;

  pair_job_ = UnboundPairJob{};
  pair_job_.active = true;
  pair_job_.mac = parsed_mac;
  pair_job_.addr_type = static_cast<esp_ble_addr_type_t>(addr_type);
  pair_job_.mac_str = mac_u64_to_str(parsed_mac);
  pair_job_.uuid = uuid;
  pair_job_.device_id = device_id;
  pair_job_.local_key = local_key;
  pair_job_.blink_confirm = blink_confirm;

  FanSession *idle = find_idle_session();
  if (idle != nullptr && !has_in_flight_connect()) {
    start_unbound_pair_connect(*idle);
  } else {
    pair_job_.waiting_disconnect = true;
    if (idle == nullptr && !sessions_.empty()) {
      disconnect_session(sessions_[0]);
    }
  }
}

void TuyaBleFanHub::start_unbound_pair_connect(FanSession &slot) {
  if (!pair_job_.active) return;
  if (this->gattc_if_ == ESP_GATT_IF_NONE) {
    finish_unbound_pair(false, "BLE GATTC interface not ready");
    return;
  }
  pair_job_.waiting_disconnect = false;
  stop_scan_if_running();
  hub_scanning_ = false;

  slot = FanSession{};
  slot.is_unbound_pair = true;
  derive_unbound_login_key(pair_job_.uuid, slot.login_key);
  mac_u64_to_bda(pair_job_.mac, slot.remote_bda);
  slot.state = SessionState::CONNECTING;
  slot.state_entered_ms = millis();
  slot.last_activity_ms = slot.state_entered_ms;

  ESP_LOGI(TAG, "[unbound-pair] Connecting to %s...", pair_job_.mac_str.c_str());
  esp_err_t err = esp_ble_gattc_open(this->gattc_if_, slot.remote_bda, pair_job_.addr_type, true);
  if (err != ESP_OK) {
    finish_unbound_pair(false, "esp_ble_gattc_open failed");
  }
}

void TuyaBleFanHub::finish_unbound_pair(bool ok, const std::string &error) {
  if (!pair_job_.active) return;
  std::string mac = pair_job_.mac_str;
  std::string uuid = pair_job_.uuid;
  pair_job_.active = false;
  pair_job_.waiting_disconnect = false;

  ESP_LOGI(TAG, "[unbound-pair] %s for %s (error=%s)", ok ? "SUCCESS" : "FAILED",
           mac.c_str(), error.c_str());
  emit_ha_event("esphome.tuya_ble_fan_paired", {
      {"ok", ok ? "true" : "false"},
      {"mac", mac},
      {"uuid", uuid},
      {"error", error},
  });
  if (FanSession *ps = find_pair_session()) {
    disconnect_session(*ps);
  }
}

void TuyaBleFanHub::dump_config() {
  ESP_LOGCONFIG(TAG, "Tuya BLE Fan Hub:");
  ESP_LOGCONFIG(TAG, "  Fans configured: %u (max simultaneous connections: %u)",
                static_cast<unsigned>(fans_.size()), static_cast<unsigned>(max_connections_));
  ESP_LOGCONFIG(TAG, "  Connection mode: %s",
                is_persistent_mode() ? "persistent (all fans stay connected)" : "on-demand (shared slots)");
  if (!is_persistent_mode()) {
    ESP_LOGCONFIG(TAG, "  Idle disconnect: %u s", static_cast<unsigned>(idle_disconnect_s_));
  }
  for (const auto *fan : fans_) {
    ESP_LOGCONFIG(TAG, "  - %s (fan=%s, light=%s, product=%s, mac=%012llX)",
                  fan->name().c_str(), fan->fan_entity_id().c_str(),
                  fan->light_entity_id().c_str(), fan->product_id().c_str(),
                  static_cast<unsigned long long>(fan->mac_address()));
  }
}

void TuyaBleFanHub::request_activity(TuyaBleFanDevice *device) {
  if (device == nullptr || pair_job_.active) return;

  FanSession *existing = find_session_by_device(device);
  if (existing != nullptr) {
    existing->last_activity_ms = millis();
    if (existing->state == SessionState::READY) {
      flush_device_dps(*existing, device);
    }
    return;
  }

  // Device does not currently have an open slot
  pending_switch_device_ = device;

  if (discovery_scan_active_ || hub_scanning_ || has_in_flight_connect()) {
    return;
  }

  FanSession *idle = find_idle_session();
  if (idle != nullptr) {
    pending_switch_device_ = nullptr;
    if (device->has_mac()) {
      start_connect(*idle, device);
    } else {
      start_bounded_scan();
    }
    return;
  }

  // All slots busy — evict the oldest idle READY slot if safe
  if (FanSession *evict = find_evictable_session(millis())) {
    disconnect_session(*evict);
  }
}

TuyaBleFanDevice *TuyaBleFanHub::pick_next_device_needing_slot() {
  if (pending_switch_device_ != nullptr && find_session_by_device(pending_switch_device_) == nullptr) {
    TuyaBleFanDevice *dev = pending_switch_device_;
    pending_switch_device_ = nullptr;
    return dev;
  }
  for (auto *fan : fans_) {
    if (find_session_by_device(fan) == nullptr && fan->has_pending_dps()) {
      return fan;
    }
  }
  if (is_persistent_mode()) {
    for (auto *fan : fans_) {
      if (find_session_by_device(fan) == nullptr) {
        return fan;
      }
    }
  }
  return nullptr;
}

void TuyaBleFanHub::start_bounded_scan() {
  if (parent_ == nullptr || scan_active_) return;
  ESP_LOGI(TAG, "Starting bounded BLE scan (%u ms) to discover fan MAC address(es)",
           static_cast<unsigned>(SCAN_DURATION_MS));
  scan_active_ = true;
  hub_scanning_ = true;
  hub_scan_started_ms_ = millis();
  for (auto *fan : fans_) {
    if (!fan->has_mac()) {
      fan->set_conn_status(BleConnStatus::SCANNING);
    }
  }
  parent_->start_scan();
}

void TuyaBleFanHub::stop_scan_if_running() {
  if (parent_ != nullptr && scan_active_) {
    parent_->stop_scan();
    scan_active_ = false;
  }
}

void TuyaBleFanHub::start_connect(FanSession &slot, TuyaBleFanDevice *device) {
  if (device == nullptr || !device->has_mac()) return;
  if (this->gattc_if_ == ESP_GATT_IF_NONE) return;
  stop_scan_if_running();
  hub_scanning_ = false;

  slot = FanSession{};
  slot.device = device;
  derive_login_key(device->local_key(), slot.login_key);
  mac_u64_to_bda(device->mac_address(), slot.remote_bda);
  slot.state = SessionState::CONNECTING;
  slot.state_entered_ms = millis();
  slot.last_activity_ms = slot.state_entered_ms;
  device->set_conn_status(BleConnStatus::CONNECTING);

  ESP_LOGI(TAG, "[%s] Connecting to %012llX...", device->name().c_str(),
           static_cast<unsigned long long>(device->mac_address()));
  esp_err_t err = esp_ble_gattc_open(this->gattc_if_, slot.remote_bda, device->addr_type(), true);
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "[%s] esp_ble_gattc_open failed: %d", device->name().c_str(), err);
    reset_session(slot);
    next_reconnect_ms_ = millis() + reconnect_backoff_ms_;
    reconnect_backoff_ms_ = std::min<uint32_t>(reconnect_backoff_ms_ * 2, 30000);
  }
}

void TuyaBleFanHub::start_probe(FanSession &slot, TuyaBleFanDevice *device,
                                const ProbeCandidate &candidate) {
  if (device == nullptr || candidate.mac == 0) return;
  if (this->gattc_if_ == ESP_GATT_IF_NONE) return;
  stop_scan_if_running();
  hub_scanning_ = false;

  slot = FanSession{};
  slot.device = device;
  slot.is_probing = true;
  slot.active_probe = candidate;
  derive_login_key(device->local_key(), slot.login_key);
  mac_u64_to_bda(candidate.mac, slot.remote_bda);
  slot.state = SessionState::CONNECTING;
  slot.state_entered_ms = millis();
  slot.last_activity_ms = slot.state_entered_ms;
  device->set_conn_status(BleConnStatus::CONNECTING);

  ESP_LOGI(TAG, "[%s] Probing Tuya v3 candidate %012llX (uuid=%s)...", device->name().c_str(),
           static_cast<unsigned long long>(candidate.mac), candidate.uuid.c_str());
  esp_err_t err = esp_ble_gattc_open(this->gattc_if_, slot.remote_bda, candidate.addr_type, true);
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "[%s] Probe esp_ble_gattc_open failed: %d", device->name().c_str(), err);
    reset_session(slot);
    next_reconnect_ms_ = millis() + reconnect_backoff_ms_;
    reconnect_backoff_ms_ = std::min<uint32_t>(reconnect_backoff_ms_ * 2, 30000);
  }
}

bool TuyaBleFanHub::find_next_probe_candidate(TuyaBleFanDevice *device, ProbeCandidate &out) const {
  if (device == nullptr) return false;
  for (const auto &c : probe_candidates_) {
    bool already_assigned = false;
    for (const auto *other : fans_) {
      if (other->has_mac() && other->mac_address() == c.mac) {
        already_assigned = true;
        break;
      }
    }
    if (already_assigned) continue;

    bool failed = false;
    for (const auto &fp : failed_probes_) {
      if (fp.first == device && fp.second == c.mac) {
        failed = true;
        break;
      }
    }
    if (failed) continue;

    out = c;
    return true;
  }
  return false;
}

void TuyaBleFanHub::record_probe_failure(FanSession &slot) {
  if (!slot.is_probing || slot.device == nullptr || slot.active_probe.mac == 0) return;
  ESP_LOGI(TAG, "[%s] Candidate %012llX did not match local_key — skipping",
           slot.device->name().c_str(), static_cast<unsigned long long>(slot.active_probe.mac));
  failed_probes_.push_back({slot.device, slot.active_probe.mac});
  slot.is_probing = false;
}

void TuyaBleFanHub::disconnect_session(FanSession &slot) {
  if (slot.state == SessionState::IDLE || slot.state == SessionState::DISCONNECTING) {
    return;
  }
  ESP_LOGD(TAG, "Disconnecting BLE GATT session (conn_id=%u)", slot.conn_id);
  slot.state = SessionState::DISCONNECTING;
  slot.state_entered_ms = millis();
  if (this->gattc_if_ != ESP_GATT_IF_NONE && slot.has_conn_id) {
    esp_ble_gattc_close(this->gattc_if_, slot.conn_id);
  } else {
    reset_session(slot);
  }
}

void TuyaBleFanHub::reset_session(FanSession &slot) {
  if (slot.device != nullptr) {
    slot.device->clear_rssi();
    slot.device->set_conn_status(BleConnStatus::DISCONNECTED);
  }
  slot = FanSession{};
  bool any_active = false;
  for (const auto &s : sessions_) {
    if (s.state != SessionState::IDLE) {
      any_active = true;
      break;
    }
  }
  if (!any_active) {
    this->set_state(esp32_ble_tracker::ClientState::IDLE);
  }
}

void TuyaBleFanHub::connect() {
  // Handled directly via esp_ble_gattc_open in start_connect()
}

void TuyaBleFanHub::disconnect() {
  for (auto &s : sessions_) {
    disconnect_session(s);
  }
}

bool TuyaBleFanHub::parse_device(const esp32_ble_tracker::ESPBTDevice &device) {
  const uint8_t *svc_fd50 = nullptr;
  size_t svc_fd50_len = 0;
  const uint8_t *svc_a201 = nullptr;
  size_t svc_a201_len = 0;
  for (const auto &sd : device.get_service_datas()) {
    if (sd.uuid == esp32_ble_tracker::ESPBTUUID::from_uint16(TUYA_BLE_ADV_SERVICE_UUID)) {
      svc_fd50 = sd.data.data();
      svc_fd50_len = sd.data.size();
    } else if (sd.uuid == esp32_ble_tracker::ESPBTUUID::from_uint16(TUYA_BLE_ADV_SERVICE_UUID_V3)) {
      svc_a201 = sd.data.data();
      svc_a201_len = sd.data.size();
    }
  }

  const uint8_t *mfg_data = nullptr;
  size_t mfg_len = 0;
  for (const auto &md : device.get_manufacturer_datas()) {
    if (md.uuid == esp32_ble_tracker::ESPBTUUID::from_uint16(TUYA_BLE_MANUFACTURER_ID)) {
      mfg_data = md.data.data();
      mfg_len = md.data.size();
      break;
    }
  }

  bool has_tuya_svc_uuid = false;
  for (const auto &su : device.get_service_uuids()) {
    if (su == esp32_ble_tracker::ESPBTUUID::from_uint16(TUYA_BLE_ADV_SERVICE_UUID) ||
        su == esp32_ble_tracker::ESPBTUUID::from_uint16(TUYA_BLE_ADV_SERVICE_UUID_V3) ||
        su == esp32_ble_tracker::ESPBTUUID::from_uint16(TUYA_BLE_SERVICE_UUID)) {
      has_tuya_svc_uuid = true;
      break;
    }
  }

  if (svc_fd50 == nullptr && svc_a201 == nullptr && mfg_data == nullptr && !has_tuya_svc_uuid) {
    return false;
  }

  uint64_t addr = device.address_uint64();
  TuyaBleAdvInfo adv = parse_tuya_ble_advertisement(svc_a201, svc_a201_len, svc_fd50, svc_fd50_len,
                                                    mfg_data, mfg_len);
  const std::string &extracted_v3_uuid = adv.uuid;
  bool has_v3_uuid = !extracted_v3_uuid.empty();

  ESP_LOGI(TAG,
           "Seen Tuya BLE adv from %012llX (RSSI %d, addr_type=%d, bound=%d, fd50=%u, a201=%u, mfg=%u, uuid=%s, pid=%s)",
           static_cast<unsigned long long>(addr), device.get_rssi(),
           static_cast<int>(device.get_address_type()), adv.bound ? 1 : 0,
           static_cast<unsigned>(svc_fd50_len), static_cast<unsigned>(svc_a201_len),
           static_cast<unsigned>(mfg_len),
           has_v3_uuid ? extracted_v3_uuid.c_str() : "-",
           adv.product_id.empty() ? "-" : adv.product_id.c_str());

  // On-demand whole-house discovery scan: emit event for newly seen or stronger-RSSI Tuya devices
  if (discovery_scan_active_ && adv.valid) {
    bool should_emit = false;
    bool found = false;
    for (auto &s : discovery_sightings_) {
      if (s.mac == addr) {
        found = true;
        if (device.get_rssi() > s.rssi) {
          s.rssi = device.get_rssi();
          should_emit = true;
        }
        break;
      }
    }
    if (!found && discovery_sightings_.size() < 64) {
      discovery_sightings_.push_back({addr, device.get_rssi()});
      should_emit = true;
    }
    if (should_emit) {
      emit_ha_event("esphome.tuya_ble_fan_found", {
          {"mac", mac_u64_to_str(addr)},
          {"addr_type", std::to_string(static_cast<int>(device.get_address_type()))},
          {"rssi", std::to_string(device.get_rssi())},
          {"bound", adv.bound ? "true" : "false"},
          {"uuid", adv.uuid},
          {"product_id", adv.product_id},
      });
    }
  }

  bool any_missing_mac = false;
  for (auto *fan : fans_) {
    if (!fan->has_mac()) {
      any_missing_mac = true;
      break;
    }
  }

  bool all_known = true;
  bool added_probe_candidate = false;

  if (any_missing_mac && has_v3_uuid) {
    bool already_in_list = false;
    for (auto &c : probe_candidates_) {
      if (c.mac == addr) {
        c.addr_type = device.get_address_type();
        c.uuid = extracted_v3_uuid;
        already_in_list = true;
        break;
      }
    }
    if (!already_in_list && probe_candidates_.size() < 32) {
      probe_candidates_.push_back({addr, device.get_address_type(), extracted_v3_uuid});
      added_probe_candidate = true;
    }
  }

  for (auto *fan : fans_) {
    if (fan->has_mac()) continue;
    if (has_v3_uuid && !fan->uuid().empty() && fan->uuid() == extracted_v3_uuid) {
      fan->update_discovered_identity(addr, device.get_address_type(), extracted_v3_uuid);
    } else if (svc_fd50 != nullptr &&
               match_tuya_advertisement(svc_fd50, svc_fd50_len, mfg_data, mfg_len,
                                        fan->product_id(), fan->device_id(), fan->local_key())) {
      fan->update_discovered_identity(addr, device.get_address_type(), extracted_v3_uuid);
    }
    if (!fan->has_mac()) all_known = false;
  }

  if (all_known && (!probe_candidates_.empty() || !failed_probes_.empty())) {
    probe_candidates_.clear();
    probe_candidates_.shrink_to_fit();
    failed_probes_.clear();
    failed_probes_.shrink_to_fit();
  }

  if (scan_active_ && !discovery_scan_active_ && (all_known || added_probe_candidate)) {
    ESP_LOGI(TAG, all_known ? "All fan BLE identities discovered — stopping scan"
                            : "Found Tuya v3 candidate — stopping scan to verify credentials");
    stop_scan_if_running();
    hub_scanning_ = false;
  }
  return false;
}

void TuyaBleFanHub::on_scan_end() {
  if (scan_active_) {
    scan_active_ = false;
    hub_scanning_ = false;
    for (auto *fan : fans_) {
      if (fan->conn_status() == BleConnStatus::SCANNING) {
        fan->set_conn_status(BleConnStatus::DISCONNECTED);
      }
    }
  }
}

void TuyaBleFanHub::ble_before_disabled_event_handler() {
  if (pair_job_.active) {
    finish_unbound_pair(false, "Bluetooth disabled");
  }
  if (discovery_scan_active_) {
    finish_discovery_scan();
  }
  scan_active_ = false;
  hub_scanning_ = false;
  for (auto &s : sessions_) {
    reset_session(s);
  }
  for (auto *fan : fans_) {
    fan->set_conn_status(BleConnStatus::DISCONNECTED);
  }
  this->gattc_if_ = ESP_GATT_IF_NONE;
  this->set_state(esp32_ble_tracker::ClientState::INIT);
}

void TuyaBleFanHub::loop() {
  if (!esp32_ble::global_ble->is_active()) {
    return;
  }

  if (this->state() == esp32_ble_tracker::ClientState::INIT) {
    esp_err_t ret = esp_ble_gattc_app_register(this->app_id);
    if (ret != ESP_OK) {
      ESP_LOGW(TAG, "esp_ble_gattc_app_register failed (app_id=%u, status=%d)", this->app_id, ret);
    } else {
      ESP_LOGD(TAG, "Called esp_ble_gattc_app_register(app_id=%u)", this->app_id);
      this->set_state(esp32_ble_tracker::ClientState::IDLE);
    }
    return;
  }

  const uint32_t now = millis();

  // 1. Enforce on-demand discovery scan timeout
  if (discovery_scan_active_ && static_cast<int32_t>(now - discovery_scan_end_ms_) >= 0) {
    finish_discovery_scan();
  }

  // 2. Handle pending unbound pairing job
  if (pair_job_.active) {
    if (pair_job_.waiting_disconnect && !has_in_flight_connect()) {
      if (FanSession *idle = find_idle_session()) {
        start_unbound_pair_connect(*idle);
        return;
      }
    }
    if (FanSession *ps = find_pair_session()) {
      if (pair_job_.blink_sent_on && ps->state == SessionState::READY &&
          now - pair_job_.blink_on_ms >= 1200) {
        send_dps(*ps, {TuyaDp::make_bool(DP_LIGHT_POWER, false)});
        pair_job_.blink_sent_on = false;
        pair_job_.blink_sent_off = true;
        pair_job_.blink_off_ms = now;
        return;
      }
      if (pair_job_.blink_sent_off && ps->state == SessionState::READY &&
          now - pair_job_.blink_off_ms >= 300) {
        pair_job_.blink_sent_off = false;
        finish_unbound_pair(true, "");
        return;
      }
    }
  }

  // 3. Enforce bounded MAC-discovery scan timeout
  if (hub_scanning_) {
    if (now - hub_scan_started_ms_ >= SCAN_DURATION_MS) {
      ESP_LOGW(TAG, "Bounded BLE scan timed out");
      if (!discovery_scan_active_) {
        stop_scan_if_running();
      }
      hub_scanning_ = false;
      next_reconnect_ms_ = now + 10000;
    }
  }

  // 4. Maintain each active GATT session slot
  for (auto &slot : sessions_) {
    if (slot.state == SessionState::IDLE) continue;

    if (slot.state == SessionState::CONNECTING || slot.state == SessionState::DISCOVERING ||
        slot.state == SessionState::ENABLING_NOTIFY ||
        slot.state == SessionState::HANDSHAKE_DEVICE_INFO ||
        slot.state == SessionState::HANDSHAKE_PAIR) {
      if (now - slot.state_entered_ms >= HANDSHAKE_TIMEOUT_MS) {
        ESP_LOGW(TAG, "BLE handshake timed out in state %u", static_cast<unsigned>(slot.state));
        if (slot.is_unbound_pair && pair_job_.active) {
          finish_unbound_pair(false, "BLE handshake timed out");
          continue;
        }
        disconnect_session(slot);
        next_reconnect_ms_ = now + reconnect_backoff_ms_;
        reconnect_backoff_ms_ = std::min<uint32_t>(reconnect_backoff_ms_ * 2, 30000);
      }
      continue;
    }

    if (slot.state == SessionState::DISCONNECTING) {
      if (now - slot.state_entered_ms >= 3000) {
        reset_session(slot);
      }
      continue;
    }

    if (slot.state == SessionState::READY && !slot.is_unbound_pair) {
      if (!is_persistent_mode() && idle_disconnect_s_ > 0 &&
          now - slot.last_activity_ms >= idle_disconnect_s_ * 1000u) {
        ESP_LOGI(TAG, "[%s] Idle for %us — disconnecting BLE slot",
                 slot.device ? slot.device->name().c_str() : "?",
                 static_cast<unsigned>(idle_disconnect_s_));
        disconnect_session(slot);
        continue;
      }

      if (slot.device != nullptr) {
        if (slot.device->has_pending_dps()) {
          flush_device_dps(slot, slot.device);
        }
        if (now - slot.last_rssi_poll_ms >= 60000) {
          slot.last_rssi_poll_ms = now;
          esp_ble_gap_read_rssi(slot.remote_bda);
        }
      }
    }
  }

  // 5. Connect next fan needing a slot (serialize one in-flight connect at a time for Bluedroid stability)
  if (!discovery_scan_active_ && !pair_job_.active && !hub_scanning_ && !has_in_flight_connect() &&
      static_cast<int32_t>(now - next_reconnect_ms_) >= 0) {
    TuyaBleFanDevice *next = pick_next_device_needing_slot();
    if (next != nullptr) {
      FanSession *idle = find_idle_session();
      if (idle != nullptr) {
        if (next->has_mac()) {
          start_connect(*idle, next);
        } else {
          ProbeCandidate cand;
          if (find_next_probe_candidate(next, cand)) {
            start_probe(*idle, next, cand);
          } else {
            start_bounded_scan();
          }
        }
      } else {
        // All slots full (e.g. >max_connections_ fans): evict oldest idle READY slot
        pending_switch_device_ = next;
        if (FanSession *evict = find_evictable_session(now)) {
          disconnect_session(*evict);
        }
      }
    }
  }
}

void TuyaBleFanHub::gap_event_handler(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param) {
  if (event == ESP_GAP_BLE_READ_RSSI_COMPLETE_EVT && param != nullptr) {
    if (param->read_rssi_cmpl.status == ESP_BT_STATUS_SUCCESS) {
      for (auto &slot : sessions_) {
        if (slot.state == SessionState::READY && slot.device != nullptr &&
            std::memcmp(param->read_rssi_cmpl.remote_addr, slot.remote_bda, 6) == 0) {
          slot.device->publish_rssi(param->read_rssi_cmpl.rssi);
          break;
        }
      }
    }
  }
}

bool TuyaBleFanHub::gattc_event_handler(esp_gattc_cb_event_t event, esp_gatt_if_t gattc_if,
                                        esp_ble_gattc_cb_param_t *param) {
  if (event == ESP_GATTC_REG_EVT) {
    if (param->reg.app_id != this->app_id) {
      return false;
    }
    if (param->reg.status == ESP_GATT_OK) {
      this->gattc_if_ = gattc_if;
      esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_DEFAULT, ESP_PWR_LVL_P9);
      esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_SCAN, ESP_PWR_LVL_P9);
      esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_CONN_HDL0, ESP_PWR_LVL_P9);
      esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_CONN_HDL1, ESP_PWR_LVL_P9);
      esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_CONN_HDL2, ESP_PWR_LVL_P9);
      ESP_LOGD(TAG, "Registered GATTC interface %d (app_id=%u, BLE TX power +9 dBm)", gattc_if, this->app_id);
    }
    return true;
  }

  if (gattc_if != ESP_GATT_IF_NONE && gattc_if != this->gattc_if_) {
    return false;
  }

  switch (event) {
    case ESP_GATTC_OPEN_EVT: {
      FanSession *slot = find_session_by_bda(param->open.remote_bda, SessionState::CONNECTING);
      if (slot == nullptr) {
        if (param->open.status == ESP_GATT_OK) {
          ESP_LOGW(TAG, "Closing unexpected/stale GATT open (conn_id=%u)", param->open.conn_id);
          esp_ble_gattc_close(gattc_if, param->open.conn_id);
        }
        break;
      }
      if (param->open.status != ESP_GATT_OK) {
        ESP_LOGW(TAG, "GATT open failed (status=%d)", param->open.status);
        if (slot->is_unbound_pair && pair_job_.active) {
          finish_unbound_pair(false, "GATT open failed");
          break;
        }
        reset_session(*slot);
        next_reconnect_ms_ = millis() + reconnect_backoff_ms_;
        reconnect_backoff_ms_ = std::min<uint32_t>(reconnect_backoff_ms_ * 2, 30000);
        break;
      }
      slot->conn_id = param->open.conn_id;
      slot->has_conn_id = true;
      reconnect_backoff_ms_ = 2000;
      slot->state = SessionState::DISCOVERING;
      slot->state_entered_ms = millis();
      esp_bt_uuid_t svc_uuid{};
      svc_uuid.len = ESP_UUID_LEN_16;
      svc_uuid.uuid.uuid16 = TUYA_BLE_SERVICE_UUID;
      esp_ble_gattc_search_service(gattc_if, slot->conn_id, &svc_uuid);
      break;
    }

    case ESP_GATTC_SEARCH_RES_EVT: {
      FanSession *slot = find_session_by_conn_id(param->search_res.conn_id);
      if (slot == nullptr) break;
      if (param->search_res.srvc_id.uuid.len == ESP_UUID_LEN_16 &&
          param->search_res.srvc_id.uuid.uuid.uuid16 == TUYA_BLE_SERVICE_UUID) {
        uint16_t start_h = param->search_res.start_handle;
        uint16_t end_h = param->search_res.end_handle;

        esp_bt_uuid_t w_uuid{};
        w_uuid.len = ESP_UUID_LEN_16;
        w_uuid.uuid.uuid16 = TUYA_BLE_WRITE_CHAR_UUID;
        esp_gattc_char_elem_t char_elem{};
        uint16_t count = 1;
        if (esp_ble_gattc_get_char_by_uuid(gattc_if, slot->conn_id, start_h, end_h, w_uuid, &char_elem, &count) ==
                ESP_GATT_OK &&
            count > 0) {
          slot->write_char_handle = char_elem.char_handle;
        }

        esp_bt_uuid_t n_uuid{};
        n_uuid.len = ESP_UUID_LEN_16;
        n_uuid.uuid.uuid16 = TUYA_BLE_NOTIFY_CHAR_UUID;
        count = 1;
        if (esp_ble_gattc_get_char_by_uuid(gattc_if, slot->conn_id, start_h, end_h, n_uuid, &char_elem, &count) ==
                ESP_GATT_OK &&
            count > 0) {
          slot->notify_char_handle = char_elem.char_handle;
          esp_bt_uuid_t cccd_uuid{};
          cccd_uuid.len = ESP_UUID_LEN_16;
          cccd_uuid.uuid.uuid16 = ESP_GATT_UUID_CHAR_CLIENT_CONFIG;
          esp_gattc_descr_elem_t descr_elem{};
          uint16_t dcount = 1;
          if (esp_ble_gattc_get_descr_by_char_handle(gattc_if, slot->conn_id, slot->notify_char_handle, cccd_uuid,
                                                     &descr_elem, &dcount) == ESP_GATT_OK &&
              dcount > 0) {
            slot->notify_cccd_handle = descr_elem.handle;
          }
        }
      }
      break;
    }

    case ESP_GATTC_SEARCH_CMPL_EVT: {
      FanSession *slot = find_session_by_conn_id(param->search_cmpl.conn_id);
      if (slot == nullptr) break;
      if (slot->write_char_handle == 0 || slot->notify_char_handle == 0 || slot->notify_cccd_handle == 0) {
        ESP_LOGW(TAG, "Tuya GATT characteristics not found (write=%u, notify=%u, cccd=%u)",
                 slot->write_char_handle, slot->notify_char_handle, slot->notify_cccd_handle);
        if (slot->is_unbound_pair && pair_job_.active) {
          finish_unbound_pair(false, "Tuya GATT characteristics not found");
          break;
        }
        disconnect_session(*slot);
        break;
      }
      slot->state = SessionState::ENABLING_NOTIFY;
      slot->state_entered_ms = millis();
      esp_ble_gattc_register_for_notify(gattc_if, slot->remote_bda, slot->notify_char_handle);
      uint8_t notify_en[2] = {0x01, 0x00};
      esp_ble_gattc_write_char_descr(gattc_if, slot->conn_id, slot->notify_cccd_handle, sizeof(notify_en),
                                     notify_en, ESP_GATT_WRITE_TYPE_RSP, ESP_GATT_AUTH_REQ_NONE);
      break;
    }

    case ESP_GATTC_WRITE_DESCR_EVT: {
      FanSession *slot = find_session_by_conn_id(param->write.conn_id);
      if (slot == nullptr) break;
      if (slot->state == SessionState::ENABLING_NOTIFY) {
        if (param->write.status != ESP_GATT_OK) {
          ESP_LOGW(TAG, "Failed to enable notifications (status=%d)", param->write.status);
          if (slot->is_unbound_pair && pair_job_.active) {
            finish_unbound_pair(false, "Failed to enable GATT notifications");
            break;
          }
          disconnect_session(*slot);
          break;
        }
        send_device_info_request(*slot);
      }
      break;
    }

    case ESP_GATTC_WRITE_CHAR_EVT: {
      FanSession *slot = find_session_by_conn_id(param->write.conn_id);
      if (slot == nullptr || param->write.handle != slot->write_char_handle) break;
      if (!slot->write_queue.empty()) {
        slot->write_queue.pop_front();
        flush_write_queue(*slot);
      }
      break;
    }

    case ESP_GATTC_NOTIFY_EVT: {
      FanSession *slot = find_session_by_conn_id(param->notify.conn_id);
      if (slot == nullptr || param->notify.handle != slot->notify_char_handle) break;
      slot->last_activity_ms = millis();
      std::vector<uint8_t> raw_packet;
      uint8_t proto_ver = 3;
      if (slot->reassembler.feed(param->notify.value, param->notify.value_len, raw_packet, proto_ver)) {
        slot->transport_version = proto_ver;
        TuyaDecryptedFrame frame;
        if (parse_encrypted_packet(raw_packet.data(), raw_packet.size(),
                                   slot->login_key, slot->session_key, slot->has_session_key, frame)) {
          handle_decrypted_frame(*slot, frame);
        } else {
          ESP_LOGW(TAG, "Failed to decrypt/verify Tuya BLE packet (len=%u)",
                   static_cast<unsigned>(raw_packet.size()));
        }
      }
      break;
    }

    case ESP_GATTC_DISCONNECT_EVT:
    case ESP_GATTC_CLOSE_EVT: {
      uint16_t evt_conn_id = (event == ESP_GATTC_DISCONNECT_EVT) ? param->disconnect.conn_id
                                                                 : param->close.conn_id;
      FanSession *slot = find_session_by_conn_id(evt_conn_id);
      if (slot == nullptr) break;
      ESP_LOGI(TAG, "BLE GATT disconnected (conn_id=%u, reason=%d)", evt_conn_id,
               event == ESP_GATTC_DISCONNECT_EVT ? param->disconnect.reason : 0);
      if (slot->is_unbound_pair && pair_job_.active) {
        finish_unbound_pair(false, "BLE disconnected during pairing");
        reset_session(*slot);
        break;
      }
      reset_session(*slot);
      break;
    }

    default:
      break;
  }

  return true;
}

void TuyaBleFanHub::enqueue_gatt_packet(FanSession &slot, uint16_t code,
                                        const std::vector<uint8_t> &payload,
                                        uint8_t security_flag, uint32_t response_to) {
  const uint8_t *key = (security_flag == SECURITY_FLAG_LOGIN) ? slot.login_key : slot.session_key;
  uint8_t iv[16];
  esp_fill_random(iv, sizeof(iv));

  uint32_t seq = slot.tx_seq_num++;
  auto enc = build_encrypted_packet(seq, response_to, code, payload, security_flag, key, iv);
  if (enc.empty()) return;
  auto chunks = fragment_gatt_packet(enc, slot.transport_version, 20);
  bool was_empty = slot.write_queue.empty();
  for (auto &c : chunks) {
    if (slot.write_queue.size() < 64) {
      slot.write_queue.push_back(std::move(c));
    }
  }
  if (was_empty) {
    flush_write_queue(slot);
  }
}

void TuyaBleFanHub::flush_write_queue(FanSession &slot) {
  if (slot.write_queue.empty() || slot.write_char_handle == 0 ||
      this->gattc_if_ == ESP_GATT_IF_NONE || !slot.has_conn_id) {
    return;
  }
  auto &front = slot.write_queue.front();
  esp_err_t err = esp_ble_gattc_write_char(this->gattc_if_, slot.conn_id, slot.write_char_handle,
                                           front.size(), front.data(),
                                           ESP_GATT_WRITE_TYPE_NO_RSP, ESP_GATT_AUTH_REQ_NONE);
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "GATT write failed (conn_id=%u): %d", slot.conn_id, err);
    slot.write_queue.clear();
  }
}

void TuyaBleFanHub::send_device_info_request(FanSession &slot) {
  slot.state = SessionState::HANDSHAKE_DEVICE_INFO;
  slot.state_entered_ms = millis();
  if (slot.device != nullptr) {
    slot.device->set_conn_status(BleConnStatus::PAIRING);
  }
  ESP_LOGD(TAG, "Sending FUN_SENDER_DEVICE_INFO (conn_id=%u)", slot.conn_id);
  enqueue_gatt_packet(slot, FUN_SENDER_DEVICE_INFO, {}, SECURITY_FLAG_LOGIN);
}

void TuyaBleFanHub::send_pair_request(FanSession &slot) {
  if (slot.is_unbound_pair && pair_job_.active) {
    slot.state = SessionState::HANDSHAKE_PAIR;
    slot.state_entered_ms = millis();
    ESP_LOGI(TAG, "[unbound-pair] Sending FUN_SENDER_PAIR (uuid=%s)", pair_job_.uuid.c_str());
    auto payload = build_pair_payload(pair_job_.uuid, pair_job_.local_key, pair_job_.device_id);
    enqueue_gatt_packet(slot, FUN_SENDER_PAIR, payload, SECURITY_FLAG_SESSION);
    return;
  }
  if (slot.device == nullptr) return;
  slot.state = SessionState::HANDSHAKE_PAIR;
  slot.state_entered_ms = millis();
  const std::string &uuid_to_use = slot.is_probing ? slot.active_probe.uuid : slot.device->uuid();
  ESP_LOGD(TAG, "Sending FUN_SENDER_PAIR (uuid=%s)", uuid_to_use.c_str());
  auto payload = build_pair_payload(uuid_to_use, slot.device->local_key(), slot.device->device_id());
  enqueue_gatt_packet(slot, FUN_SENDER_PAIR, payload, SECURITY_FLAG_SESSION);
}

void TuyaBleFanHub::send_device_status_request(FanSession &slot) {
  ESP_LOGD(TAG, "Requesting device DP status (conn_id=%u)", slot.conn_id);
  enqueue_gatt_packet(slot, FUN_SENDER_DEVICE_STATUS, {}, SECURITY_FLAG_SESSION);
}

void TuyaBleFanHub::send_dps(FanSession &slot, const std::vector<TuyaDp> &dps) {
  if (dps.empty() || !slot.has_session_key) return;
  slot.last_activity_ms = millis();
  if (slot.protocol_version >= 4) {
    auto payload = encode_dps_v4(slot.dp_seq_num++, dps);
    enqueue_gatt_packet(slot, FUN_SENDER_DPS_V4, payload, SECURITY_FLAG_SESSION);
  } else {
    auto payload = encode_dps_v3(dps);
    enqueue_gatt_packet(slot, FUN_SENDER_DPS, payload, SECURITY_FLAG_SESSION);
  }
}

void TuyaBleFanHub::flush_device_dps(FanSession &slot, TuyaBleFanDevice *device) {
  if (device == nullptr) return;
  auto dps = device->take_pending_dps();
  if (!dps.empty()) {
    send_dps(slot, dps);
  }
  auto followup = device->take_followup_dps();
  if (!followup.empty()) {
    send_dps(slot, followup);
  }
}

void TuyaBleFanHub::handle_decrypted_frame(FanSession &slot, const TuyaDecryptedFrame &frame) {
  if (slot.device == nullptr && !(slot.is_unbound_pair && pair_job_.active)) return;

  if (frame.code == FUN_SENDER_DEVICE_INFO && slot.state == SessionState::HANDSHAKE_DEVICE_INFO) {
    TuyaDeviceInfoResponse info;
    if (!parse_device_info_response(frame.data, info)) {
      ESP_LOGW(TAG, "Invalid DEVICE_INFO response (len=%u)", static_cast<unsigned>(frame.data.size()));
      if (slot.is_unbound_pair && pair_job_.active) {
        finish_unbound_pair(false, "Invalid DEVICE_INFO response");
        return;
      }
      if (slot.is_probing) record_probe_failure(slot);
      disconnect_session(slot);
      return;
    }
    slot.protocol_version = info.protocol_version_major >= 4 ? 4 : 3;
    if (slot.is_unbound_pair && pair_job_.active) {
      derive_unbound_session_key(pair_job_.uuid, info.srand, slot.session_key);
      slot.has_session_key = true;
      ESP_LOGI(TAG, "[unbound-pair] Device info OK (proto v%u.%u, bound=%d)",
               info.protocol_version_major, info.protocol_version_minor, info.is_bind ? 1 : 0);
      send_pair_request(slot);
      return;
    }
    derive_session_key(slot.device->local_key(), info.srand, slot.session_key);
    slot.has_session_key = true;
    ESP_LOGI(TAG, "[%s] Device info OK (proto v%u.%u, bound=%d)",
             slot.device->name().c_str(), info.protocol_version_major,
             info.protocol_version_minor, info.is_bind ? 1 : 0);
    send_pair_request(slot);
    return;
  }

  if (frame.code == FUN_SENDER_PAIR && slot.state == SessionState::HANDSHAKE_PAIR) {
    uint8_t status = frame.data.empty() ? 0 : frame.data[0];
    if (slot.is_unbound_pair && pair_job_.active) {
      if (status != 0 && status != 2) {
        ESP_LOGW(TAG, "[unbound-pair] Pair rejected with status %u", status);
        finish_unbound_pair(false, "Pair rejected (status " + std::to_string(status) + ")");
        return;
      }
      slot.state = SessionState::READY;
      slot.last_activity_ms = millis();
      ESP_LOGI(TAG, "[unbound-pair] Pairing accepted (status=%u)!", status);
      if (pair_job_.blink_confirm) {
        send_dps(slot, {TuyaDp::make_bool(DP_LIGHT_POWER, true)});
        pair_job_.blink_sent_on = true;
        pair_job_.blink_on_ms = millis();
      } else {
        finish_unbound_pair(true, "");
      }
      return;
    }
    if (status != 0 && status != 2) {
      ESP_LOGW(TAG, "[%s] Pair failed with status %u", slot.device->name().c_str(), status);
      if (slot.is_probing) record_probe_failure(slot);
      disconnect_session(slot);
      return;
    }
    if (slot.is_probing) {
      ESP_LOGI(TAG, "[%s] Cryptographically verified candidate %012llX (uuid=%s)!",
               slot.device->name().c_str(),
               static_cast<unsigned long long>(slot.active_probe.mac),
               slot.active_probe.uuid.c_str());
      slot.device->update_discovered_identity(slot.active_probe.mac, slot.active_probe.addr_type,
                                              slot.active_probe.uuid);
      slot.is_probing = false;
    }
    slot.state = SessionState::READY;
    slot.last_activity_ms = millis();
    slot.last_rssi_poll_ms = slot.last_activity_ms;
    slot.device->set_conn_status(BleConnStatus::CONNECTED);
    ESP_LOGI(TAG, "[%s] Tuya BLE session READY (conn_id=%u)", slot.device->name().c_str(), slot.conn_id);

    // Flush any queued user commands immediately, query full status, and read live RSSI
    flush_device_dps(slot, slot.device);
    send_device_status_request(slot);
    esp_ble_gap_read_rssi(slot.remote_bda);
    return;
  }

  if (slot.device == nullptr) return;

  // Device time sync requests (0x8011 = Unix ms ASCII + tz, 0x8012 = local date/time)
  if (frame.code == FUN_RECEIVE_TIME1_REQ) {
    time_t now_s = std::time(nullptr);
    int64_t ts_ms = (now_s > 1700000000) ? static_cast<int64_t>(now_s) * 1000LL : 1700000000000LL;
    char ts_buf[20];
    snprintf(ts_buf, sizeof(ts_buf), "%013lld", static_cast<long long>(ts_ms));
    std::vector<uint8_t> resp(ts_buf, ts_buf + 13);
    resp.push_back(0x00);
    resp.push_back(0x00);
    enqueue_gatt_packet(slot, FUN_RECEIVE_TIME1_REQ, resp, SECURITY_FLAG_SESSION, frame.seq_num);
    return;
  }

  if (frame.code == FUN_RECEIVE_TIME2_REQ) {
    time_t now_s = std::time(nullptr);
    if (now_s < 1700000000) now_s = 1700000000;
    struct tm tm_buf{};
    localtime_r(&now_s, &tm_buf);
    std::vector<uint8_t> resp = {
        static_cast<uint8_t>((tm_buf.tm_year + 1900) % 100),
        static_cast<uint8_t>(tm_buf.tm_mon + 1),
        static_cast<uint8_t>(tm_buf.tm_mday),
        static_cast<uint8_t>(tm_buf.tm_hour),
        static_cast<uint8_t>(tm_buf.tm_min),
        static_cast<uint8_t>(tm_buf.tm_sec),
        static_cast<uint8_t>(tm_buf.tm_wday),
        0x00,
        0x00,
    };
    enqueue_gatt_packet(slot, FUN_RECEIVE_TIME2_REQ, resp, SECURITY_FLAG_SESSION, frame.seq_num);
    return;
  }

  if (frame.code == FUN_RPT_NET_STAT_REQ) {
    enqueue_gatt_packet(slot, FUN_RPT_NET_STAT_REQ, {0x00}, SECURITY_FLAG_SESSION, frame.seq_num);
    return;
  }

  // Incoming DP reports (v3, signed v3, and v4)
  if (frame.code == FUN_RECEIVE_DP || frame.code == FUN_RECEIVE_TIME_DP ||
      frame.code == FUN_RECEIVE_SIGN_DP || frame.code == FUN_RECEIVE_SIGN_TIME_DP ||
      frame.code == FUN_RECEIVE_DP_V4 || frame.code == FUN_RECEIVE_TIME_DP_V4) {
    const uint8_t *ptr = frame.data.data();
    size_t len = frame.data.size();
    std::vector<TuyaDp> dps;
    std::vector<uint8_t> ack_payload;
    bool send_ack = true;

    if (frame.code == FUN_RECEIVE_DP) {
      decode_dps_v3(ptr, len, dps);
    } else if (frame.code == FUN_RECEIVE_TIME_DP && len > 1) {
      uint8_t time_type = ptr[0];
      size_t skip = 1 + (time_type == 0 ? 13 : 4);
      if (skip < len) decode_dps_v3(ptr + skip, len - skip, dps);
    } else if (frame.code == FUN_RECEIVE_SIGN_DP && len > 3) {
      decode_dps_v3(ptr + 3, len - 3, dps);
      ack_payload = {ptr[0], ptr[1], ptr[2], 0x00};
    } else if (frame.code == FUN_RECEIVE_SIGN_TIME_DP && len > 4) {
      uint8_t time_type = ptr[3];
      size_t skip = 4 + (time_type == 0 ? 13 : 4);
      if (skip < len) decode_dps_v3(ptr + skip, len - skip, dps);
      ack_payload = {ptr[0], ptr[1], ptr[2], 0x00};
    } else if (frame.code == FUN_RECEIVE_DP_V4) {
      // Official Tuya BLE v4 header: version(1) + sn(4) + type_ack(1) + mode(1) = 7 bytes
      if (len > 7 && decode_dps_v4(ptr + 7, len - 7, dps) && !dps.empty()) {
        send_ack = (ptr[5] & 0x80) == 0;
        ack_payload.assign(ptr, ptr + 7);
        ack_payload.push_back(0x00);
      } else if (len > 3) {
        // Fallback for non-standard 3-byte v4 header
        decode_dps_v4(ptr + 3, len - 3, dps);
      }
    } else if (frame.code == FUN_RECEIVE_TIME_DP_V4) {
      // Official Tuya BLE v4 header (7 bytes) + time_type(1) + timestamp(13 or 4 bytes)
      if (len > 8) {
        uint8_t time_type = ptr[7];
        size_t skip = 8 + (time_type == 0 ? 13 : 4);
        if (skip < len && decode_dps_v4(ptr + skip, len - skip, dps) && !dps.empty()) {
          send_ack = (ptr[5] & 0x80) == 0;
          ack_payload.assign(ptr, ptr + 7);
          ack_payload.push_back(0x00);
        }
      }
      if (dps.empty() && len > 4) {
        uint8_t time_type = ptr[3];
        size_t skip = 4 + (time_type == 0 ? 13 : 4);
        if (skip < len) decode_dps_v4(ptr + skip, len - skip, dps);
      }
    }

    if (!dps.empty()) {
      ESP_LOGD(TAG, "[%s] Received %u DP(s)", slot.device->name().c_str(),
               static_cast<unsigned>(dps.size()));
      slot.device->apply_incoming_dps(dps);
    }

    // Send ACK response so device stops retrying the notification
    if (send_ack) {
      enqueue_gatt_packet(slot, frame.code, ack_payload, SECURITY_FLAG_SESSION, frame.seq_num);
    }
  }
}

}  // namespace tuya_ble_fan
}  // namespace esphome

#endif  // USE_ESP32
