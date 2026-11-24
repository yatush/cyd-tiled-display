#include "tuya_ble_fan.h"

#ifdef USE_ESP32

#include <esp_random.h>

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>

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
        float bf = std::max(0.0f, std::min(1.0f, std::atof(b->c_str()) / 255.0f));
        brightness = brightness_float_to_tuya(bf);
        has_extra = true;
      } else if (const std::string *bp = find_data("brightness_pct")) {
        float bf = std::max(0.0f, std::min(1.0f, std::atof(bp->c_str()) / 100.0f));
        brightness = brightness_float_to_tuya(bf);
        has_extra = true;
      }
      if (const std::string *m = find_data("color_temp")) {
        ct = mireds_to_tuya_ct(std::atof(m->c_str()));
        has_extra = true;
      } else if (const std::string *k = find_data("kelvin")) {
        float kv = std::atof(k->c_str());
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
  if (syncing_) return;
  bool on = state->current_values.is_on();
  if (!on) {
    parent_->set_light_power(false);
    return;
  }
  int brightness = brightness_float_to_tuya(state->current_values.get_brightness());
  int ct = mireds_to_tuya_ct(state->current_values.get_color_temperature());
  parent_->set_light_state(true, brightness, ct);
}

void TuyaBleLightOutput::sync_from_device() {
  if (light_state_ == nullptr) return;
  syncing_ = true;
  auto call = light_state_->make_call();
  call.set_state(parent_->light_on());
  if (parent_->light_on()) {
    call.set_brightness(tuya_brightness_to_float(parent_->light_brightness()));
    call.set_color_temperature(tuya_ct_to_mireds(parent_->light_color_temp()));
  }
  call.set_transition_length(0);
  call.perform();
  syncing_ = false;
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
  uint32_t pref_hash = fnv1a_hash("tuya_ble_mac:" + device_id_);
  mac_pref_ = global_preferences->make_preference<CachedMac>(pref_hash);
  if (mac_address_ == 0) {
    CachedMac cached{0, static_cast<uint8_t>(BLE_ADDR_TYPE_PUBLIC)};
    if (mac_pref_.load(&cached) && cached.mac != 0) {
      mac_address_ = cached.mac;
      addr_type_ = static_cast<esp_ble_addr_type_t>(cached.addr_type);
      ESP_LOGI(TAG, "[%s] Loaded cached BLE MAC: %012llX", name_.c_str(),
               static_cast<unsigned long long>(mac_address_));
    }
  }

  TuyaBleFanRegistry::instance().register_fan_entity(fan_entity_id_, this);
  if (!light_entity_id_.empty()) {
    TuyaBleFanRegistry::instance().register_light_entity(light_entity_id_, this);
  }
}

