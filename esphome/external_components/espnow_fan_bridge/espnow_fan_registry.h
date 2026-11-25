#pragma once

#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace esphome {
namespace espnow_fan_bridge {

// Mirrors tuya_ble_fan::BleConnStatus (0=DISCONNECTED..4=CONNECTED)
enum class RemoteBleConnStatus : uint8_t {
  DISCONNECTED = 0,
  SCANNING = 1,
  CONNECTING = 2,
  PAIRING = 3,
  CONNECTED = 4,
};

enum class EspNowDisplayMode : uint8_t {
  NONE = 0,                  // Not managed, or seamlessly falling back to HA
  ACTIVE = 1,                // Connected over ESP-NOW (show radio icon + Hub BLE status)
  OFFLINE_DISCONNECTED = 2,  // Both ESP-NOW and HA are unreachable (show gray radio + "disc")
};

struct RemoteFanState {
  std::string name;
  std::string fan_entity_id;
  std::string light_entity_id;
  uint32_t fan_key_hash{0};

  bool has_state{false};
  bool espnow_reachable{false};
  uint32_t last_seen_ms{0};
  RemoteBleConnStatus ble_status{RemoteBleConnStatus::DISCONNECTED};
  int8_t ble_rssi{-127};

  bool fan_on{false};
  uint8_t fan_speed{1};  // 1..6
  bool fan_reverse{false};
  uint8_t fan_preset{0};  // 0=fresh, 1=nature
  uint16_t fan_timer{0};  // 0..540

  bool light_on{false};
  uint16_t light_brightness{1000};  // 10..1000
  uint16_t light_color_temp{500};   // 0..1000

  int fan_percentage() const {
    if (!fan_on || fan_speed == 0) return 0;
    int pct = (static_cast<int>(fan_speed) * 100 + 3) / 6;
    return pct > 100 ? 100 : pct;
  }
};

class EspNowFanBridge;

class EspNowFanRegistry {
 public:
  static EspNowFanRegistry &instance() {
    static EspNowFanRegistry inst;
    return inst;
  }

  void set_bridge(EspNowFanBridge *bridge) { bridge_ = bridge; }
  EspNowFanBridge *bridge() const { return bridge_; }

  void register_remote_fan(RemoteFanState *fan) {
    if (fan == nullptr) return;
    if (!fan->fan_entity_id.empty()) {
      fan_entities_[fan->fan_entity_id] = fan;
    }
    if (!fan->light_entity_id.empty()) {
      light_entities_[fan->light_entity_id] = fan;
    }
  }

  void set_state_change_callback(std::function<void(const std::string &, const std::string &)> cb) {
    state_change_cb_ = std::move(cb);
  }

  void notify_state_changed(const std::string &key, const std::string &value) {
    if (state_change_cb_) {
      state_change_cb_(key, value);
    }
  }

  void set_redraw_callback(std::function<void()> cb) { redraw_cb_ = std::move(cb); }

  void notify_redraw() {
    if (redraw_cb_) {
      redraw_cb_();
    }
  }

  bool handles_entity(const std::string &entity_or_key) const {
    const std::string base = base_entity(entity_or_key);
    return fan_entities_.count(base) > 0 || light_entities_.count(base) > 0;
  }

  // Returns whether this entity's ESP-NOW hub is reachable or should show 'no hub'
  EspNowDisplayMode get_display_mode(const std::string &entity_or_key, bool /*ha_connected*/,
                                     RemoteBleConnStatus &out_ble_status) const {
    const RemoteFanState *fan = find_fan(entity_or_key);
    if (fan == nullptr) return EspNowDisplayMode::NONE;
    if (fan->espnow_reachable) {
      out_ble_status = fan->ble_status;
      return EspNowDisplayMode::ACTIVE;
    }
    out_ble_status = RemoteBleConnStatus::DISCONNECTED;
    return EspNowDisplayMode::OFFLINE_DISCONNECTED;
  }

  bool get_text_state(const std::string &key, bool ha_connected, std::string &out) const {
    const std::string base = base_entity(key);
    const std::string attr = attr_name(key);

    auto fit = fan_entities_.find(base);
    if (fit != fan_entities_.end()) {
      const RemoteFanState *f = fit->second;
      if (!f->has_state || (!f->espnow_reachable && ha_connected)) return false;
      if (attr.empty()) {
        out = f->fan_on ? "on" : "off";
        return true;
      }
      if (attr == "percentage") {
        out = std::to_string(f->fan_percentage());
        return true;
      }
      if (attr == "direction") {
        out = f->fan_reverse ? "reverse" : "forward";
        return true;
      }
      if (attr == "preset_mode") {
        out = f->fan_preset == 1 ? "nature" : "fresh";
        return true;
      }
      return false;
    }

    auto lit = light_entities_.find(base);
    if (lit != light_entities_.end()) {
      const RemoteFanState *f = lit->second;
      if (!f->has_state || (!f->espnow_reachable && ha_connected)) return false;
      if (attr.empty()) {
        out = f->light_on ? "on" : "off";
        return true;
      }
      if (attr == "brightness") {
        int b255 = f->light_on ? ((static_cast<int>(f->light_brightness) * 255 + 500) / 1000) : 0;
        out = std::to_string(b255);
        return true;
      }
      if (attr == "color_temp_kelvin") {
        int k = 2700 + ((static_cast<int>(f->light_color_temp) * (6500 - 2700) + 500) / 1000);
        out = std::to_string(k);
        return true;
      }
      return false;
    }

    return false;
  }

  bool get_binary_state(const std::string &key, bool ha_connected, bool &out) const {
    const std::string base = base_entity(key);
    auto fit = fan_entities_.find(base);
    if (fit != fan_entities_.end()) {
      const RemoteFanState *f = fit->second;
      if (!f->has_state || (!f->espnow_reachable && ha_connected)) return false;
      out = f->fan_on;
      return true;
    }
    auto lit = light_entities_.find(base);
    if (lit != light_entities_.end()) {
      const RemoteFanState *f = lit->second;
      if (!f->has_state || (!f->espnow_reachable && ha_connected)) return false;
      out = f->light_on;
      return true;
    }
    return false;
  }

  bool handle_action(const std::string &entity_id, const std::string &action,
                     const std::vector<std::pair<std::string, std::string>> &data,
                     bool ha_connected) const;

 private:
  const RemoteFanState *find_fan(const std::string &entity_or_key) const {
    const std::string base = base_entity(entity_or_key);
    auto fit = fan_entities_.find(base);
    if (fit != fan_entities_.end()) return fit->second;
    auto lit = light_entities_.find(base);
    if (lit != light_entities_.end()) return lit->second;
    return nullptr;
  }

  static std::string base_entity(const std::string &key) {
    size_t pos = key.find('|');
    return pos == std::string::npos ? key : key.substr(0, pos);
  }

  static std::string attr_name(const std::string &key) {
    size_t pos = key.find('|');
    return pos == std::string::npos ? "" : key.substr(pos + 1);
  }

  EspNowFanBridge *bridge_{nullptr};
  std::map<std::string, RemoteFanState *> fan_entities_;
  std::map<std::string, RemoteFanState *> light_entities_;
  std::function<void(const std::string &, const std::string &)> state_change_cb_;
  std::function<void()> redraw_cb_;
};

}  // namespace espnow_fan_bridge
}  // namespace esphome
