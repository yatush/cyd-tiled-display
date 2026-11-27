#pragma once

#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace esphome {
namespace tuya_ble_fan {

class TuyaBleFanDevice;

// Ordered from least progressive (0) to most progressive (4)
enum class BleConnStatus : uint8_t {
  DISCONNECTED = 0,
  SCANNING = 1,
  CONNECTING = 2,
  PAIRING = 3,
  CONNECTED = 4,
};

class TuyaBleFanRegistry {
 public:
  static TuyaBleFanRegistry &instance() {
    static TuyaBleFanRegistry inst;
    return inst;
  }

  void register_device(TuyaBleFanDevice *dev) {
    if (dev == nullptr) return;
    for (auto *existing : devices_) {
      if (existing == dev) return;
    }
    devices_.push_back(dev);
  }

  const std::vector<TuyaBleFanDevice *> &all_devices() const { return devices_; }

  void register_fan_entity(const std::string &entity_id, TuyaBleFanDevice *dev) {
    if (!entity_id.empty() && dev != nullptr) {
      fan_entities_[entity_id] = dev;
      register_device(dev);
    }
  }

  void register_light_entity(const std::string &entity_id, TuyaBleFanDevice *dev) {
    if (!entity_id.empty() && dev != nullptr) {
      light_entities_[entity_id] = dev;
      register_device(dev);
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

  void add_device_change_listener(std::function<void(TuyaBleFanDevice *)> cb) {
    if (cb) {
      device_change_listeners_.push_back(std::move(cb));
    }
  }

  void notify_device_changed(TuyaBleFanDevice *dev) {
    if (dev == nullptr) return;
    for (auto &cb : device_change_listeners_) {
      if (cb) cb(dev);
    }
  }

  bool handles_entity(const std::string &entity_or_key) const {
    const std::string base = base_entity(entity_or_key);
    return fan_entities_.count(base) > 0 || light_entities_.count(base) > 0;
  }

  void set_in_flight_connect_provider(std::function<bool()> provider) {
    in_flight_connect_provider_ = std::move(provider);
  }

  bool has_in_flight_connect() const {
    return in_flight_connect_provider_ ? in_flight_connect_provider_() : false;
  }

  bool get_connection_status(const std::string &entity_or_key, BleConnStatus &out) const;
  bool get_text_state(const std::string &key, std::string &out) const;
  bool get_binary_state(const std::string &key, bool &out) const;
  bool handle_action(const std::string &entity_id, const std::string &action,
                     const std::vector<std::pair<std::string, std::string>> &data) const;

 private:
  static std::string base_entity(const std::string &key) {
    size_t pos = key.find('|');
    return pos == std::string::npos ? key : key.substr(0, pos);
  }

  static std::string attr_name(const std::string &key) {
    size_t pos = key.find('|');
    return pos == std::string::npos ? "" : key.substr(pos + 1);
  }

  std::vector<TuyaBleFanDevice *> devices_;
  std::map<std::string, TuyaBleFanDevice *> fan_entities_;
  std::map<std::string, TuyaBleFanDevice *> light_entities_;
  std::function<void(const std::string &, const std::string &)> state_change_cb_;
  std::vector<std::function<void(TuyaBleFanDevice *)>> device_change_listeners_;
  std::function<bool()> in_flight_connect_provider_;
};

}  // namespace tuya_ble_fan
}  // namespace esphome