void TuyaBleFanDevice::update_discovered_mac(uint64_t mac, esp_ble_addr_type_t addr_type) {
  if (mac == 0) return;
  bool changed = (mac != mac_address_ || addr_type != addr_type_);
  mac_address_ = mac;
  addr_type_ = addr_type;
  if (changed) {
    CachedMac cached{mac, static_cast<uint8_t>(addr_type)};
    mac_pref_.save(&cached);
    ESP_LOGI(TAG, "[%s] Cached discovered BLE MAC: %012llX (type=%d)", name_.c_str(),
             static_cast<unsigned long long>(mac), static_cast<int>(addr_type));
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
  queue_dps({TuyaDp::make_bool(DP_LIGHT_POWER, on)});
  notify_light_changed();
}

void TuyaBleFanDevice::set_light_brightness(int brightness_10_to_1000) {
  light_brightness_ = std::max(10, std::min(1000, brightness_10_to_1000));
  light_on_ = true;
  queue_dps({TuyaDp::make_bool(DP_LIGHT_POWER, true), TuyaDp::make_int(DP_LIGHT_BRIGHTNESS, light_brightness_)});
  notify_light_changed();
}

void TuyaBleFanDevice::set_light_color_temp(int color_temp_0_to_1000) {
  light_color_temp_ = std::max(0, std::min(1000, color_temp_0_to_1000));
  queue_dps({TuyaDp::make_int(DP_LIGHT_COLOR_TEMP, light_color_temp_)});
  notify_light_changed();
}

void TuyaBleFanDevice::set_light_state(bool on, int brightness_10_to_1000, int color_temp_0_to_1000) {
  light_on_ = on;
  light_brightness_ = std::max(10, std::min(1000, brightness_10_to_1000));
  light_color_temp_ = std::max(0, std::min(1000, color_temp_0_to_1000));
  std::vector<TuyaDp> dps;
  dps.push_back(TuyaDp::make_bool(DP_LIGHT_POWER, on));
  if (on) {
    dps.push_back(TuyaDp::make_int(DP_LIGHT_BRIGHTNESS, light_brightness_));
    dps.push_back(TuyaDp::make_int(DP_LIGHT_COLOR_TEMP, light_color_temp_));
  }
  queue_dps(dps);
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

void TuyaBleFanDevice::notify_fan_changed() {
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
}

void TuyaBleFanDevice::notify_light_changed() {
  if (light_output_ != nullptr) {
    light_output_->sync_from_device();
  }
  if (!light_entity_id_.empty()) {
    TuyaBleFanRegistry::instance().notify_state_changed(light_entity_id_, light_on_ ? "on" : "off");
  }
}

void TuyaBleFanDevice::notify_timer_changed() {
  if (timer_number_ != nullptr) {
    timer_number_->sync_from_device();
  }
}

// ============================================================================
// TuyaBleFanHub
// ============================================================================

void TuyaBleFanHub::setup() {
  for (auto *fan : fans_) {
    fan->set_hub(this);
    fan->setup();
  }
  if (parent_ != nullptr) {
    parent_->register_client(this);
  }
  state_entered_ms_ = millis();
  last_activity_ms_ = millis();
}

void TuyaBleFanHub::dump_config() {
  ESP_LOGCONFIG(TAG, "Tuya BLE Fan Hub:");
  ESP_LOGCONFIG(TAG, "  Fans configured: %u", static_cast<unsigned>(fans_.size()));
  ESP_LOGCONFIG(TAG, "  Connection mode: %s",
                is_persistent_mode() ? "persistent (1 fan)" : "on-demand (idle disconnect)");
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
  if (device == nullptr) return;
  last_activity_ms_ = millis();

  if (session_state_ == SessionState::READY && active_device_ == device) {
    auto dps = device->take_pending_dps();
    if (!dps.empty()) {
      send_dps(dps);
    }
    return;
  }

  if (active_device_ != nullptr && active_device_ != device) {
    // Switch cleanly to the newly requested fan
    pending_switch_device_ = device;
    if (session_state_ == SessionState::READY ||
        session_state_ == SessionState::HANDSHAKE_DEVICE_INFO ||
        session_state_ == SessionState::HANDSHAKE_PAIR ||
        session_state_ == SessionState::DISCOVERING ||
        session_state_ == SessionState::ENABLING_NOTIFY) {
      disconnect_current();
    }
    return;
  }

  if (session_state_ == SessionState::IDLE) {
    if (device->has_mac()) {
      start_connect(device);
    } else {
      start_bounded_scan();
    }
  }
}

TuyaBleFanDevice *TuyaBleFanHub::pick_next_device_with_work() {
  if (pending_switch_device_ != nullptr) {
    TuyaBleFanDevice *dev = pending_switch_device_;
    pending_switch_device_ = nullptr;
    return dev;
  }
  for (auto *fan : fans_) {
    if (fan->has_pending_dps()) return fan;
  }
  if (is_persistent_mode() && !fans_.empty()) {
    return fans_[0];
  }
  return nullptr;
}

void TuyaBleFanHub::start_bounded_scan() {
  if (parent_ == nullptr || scan_active_) return;
  ESP_LOGI(TAG, "Starting bounded BLE scan (%u ms) to discover fan MAC address(es)",
           static_cast<unsigned>(SCAN_DURATION_MS));
  scan_active_ = true;
  session_state_ = SessionState::SCANNING;
  state_entered_ms_ = millis();
  parent_->start_scan();
}

void TuyaBleFanHub::stop_scan_if_running() {
  if (parent_ != nullptr && scan_active_) {
    parent_->stop_scan();
    scan_active_ = false;
  }
}

void TuyaBleFanHub::start_connect(TuyaBleFanDevice *device) {
  if (device == nullptr || !device->has_mac()) return;
  if (this->gattc_if_ == 0) {
    // Wait until ESP_GATTC_REG_EVT registers gattc_if_
    return;
  }
  stop_scan_if_running();

  active_device_ = device;
  derive_login_key(device->local_key(), login_key_);
  has_session_key_ = false;
  protocol_version_ = 3;
  tx_seq_num_ = 1;
  dp_seq_num_ = 1;
  write_char_handle_ = 0;
  notify_char_handle_ = 0;
  notify_cccd_handle_ = 0;
  reassembler_.reset();
  write_queue_.clear();

  mac_u64_to_bda(device->mac_address(), this->remote_bda_);
  this->address_ = device->mac_address();
  session_state_ = SessionState::CONNECTING;
  state_entered_ms_ = millis();
  last_activity_ms_ = millis();

  ESP_LOGI(TAG, "[%s] Connecting to %012llX...", device->name().c_str(),
           static_cast<unsigned long long>(device->mac_address()));
  esp_err_t err = esp_ble_gattc_open(this->gattc_if_, this->remote_bda_, device->addr_type(), true);
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "[%s] esp_ble_gattc_open failed: %d", device->name().c_str(), err);
    reset_session();
    next_reconnect_ms_ = millis() + reconnect_backoff_ms_;
    reconnect_backoff_ms_ = std::min<uint32_t>(reconnect_backoff_ms_ * 2, 30000);
  }
}

