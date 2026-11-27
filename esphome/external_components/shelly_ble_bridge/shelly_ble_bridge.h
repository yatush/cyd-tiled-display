#pragma once

#include "esphome/core/component.h"
#include "esphome/core/defines.h"

#ifdef USE_ESP32

#include <esp_gap_ble_api.h>

#include <atomic>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

#include "esphome/components/esp32_ble_tracker/esp32_ble_tracker.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/core/preferences.h"
#include "shelly_ble_protocol.h"
#include "shelly_ble_registry.h"

#ifdef USE_API_CUSTOM_SERVICES
#include "esphome/components/api/custom_api_device.h"
#endif

namespace esphome {
namespace shelly_ble_bridge {

struct ManagedShelly {
  std::string name;
  std::string mac_address;
  uint32_t device_id{0};
  uint8_t channel{0};
  ShellyBleKind kind{ShellyBleKind::SWITCH};
  std::string entity_id;
  bool static_configured{false};

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

class ShellyBleBridge : public Component,
#ifdef USE_API_CUSTOM_SERVICES
                        public api::CustomAPIDevice,
#endif
                        public esp32_ble_tracker::ESPBTClient {
 public:
  void set_parent(esp32_ble_tracker::ESP32BLETracker *parent) { parent_ = parent; }
  void set_network_key(const std::string &key) { network_key_ = key; }
  void set_visible_shellys_sensor(text_sensor::TextSensor *sensor) {
    visible_shellys_sensor_ = sensor;
  }

  void add_known_name(const std::string &mac_address, const std::string &name);
  void add_shelly(const std::string &name, const std::string &mac_address, uint8_t channel,
                  ShellyBleKind kind, const std::string &entity_id);
  void add_detached_switch(const std::string &name, const std::string &mac_address,
                           uint8_t input_channel, const std::string &target_fan_device_id,
                           const std::string &target_light_entity_id);
  void on_sync_detached_switches(std::string rules);

  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::AFTER_BLUETOOTH; }

  // ESPBTClient interface (passive BLE scanner + GAP adv callback, zero GATT connections)
  bool parse_device(const esp32_ble_tracker::ESPBTDevice &device) override;
  void on_scan_end() override;
  bool gattc_event_handler(esp_gattc_cb_event_t event, esp_gatt_if_t gattc_if,
                           esp_ble_gattc_cb_param_t *param) override {
    return false;
  }
  void gap_event_handler(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param) override;
  void connect() override {}
  void disconnect() override {}

  // Enqueue a command from ESP-NOW (returns true if target_id is in BLE range / managed)
  bool enqueue_command(uint32_t device_id, uint8_t channel, uint8_t opcode, uint8_t arg,
                       uint8_t flags, uint16_t cmd_seq = 0);
  std::vector<ShellyCachedState> get_cached_states() const;

 protected:
  enum class TxState : uint8_t {
    IDLE = 0,
    CONFIGURING,
    ADVERTISING,
  };

  struct PersistedDetachedBlob {
    uint8_t valid{0};
    char data[1023]{};
  };

  static constexpr uint32_t TX_BURST_MS = 200;
  static constexpr uint32_t TX_GAP_MS = 20;
  static constexpr uint32_t TX_CONFIG_TIMEOUT_MS = 60;
  static constexpr uint32_t SCAN_RESTART_DELAY_MS = 2000;
  static constexpr uint32_t DEDUP_TTL_MS = 5000;
  static constexpr uint32_t SHELLY_BLE_STALE_MS = 120000;
  static constexpr uint32_t VISIBLE_PUBLISH_INTERVAL_MS = 30000;
  static constexpr size_t MAX_DYNAMIC_SHELLYS = 32;

  void apply_detached_switches_blob(const std::string &rules);
  std::string resolve_display_name(uint32_t device_id, const std::string &ble_name) const;
  ManagedShelly *find_shelly(uint32_t device_id, uint8_t channel);
  ManagedShelly *find_or_create_shelly(uint32_t device_id, uint8_t channel, ShellyBleKind kind,
                                       uint32_t now_ms, const std::string &ble_name);
  bool handles_device(uint32_t device_id) const;
  void handle_state_beacon(const ShellyBleBeacon &beacon, int rssi, const std::string &ble_name);
  void handle_input_beacon(const ShellyBleBeacon &beacon, int rssi);
  void publish_visible_shellys(uint32_t now_ms, bool force = false);
  void tick_tx(uint32_t now_ms);
  void start_next_tx(uint32_t now_ms);

  esp32_ble_tracker::ESP32BLETracker *parent_{nullptr};
  text_sensor::TextSensor *visible_shellys_sensor_{nullptr};
  std::string network_key_{"cyd_espnow_default"};

  std::unordered_map<uint32_t, std::string> known_names_;
  std::vector<ManagedShelly> shellys_;
  std::vector<DetachedSwitchBinding> detached_switches_;
  ESPPreferenceObject detached_pref_;

  SeqDedupRing state_dedup_;
  SeqDedupRing input_dedup_;
  ShellyTxQueue tx_queue_;

  TxState tx_state_{TxState::IDLE};
  uint32_t tx_state_ms_{0};
  uint32_t last_tx_done_ms_{0};
  uint16_t next_seq_{1};
  std::atomic<bool> adv_raw_ready_{false};
  uint32_t last_scan_check_ms_{0};
  uint32_t last_visible_publish_ms_{0};
  std::string last_visible_summary_;
};

}  // namespace shelly_ble_bridge
}  // namespace esphome

#endif  // USE_ESP32
