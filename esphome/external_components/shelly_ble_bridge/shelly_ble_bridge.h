#pragma once

#include "esphome/core/component.h"
#include "esphome/core/defines.h"

#ifdef USE_ESP32

#include <esp_gap_ble_api.h>

#include <atomic>
#include <cstdint>
#include <string>
#include <vector>

#include "esphome/components/esp32_ble_tracker/esp32_ble_tracker.h"
#include "shelly_ble_protocol.h"
#include "shelly_ble_registry.h"

namespace esphome {
namespace shelly_ble_bridge {

struct ManagedShelly {
  std::string name;
  std::string mac_address;
  uint32_t device_id{0};
  uint8_t channel{0};
  ShellyBleKind kind{ShellyBleKind::SWITCH};
  std::string entity_id;

  bool has_state{false};
  uint8_t state_flags{0};
  uint8_t position{255};
  int8_t ble_rssi{-127};
  uint32_t last_seen_ms{0};
};

struct DetachedSwitchBinding {
  std::string name;
  std::string mac_address;
  uint32_t source_id{0};
  uint8_t input_channel{0};
  std::string target_fan_device_id;
  std::string target_light_entity_id;
};

class ShellyBleBridge : public Component, public esp32_ble_tracker::ESPBTClient {
 public:
  void set_parent(esp32_ble_tracker::ESP32BLETracker *parent) { parent_ = parent; }
  void set_network_key(const std::string &key) { network_key_ = key; }

  void add_shelly(const std::string &name, const std::string &mac_address, uint8_t channel,
                  ShellyBleKind kind, const std::string &entity_id);
  void add_detached_switch(const std::string &name, const std::string &mac_address,
                           uint8_t input_channel, const std::string &target_fan_device_id,
                           const std::string &target_light_entity_id);

  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::AFTER_BLUETOOTH; }

  // ESPBTClient interface (passive BLE scanner + GAP adv callback, zero GATT connections)
  bool parse_device(const esp32_ble_tracker::ESPBTDevice &device) override;
  void on_scan_end() override;
  bool gattc_event_handler(esp_gattc_cb_event_t event, esp_gattc_if_t gattc_if,
                           esp_ble_gattc_cb_param_t *param) override {
    return false;
  }
  void gap_event_handler(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param) override;
  void connect() override {}
  void disconnect() override {}

  // Enqueue a command from ESP-NOW (returns true if target_id is managed by this hub)
  bool enqueue_command(uint32_t device_id, uint8_t channel, uint8_t opcode, uint8_t arg,
                       uint8_t flags);
  std::vector<ShellyCachedState> get_cached_states() const;

 protected:
  enum class TxState : uint8_t {
    IDLE = 0,
    CONFIGURING,
    ADVERTISING,
  };

  static constexpr uint32_t TX_BURST_MS = 200;
  static constexpr uint32_t TX_GAP_MS = 20;
  static constexpr uint32_t TX_CONFIG_TIMEOUT_MS = 60;
  static constexpr uint32_t SCAN_RESTART_DELAY_MS = 2000;

  ManagedShelly *find_shelly(uint32_t device_id, uint8_t channel);
  bool handles_device(uint32_t device_id) const;
  void handle_state_beacon(const ShellyBleBeacon &beacon, int rssi);
  void handle_input_beacon(const ShellyBleBeacon &beacon, int rssi);
  void tick_tx(uint32_t now_ms);
  void start_next_tx(uint32_t now_ms);

  esp32_ble_tracker::ESP32BLETracker *parent_{nullptr};
  std::string network_key_{"cyd_espnow_default"};

  std::vector<ManagedShelly> shellys_;
  std::vector<DetachedSwitchBinding> detached_switches_;

  SeqDedupRing state_dedup_;
  SeqDedupRing input_dedup_;
  ShellyTxQueue tx_queue_;

  TxState tx_state_{TxState::IDLE};
  uint32_t tx_state_ms_{0};
  uint32_t last_tx_done_ms_{0};
  uint16_t next_seq_{1};
  std::atomic<bool> adv_raw_ready_{false};
  bool scan_kick_pending_{true};
  uint32_t last_scan_end_ms_{0};
};

}  // namespace shelly_ble_bridge
}  // namespace esphome

#endif  // USE_ESP32