void TuyaBleFanHub::disconnect_current() {
  if (session_state_ == SessionState::IDLE || session_state_ == SessionState::DISCONNECTING) {
    return;
  }
  ESP_LOGD(TAG, "Disconnecting BLE GATT session");
  session_state_ = SessionState::DISCONNECTING;
  state_entered_ms_ = millis();
  if (this->gattc_if_ != 0 && this->conn_id_ != 0) {
    esp_ble_gattc_close(this->gattc_if_, this->conn_id_);
  } else {
    reset_session();
  }
}

void TuyaBleFanHub::reset_session() {
  session_state_ = SessionState::IDLE;
  active_device_ = nullptr;
  write_char_handle_ = 0;
  notify_char_handle_ = 0;
  notify_cccd_handle_ = 0;
  has_session_key_ = false;
  reassembler_.reset();
  write_queue_.clear();
  this->set_state(esp32_ble_tracker::ClientState::IDLE);
}

void TuyaBleFanHub::connect() {
  // Handled directly via esp_ble_gattc_open in start_connect()
}

bool TuyaBleFanHub::parse_device(const esp32_ble_tracker::ESPBTDevice &device) {
  const uint8_t *svc_data = nullptr;
  size_t svc_len = 0;
  for (const auto &sd : device.get_service_datas()) {
    if (sd.uuid == esp32_ble_tracker::ESPBTUUID::from_uint16(TUYA_BLE_ADV_SERVICE_UUID)) {
      svc_data = sd.data.data();
      svc_len = sd.data.size();
      break;
    }
  }
  if (svc_data == nullptr) return false;

  const uint8_t *mfg_data = nullptr;
  size_t mfg_len = 0;
  for (const auto &md : device.get_manufacturer_datas()) {
    if (md.uuid == esp32_ble_tracker::ESPBTUUID::from_uint16(TUYA_BLE_MANUFACTURER_ID)) {
      mfg_data = md.data.data();
      mfg_len = md.data.size();
      break;
    }
  }

  uint64_t addr = device.address_uint64();
  ESP_LOGD(TAG, "Seen Tuya BLE adv from %s (RSSI %d, svc_len=%u, mfg_len=%u)",
           device.address_str().c_str(), device.get_rssi(),
           static_cast<unsigned>(svc_len), static_cast<unsigned>(mfg_len));

  bool all_known = true;
  for (auto *fan : fans_) {
    if (fan->has_mac()) continue;
    if (match_tuya_advertisement(svc_data, svc_len, mfg_data, mfg_len,
                                 fan->product_id(), fan->device_id(), fan->local_key())) {
      fan->update_discovered_mac(addr, device.get_address_type());
    }
    if (!fan->has_mac()) all_known = false;
  }

  if (all_known && scan_active_) {
    ESP_LOGI(TAG, "All fan BLE MAC addresses discovered — stopping scan");
    stop_scan_if_running();
    session_state_ = SessionState::IDLE;
  }
  return false;
}

