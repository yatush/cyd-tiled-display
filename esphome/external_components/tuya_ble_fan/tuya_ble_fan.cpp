#include "tuya_ble_fan_internal.h"

#ifdef USE_ESP32

namespace esphome {
namespace tuya_ble_fan {

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


}  // namespace tuya_ble_fan
}  // namespace esphome

#endif  // USE_ESP32
