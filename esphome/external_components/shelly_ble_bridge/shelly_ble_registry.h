#pragma once

#include <cstdint>
#include <functional>
#include <string>
#include <vector>

namespace esphome {
namespace shelly_ble_bridge {

struct ShellyCachedState {
  uint32_t device_id{0};
  uint8_t channel{0};
  uint8_t kind{1};  // 1=SWITCH, 2=COVER
  uint8_t state_flags{0};
  uint8_t position{255};
  int8_t ble_rssi{-127};
  bool has_state{false};
};

// Lightweight decoupled bridge between espnow_fan_bridge (hub role) and shelly_ble_bridge
class ShellyBleBridgeRegistry {
 public:
  using CmdHandler = std::function<bool(uint32_t device_id, uint8_t channel, uint8_t opcode,
                                        uint8_t arg, uint8_t flags, uint16_t cmd_seq)>;
  using DevicePredicate = std::function<bool(uint32_t device_id)>;
  using StateCallback = std::function<void(const ShellyCachedState &)>;
  using SnapshotProvider = std::function<std::vector<ShellyCachedState>()>;
  using RemoteLightToggleHandler =
      std::function<bool(const std::string &target_fan_device_id,
                         const std::string &target_light_entity_id, uint32_t source_id,
                         uint16_t source_seq)>;

  static ShellyBleBridgeRegistry &instance() {
    static ShellyBleBridgeRegistry inst;
    return inst;
  }

  void set_cmd_handler(CmdHandler handler) { cmd_handler_ = std::move(handler); }
  void set_device_predicate(DevicePredicate pred) { device_predicate_ = std::move(pred); }
  void set_state_callback(StateCallback cb) { state_cb_ = std::move(cb); }
  void set_snapshot_provider(SnapshotProvider provider) { snapshot_provider_ = std::move(provider); }
  void set_remote_light_toggle_handler(RemoteLightToggleHandler handler) {
    remote_light_toggle_handler_ = std::move(handler);
  }

  bool handles_device(uint32_t device_id) const {
    if (!device_predicate_) return false;
    return device_predicate_(device_id);
  }

  bool enqueue_command(uint32_t device_id, uint8_t channel, uint8_t opcode, uint8_t arg,
                       uint8_t flags, uint16_t cmd_seq = 0) const {
    if (!cmd_handler_) return false;
    return cmd_handler_(device_id, channel, opcode, arg, flags, cmd_seq);
  }

  void notify_state_updated(const ShellyCachedState &st) const {
    if (state_cb_) {
      state_cb_(st);
    }
  }

  std::vector<ShellyCachedState> all_cached_states() const {
    if (!snapshot_provider_) return {};
    return snapshot_provider_();
  }

  bool toggle_remote_light(const std::string &target_fan_device_id,
                           const std::string &target_light_entity_id, uint32_t source_id,
                           uint16_t source_seq) const {
    if (!remote_light_toggle_handler_) return false;
    return remote_light_toggle_handler_(target_fan_device_id, target_light_entity_id, source_id,
                                        source_seq);
  }

 private:
  CmdHandler cmd_handler_;
  DevicePredicate device_predicate_;
  StateCallback state_cb_;
  SnapshotProvider snapshot_provider_;
  RemoteLightToggleHandler remote_light_toggle_handler_;
};

}  // namespace shelly_ble_bridge
}  // namespace esphome