void TuyaBleFanHub::on_scan_end() {
  if (scan_active_) {
    scan_active_ = false;
    if (session_state_ == SessionState::SCANNING) {
      session_state_ = SessionState::IDLE;
    }
  }
}

void TuyaBleFanHub::loop() {
  const uint32_t now = millis();

  // Enforce bounded scan timeout
  if (session_state_ == SessionState::SCANNING) {
    if (now - state_entered_ms_ >= SCAN_DURATION_MS) {
      ESP_LOGW(TAG, "Bounded BLE scan timed out");
      stop_scan_if_running();
      session_state_ = SessionState::IDLE;
      next_reconnect_ms_ = now + 10000;
    }
    return;
  }

  // Enforce handshake / connection / disconnect timeouts
  if (session_state_ == SessionState::CONNECTING ||
      session_state_ == SessionState::DISCOVERING ||
      session_state_ == SessionState::ENABLING_NOTIFY ||
      session_state_ == SessionState::HANDSHAKE_DEVICE_INFO ||
      session_state_ == SessionState::HANDSHAKE_PAIR) {
    if (now - state_entered_ms_ >= HANDSHAKE_TIMEOUT_MS) {
      ESP_LOGW(TAG, "BLE handshake timed out in state %u", static_cast<unsigned>(session_state_));
      disconnect_current();
      next_reconnect_ms_ = now + reconnect_backoff_ms_;
      reconnect_backoff_ms_ = std::min<uint32_t>(reconnect_backoff_ms_ * 2, 30000);
    }
    return;
  }

  if (session_state_ == SessionState::DISCONNECTING) {
    if (now - state_entered_ms_ >= 3000) {
      reset_session();
    }
    return;
  }

  // Idle disconnect when in on-demand mode
  if (session_state_ == SessionState::READY && !is_persistent_mode() && idle_disconnect_s_ > 0) {
    if (now - last_activity_ms_ >= idle_disconnect_s_ * 1000u) {
      ESP_LOGI(TAG, "[%s] Idle for %us — disconnecting BLE slot",
               active_device_ ? active_device_->name().c_str() : "?",
               static_cast<unsigned>(idle_disconnect_s_));
      disconnect_current();
      return;
    }
  }

  // Flush any pending DPs if READY
  if (session_state_ == SessionState::READY && active_device_ != nullptr) {
    if (active_device_->has_pending_dps()) {
      auto dps = active_device_->take_pending_dps();
      if (!dps.empty()) {
        send_dps(dps);
      }
    }
    return;
  }

  // IDLE: check if any fan needs MAC discovery or connection
  if (session_state_ == SessionState::IDLE && now >= next_reconnect_ms_) {
    TuyaBleFanDevice *next = pick_next_device_with_work();
    if (next != nullptr) {
      if (next->has_mac()) {
        start_connect(next);
      } else {
        start_bounded_scan();
      }
    }
  }
}

void TuyaBleFanHub::gap_event_handler(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param) {
  (void) event;
  (void) param;
}

