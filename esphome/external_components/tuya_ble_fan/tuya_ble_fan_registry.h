#pragma once

#include <functional>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace esphome {
namespace tuya_ble_fan {

class TuyaBleFanDevice;

class TuyaBleFanRegistry {
 public:
  static TuyaBleFanRegistry &instance() {
    static TuyaBleFanRegistry inst;
    return inst;
  }

  void register_fan_entity(const std::string &entity_id, TuyaBleFanDevice *dev) {
    if (!entity_id.empty() && dev != nullptr) {
      fan_entities_[entity_id] = dev;
    }
  }

  void register_light_entity(const std::string &entity_id, TuyaBleFanDevice *dev) {
    if (!entity_id.empty() && dev != nullptr) {
      light_entities_[entity_id] = dev;
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

  bool handles_entity(const std::string &entity_or_key) const {
    const std::string base = base_entity(entity_or_key);
    return fan_entities_.count(base) > 0 || light_entities_.count(base) > 0;
  }

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

  std::map<std::string, TuyaBleFanDevice *> fan_entities_;
  std::map<std::string, TuyaBleFanDevice *> light_entities_;
  std::function<void(const std::string &, const std::string &)> state_change_cb_;
};

}  // namespace tuya_ble_fan
}  // namespace esphome