bool TuyaBleFanHub::gattc_event_handler(esp_gattc_cb_event_t event, esp_gatt_if_t gattc_if,
                                        esp_ble_gattc_cb_param_t *param) {
  if (event == ESP_GATTC_REG_EVT) {
    if (param->reg.status == ESP_GATT_OK) {
      this->gattc_if_ = gattc_if;
      ESP_LOGD(TAG, "Registered GATTC interface %d", gattc_if);
    }
    return true;
  }

  if (gattc_if != ESP_GATT_IF_NONE && gattc_if != this->gattc_if_) {
    return false;
  }

  switch (event) {
    case ESP_GATTC_OPEN_EVT: {
      if (param->open.status != ESP_GATT_OK) {
        ESP_LOGW(TAG, "GATT open failed (status=%d)", param->open.status);
        reset_session();
        next_reconnect_ms_ = millis() + reconnect_backoff_ms_;
        reconnect_backoff_ms_ = std::min<uint32_t>(reconnect_backoff_ms_ * 2, 30000);
        break;
      }
      this->conn_id_ = param->open.conn_id;
      reconnect_backoff_ms_ = 2000;
      session_state_ = SessionState::DISCOVERING;
      state_entered_ms_ = millis();
      esp_bt_uuid_t svc_uuid{};
      svc_uuid.len = ESP_UUID_LEN_16;
      svc_uuid.uuid.uuid16 = TUYA_BLE_SERVICE_UUID;
      esp_ble_gattc_search_service(gattc_if, this->conn_id_, &svc_uuid);
      break;
    }

    case ESP_GATTC_SEARCH_RES_EVT: {
      if (param->search_res.srvc_id.uuid.len == ESP_UUID_LEN_16 &&
          param->search_res.srvc_id.uuid.uuid.uuid16 == TUYA_BLE_SERVICE_UUID) {
        uint16_t start_h = param->search_res.start_handle;
        uint16_t end_h = param->search_res.end_handle;

        esp_bt_uuid_t w_uuid{};
        w_uuid.len = ESP_UUID_LEN_16;
        w_uuid.uuid.uuid16 = TUYA_BLE_WRITE_CHAR_UUID;
        esp_gattc_char_elem_t char_elem{};
        uint16_t count = 1;
        if (esp_ble_gattc_get_char_by_uuid(gattc_if, this->conn_id_, start_h, end_h, w_uuid, &char_elem, &count) ==
                ESP_GATT_OK &&
            count > 0) {
          write_char_handle_ = char_elem.char_handle;
        }

        esp_bt_uuid_t n_uuid{};
        n_uuid.len = ESP_UUID_LEN_16;
        n_uuid.uuid.uuid16 = TUYA_BLE_NOTIFY_CHAR_UUID;
        count = 1;
        if (esp_ble_gattc_get_char_by_uuid(gattc_if, this->conn_id_, start_h, end_h, n_uuid, &char_elem, &count) ==
                ESP_GATT_OK &&
            count > 0) {
          notify_char_handle_ = char_elem.char_handle;
          esp_bt_uuid_t cccd_uuid{};
          cccd_uuid.len = ESP_UUID_LEN_16;
          cccd_uuid.uuid.uuid16 = ESP_GATT_UUID_CHAR_CLIENT_CONFIG;
          esp_gattc_descr_elem_t descr_elem{};
          uint16_t dcount = 1;
          if (esp_ble_gattc_get_descr_by_char_handle(gattc_if, this->conn_id_, notify_char_handle_, cccd_uuid,
                                                     &descr_elem, &dcount) == ESP_GATT_OK &&
              dcount > 0) {
            notify_cccd_handle_ = descr_elem.handle;
          }
        }
      }
      break;
    }

    case ESP_GATTC_SEARCH_CMPL_EVT: {
      if (write_char_handle_ == 0 || notify_char_handle_ == 0 || notify_cccd_handle_ == 0) {
        ESP_LOGW(TAG, "Tuya GATT characteristics not found (write=%u, notify=%u, cccd=%u)",
                 write_char_handle_, notify_char_handle_, notify_cccd_handle_);
        disconnect_current();
        break;
      }
      session_state_ = SessionState::ENABLING_NOTIFY;
      state_entered_ms_ = millis();
      esp_ble_gattc_register_for_notify(gattc_if, this->remote_bda_, notify_char_handle_);
      uint8_t notify_en[2] = {0x01, 0x00};
      esp_ble_gattc_write_char_descr(gattc_if, this->conn_id_, notify_cccd_handle_, sizeof(notify_en),
                                     notify_en, ESP_GATT_WRITE_TYPE_RSP, ESP_GATT_AUTH_REQ_NONE);
      break;
    }

    case ESP_GATTC_WRITE_DESCR_EVT: {
      if (session_state_ == SessionState::ENABLING_NOTIFY) {
        if (param->write.status != ESP_GATT_OK) {
          ESP_LOGW(TAG, "Failed to enable notifications (status=%d)", param->write.status);
          disconnect_current();
          break;
        }
        send_device_info_request();
      }
      break;
    }

    case ESP_GATTC_WRITE_CHAR_EVT: {
      if (!write_queue_.empty()) {
        write_queue_.pop_front();
        flush_write_queue();
      }
      break;
    }

    case ESP_GATTC_NOTIFY_EVT: {
      if (param->notify.handle != notify_char_handle_) break;
      last_activity_ms_ = millis();
      std::vector<uint8_t> raw_packet;
      uint8_t proto_ver = 3;
      if (reassembler_.feed(param->notify.value, param->notify.value_len, raw_packet, proto_ver)) {
        protocol_version_ = proto_ver;
        TuyaDecryptedFrame frame;
        if (parse_encrypted_packet(raw_packet.data(), raw_packet.size(),
                                   login_key_, session_key_, has_session_key_, frame)) {
          handle_decrypted_frame(frame);
        } else {
          ESP_LOGW(TAG, "Failed to decrypt/verify Tuya BLE packet (len=%u)",
                   static_cast<unsigned>(raw_packet.size()));
        }
      }
      break;
    }

    case ESP_GATTC_DISCONNECT_EVT:
    case ESP_GATTC_CLOSE_EVT: {
      ESP_LOGI(TAG, "BLE GATT disconnected (reason=%d)",
               event == ESP_GATTC_DISCONNECT_EVT ? param->disconnect.reason : 0);
      reset_session();
      break;
    }

    default:
      break;
  }

  return true;
}

void TuyaBleFanHub::enqueue_gatt_packet(uint16_t code, const std::vector<uint8_t> &payload,
                                        uint8_t security_flag) {
  const uint8_t *key = (security_flag == SECURITY_FLAG_LOGIN) ? login_key_ : session_key_;
  uint8_t iv[16];
  esp_fill_random(iv, sizeof(iv));

  uint32_t seq = tx_seq_num_++;
  auto enc = build_encrypted_packet(seq, 0, code, payload, security_flag, key, iv);
  auto chunks = fragment_gatt_packet(enc, protocol_version_, 20);
  bool was_empty = write_queue_.empty();
  for (auto &c : chunks) {
    write_queue_.push_back(std::move(c));
  }
  if (was_empty) {
    flush_write_queue();
  }
}

void TuyaBleFanHub::flush_write_queue() {
  if (write_queue_.empty() || write_char_handle_ == 0 || this->gattc_if_ == 0) return;
  auto &front = write_queue_.front();
  esp_err_t err = esp_ble_gattc_write_char(this->gattc_if_, this->conn_id_, write_char_handle_,
                                           front.size(), front.data(),
                                           ESP_GATT_WRITE_TYPE_NO_RSP, ESP_GATT_AUTH_REQ_NONE);
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "GATT write failed: %d", err);
    write_queue_.clear();
  }
}

void TuyaBleFanHub::send_device_info_request() {
  session_state_ = SessionState::HANDSHAKE_DEVICE_INFO;
  state_entered_ms_ = millis();
  ESP_LOGD(TAG, "Sending FUN_SENDER_DEVICE_INFO");
  enqueue_gatt_packet(FUN_SENDER_DEVICE_INFO, {}, SECURITY_FLAG_LOGIN);
}

void TuyaBleFanHub::send_pair_request() {
  if (active_device_ == nullptr) return;
  session_state_ = SessionState::HANDSHAKE_PAIR;
  state_entered_ms_ = millis();
  ESP_LOGD(TAG, "Sending FUN_SENDER_PAIR");
  auto payload = build_pair_payload(active_device_->uuid(), active_device_->local_key(),
                                    active_device_->device_id());
  enqueue_gatt_packet(FUN_SENDER_PAIR, payload, SECURITY_FLAG_SESSION);
}

void TuyaBleFanHub::send_device_status_request() {
  ESP_LOGD(TAG, "Requesting device DP status");
  enqueue_gatt_packet(FUN_SENDER_DEVICE_STATUS, {}, SECURITY_FLAG_SESSION);
}

void TuyaBleFanHub::send_dps(const std::vector<TuyaDp> &dps) {
  if (dps.empty() || !has_session_key_) return;
  last_activity_ms_ = millis();
  if (protocol_version_ >= 4) {
    auto payload = encode_dps_v4(dp_seq_num_++, dps);
    enqueue_gatt_packet(FUN_SENDER_DPS_V4, payload, SECURITY_FLAG_SESSION);
  } else {
    auto payload = encode_dps_v3(dps);
    enqueue_gatt_packet(FUN_SENDER_DPS, payload, SECURITY_FLAG_SESSION);
  }
}

void TuyaBleFanHub::handle_decrypted_frame(const TuyaDecryptedFrame &frame) {
  if (active_device_ == nullptr) return;

  if (frame.code == FUN_SENDER_DEVICE_INFO && session_state_ == SessionState::HANDSHAKE_DEVICE_INFO) {
    TuyaDeviceInfoResponse info;
    if (!parse_device_info_response(frame.data, info)) {
      ESP_LOGW(TAG, "Invalid DEVICE_INFO response (len=%u)", static_cast<unsigned>(frame.data.size()));
      disconnect_current();
      return;
    }
    protocol_version_ = info.protocol_version_major >= 4 ? 4 : 3;
    derive_session_key(active_device_->local_key(), info.srand, session_key_);
    has_session_key_ = true;
    ESP_LOGI(TAG, "[%s] Device info OK (proto v%u.%u, bound=%d)",
             active_device_->name().c_str(), info.protocol_version_major,
             info.protocol_version_minor, info.is_bind ? 1 : 0);
    send_pair_request();
    return;
  }

  if (frame.code == FUN_SENDER_PAIR && session_state_ == SessionState::HANDSHAKE_PAIR) {
    uint8_t status = frame.data.empty() ? 0 : frame.data[0];
    if (status != 0 && status != 2) {
      ESP_LOGW(TAG, "[%s] Pair failed with status %u", active_device_->name().c_str(), status);
      disconnect_current();
      return;
    }
    session_state_ = SessionState::READY;
    last_activity_ms_ = millis();
    ESP_LOGI(TAG, "[%s] Tuya BLE session READY", active_device_->name().c_str());

    // Flush any queued user commands immediately, then query full status
    auto dps = active_device_->take_pending_dps();
    if (!dps.empty()) {
      send_dps(dps);
    }
    send_device_status_request();
    return;
  }

  // Incoming DP reports (v3 and v4)
  if (frame.code == FUN_RECEIVE_DP || frame.code == FUN_RECEIVE_TIME_DP ||
      frame.code == FUN_RECEIVE_DP_V4 || frame.code == FUN_RECEIVE_TIME_DP_V4) {
    const uint8_t *ptr = frame.data.data();
    size_t len = frame.data.size();
    std::vector<TuyaDp> dps;

    if (frame.code == FUN_RECEIVE_DP) {
      decode_dps_v3(ptr, len, dps);
    } else if (frame.code == FUN_RECEIVE_TIME_DP && len > 1) {
      uint8_t time_type = ptr[0];
      size_t skip = 1 + (time_type == 0 ? 4 : 13);
      if (skip < len) decode_dps_v3(ptr + skip, len - skip, dps);
    } else if (frame.code == FUN_RECEIVE_DP_V4 && len > 3) {
      decode_dps_v4(ptr + 3, len - 3, dps);
    } else if (frame.code == FUN_RECEIVE_TIME_DP_V4 && len > 4) {
      uint8_t time_type = ptr[3];
      size_t skip = 4 + (time_type == 0 ? 4 : 13);
      if (skip < len) decode_dps_v4(ptr + skip, len - skip, dps);
    }

    if (!dps.empty()) {
      ESP_LOGD(TAG, "[%s] Received %u DP(s)", active_device_->name().c_str(),
               static_cast<unsigned>(dps.size()));
      active_device_->apply_incoming_dps(dps);
    }

    // Send ACK response so device stops retrying the notification
    uint8_t iv[16];
    esp_fill_random(iv, sizeof(iv));
    auto ack = build_encrypted_packet(tx_seq_num_++, frame.seq_num, frame.code, {},
                                      SECURITY_FLAG_SESSION, session_key_, iv);
    auto chunks = fragment_gatt_packet(ack, protocol_version_, 20);
    bool was_empty = write_queue_.empty();
    for (auto &c : chunks) write_queue_.push_back(std::move(c));
    if (was_empty) flush_write_queue();
  }
}

}  // namespace tuya_ble_fan
}  // namespace esphome

#endif  // USE_ESP32
