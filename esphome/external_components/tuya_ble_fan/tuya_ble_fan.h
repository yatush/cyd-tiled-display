#pragma once

#include "esphome/core/component.h"
#include "esphome/core/defines.h"
#include "esphome/core/preferences.h"

#ifdef USE_ESP32

#include <esp_gap_ble_api.h>
#include <esp_gattc_api.h>

#include <cstdint>
#include <deque>
#include <string>
#include <vector>

#include "esphome/components/esp32_ble_tracker/esp32_ble_tracker.h"
#include "esphome/components/fan/fan.h"
#include "esphome/components/light/light_output.h"
#include "esphome/components/light/light_state.h"
#include "esphome/components/number/number.h"
#include "esphome/components/sensor/sensor.h"
#ifdef USE_API_CUSTOM_SERVICES
#include "esphome/components/api/custom_api_device.h"
#endif
#include "tuya_ble_fan_registry.h"
#include "tuya_ble_protocol.h"

namespace esphome {
namespace tuya_ble_fan {

class TuyaBleFanHub;
class TuyaBleFanDevice;

// Native ESPHome Fan entity backed by a TuyaBleFanDevice
class TuyaBleFanEntity : public fan::Fan {
 public:
  explicit TuyaBleFanEntity(TuyaBleFanDevice *parent) : parent_(parent) {}
  fan::FanTraits get_traits() override;
  void control(const fan::FanCall &call) override;
  void sync_from_device();

 private:
  TuyaBleFanDevice *parent_;
};

// Native ESPHome LightOutput backed by a TuyaBleFanDevice
class TuyaBleLightOutput : public light::LightOutput {
 public:
  explicit TuyaBleLightOutput(TuyaBleFanDevice *parent) : parent_(parent) {}
  light::LightTraits get_traits() override;
  void write_state(light::LightState *state) override;
  void set_light_state(light::LightState *state) { light_state_ = state; }
  void sync_from_device();

 private:
  TuyaBleFanDevice *parent_;
  light::LightState *light_state_{nullptr};
  bool syncing_{false};
  bool in_write_state_{false};
  bool initial_write_skipped_{false};
};

// Native ESPHome Number entity for FlyFan timer (DP 64: 0..540 minutes)
class TuyaBleTimerNumber : public number::Number {
 public:
  explicit TuyaBleTimerNumber(TuyaBleFanDevice *parent) : parent_(parent) {}
  void control(float value) override;
  void sync_from_device();

 private:
  TuyaBleFanDevice *parent_;
};

// Represents one physical Tuya FlyFan ceiling receiver
class TuyaBleFanDevice {
 public:
  void set_hub(TuyaBleFanHub *hub) { hub_ = hub; }
  void set_name(const std::string &name) { name_ = name; }
  void set_device_id(const std::string &device_id) { device_id_ = device_id; }
  void set_local_key(const std::string &local_key) { local_key_ = local_key; }
  void set_product_id(const std::string &product_id) { product_id_ = product_id; }
  void set_uuid(const std::string &uuid) { uuid_ = uuid; }
  void set_mac_address(uint64_t mac) { mac_address_ = mac; }
  void set_fan_entity_id(const std::string &id) { fan_entity_id_ = id; }
  void set_light_entity_id(const std::string &id) { light_entity_id_ = id; }

  void set_fan_entity(TuyaBleFanEntity *entity) { fan_entity_ = entity; }
  void set_light_output(TuyaBleLightOutput *output) { light_output_ = output; }
  void set_timer_number(TuyaBleTimerNumber *num) { timer_number_ = num; }

  void setup();

  const std::string &name() const { return name_; }
  const std::string &device_id() const { return device_id_; }
  const std::string &local_key() const { return local_key_; }
  const std::string &product_id() const { return product_id_; }
  const std::string &uuid() const { return uuid_; }
  const std::string &fan_entity_id() const { return fan_entity_id_; }
  const std::string &light_entity_id() const { return light_entity_id_; }

  uint64_t mac_address() const { return mac_address_; }
  esp_ble_addr_type_t addr_type() const { return addr_type_; }
  bool has_mac() const { return mac_address_ != 0; }
  void update_discovered_mac(uint64_t mac, esp_ble_addr_type_t addr_type);
  void update_discovered_identity(uint64_t mac, esp_ble_addr_type_t addr_type, const std::string &uuid);

  // Live state getters
  bool fan_on() const { return fan_on_; }
  int fan_speed() const { return fan_speed_; }            // 1..6
  int fan_percentage() const;                             // 0..100
  bool fan_reverse() const { return fan_reverse_; }
  uint8_t fan_preset() const { return fan_preset_; }      // 0=fresh, 1=nature
  int fan_timer() const { return fan_timer_; }            // 0..540
  bool light_on() const { return light_on_; }
  int light_brightness() const { return light_brightness_; }   // 10..1000
  int light_color_temp() const { return light_color_temp_; }   // 0..1000

  // Local control API (updates optimistic state, queues BLE DPs, notifies HA & CYD UI)
  void set_fan_power(bool on);
  void set_fan_speed(int speed_1_to_6);
  void set_fan_percentage(int pct);
  void set_fan_direction(bool reverse);
  void set_fan_preset(uint8_t preset);
  void set_fan_timer(int minutes);

  void set_light_power(bool on);
  void set_light_brightness(int brightness_10_to_1000);
  void set_light_color_temp(int color_temp_0_to_1000);
  void set_light_state(bool on, int brightness_10_to_1000, int color_temp_0_to_1000);

  void set_rssi_sensor(sensor::Sensor *sensor) { rssi_sensor_ = sensor; }
  void publish_rssi(int rssi);
  void clear_rssi();

  // Incoming DP updates from BLE device
  void apply_incoming_dps(const std::vector<TuyaDp> &dps);

  // Pending DP queue managed by Hub
  bool has_pending_dps() const { return !pending_dps_.empty() || !followup_dps_.empty(); }
  std::vector<TuyaDp> take_pending_dps();
  std::vector<TuyaDp> take_followup_dps();
  void queue_dps(const std::vector<TuyaDp> &dps);

 protected:
  struct CachedBleIdentity {
    uint64_t mac;
    uint8_t addr_type;
    char uuid[17];
  };

  void notify_fan_changed();
  void notify_light_changed();
  void notify_timer_changed();

  TuyaBleFanHub *hub_{nullptr};
  std::string name_;
  std::string device_id_;
  std::string local_key_;
  std::string product_id_;
  std::string uuid_;
  std::string fan_entity_id_;
  std::string light_entity_id_;

  uint64_t mac_address_{0};
  esp_ble_addr_type_t addr_type_{BLE_ADDR_TYPE_PUBLIC};
  ESPPreferenceObject identity_pref_;

  // Fan state
  bool fan_on_{false};
  int fan_speed_{1};        // 1..6
  bool fan_reverse_{false};
  uint8_t fan_preset_{0};   // 0=fresh, 1=nature
  int fan_timer_{0};        // 0..540

  // Light state
  bool light_on_{false};
  int light_brightness_{1000};
  int light_color_temp_{500};

  // Pending DPs coalesced by DP ID
  std::vector<TuyaDp> pending_dps_;
  std::vector<TuyaDp> followup_dps_;

  // Optional native HA entities
  TuyaBleFanEntity *fan_entity_{nullptr};
  TuyaBleLightOutput *light_output_{nullptr};
  TuyaBleTimerNumber *timer_number_{nullptr};
  sensor::Sensor *rssi_sensor_{nullptr};
};

// Single-slot BLE GATT hub managing 1 or more TuyaBleFanDevice instances
class TuyaBleFanHub : public Component,
#ifdef USE_API_CUSTOM_SERVICES
                      public api::CustomAPIDevice,
#endif
                      public esp32_ble_tracker::ESPBTClient {
 public:
  void set_parent(esp32_ble_tracker::ESP32BLETracker *parent) { parent_ = parent; }
  void set_idle_disconnect_s(uint32_t seconds) { idle_disconnect_s_ = seconds; }
  void add_fan(TuyaBleFanDevice *fan) { fans_.push_back(fan); }

  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::AFTER_BLUETOOTH; }

  // ESPBTClient interface
  bool parse_device(const esp32_ble_tracker::ESPBTDevice &device) override;
  void on_scan_end() override;
  bool gattc_event_handler(esp_gattc_cb_event_t event, esp_gatt_if_t gattc_if,
                           esp_ble_gattc_cb_param_t *param) override;
  void gap_event_handler(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param) override;
  void connect() override;
  void disconnect() override;
  void ble_before_disabled_event_handler() override;

  void request_activity(TuyaBleFanDevice *device);

  // On-demand Native API services (zero idle RAM overhead)
  void on_scan_service(int duration_s);
  void on_pair_service(std::string mac, int addr_type, std::string uuid,
                       std::string device_id, std::string local_key, bool blink_confirm);

 protected:
  enum class SessionState : uint8_t {
    IDLE = 0,
    SCANNING,
    CONNECTING,
    DISCOVERING,
    ENABLING_NOTIFY,
    HANDSHAKE_DEVICE_INFO,
    HANDSHAKE_PAIR,
    READY,
    DISCONNECTING,
  };

  struct ProbeCandidate {
    uint64_t mac{0};
    esp_ble_addr_type_t addr_type{BLE_ADDR_TYPE_PUBLIC};
    std::string uuid;
  };

  struct ScanSighting {
    uint64_t mac{0};
    int rssi{-127};
  };

  struct UnboundPairJob {
    bool active{false};
    bool waiting_disconnect{false};
    uint64_t mac{0};
    esp_ble_addr_type_t addr_type{BLE_ADDR_TYPE_PUBLIC};
    std::string mac_str;
    std::string uuid;
    std::string device_id;
    std::string local_key;
    bool blink_confirm{true};
    bool blink_sent_on{false};
    uint32_t blink_on_ms{0};
    bool blink_sent_off{false};
    uint32_t blink_off_ms{0};
  };

  bool is_persistent_mode() const { return fans_.size() == 1 && idle_disconnect_s_ == 0; }
  void start_bounded_scan();
  void stop_scan_if_running();
  void finish_discovery_scan();
  void start_connect(TuyaBleFanDevice *device);
  void start_probe(TuyaBleFanDevice *device, const ProbeCandidate &candidate);
  void start_unbound_pair_connect();
  void finish_unbound_pair(bool ok, const std::string &error);
  bool find_next_probe_candidate(TuyaBleFanDevice *device, ProbeCandidate &out) const;
  void record_probe_failure();
  void disconnect_current();
  void reset_session();

  void send_device_info_request();
  void send_pair_request();
  void send_device_status_request();
  void send_dps(const std::vector<TuyaDp> &dps);
  void flush_device_dps(TuyaBleFanDevice *device);
  void enqueue_gatt_packet(uint16_t code, const std::vector<uint8_t> &payload, uint8_t security_flag);
  void flush_write_queue();
  void handle_decrypted_frame(const TuyaDecryptedFrame &frame);
  void emit_ha_event(const std::string &event_name, const std::map<std::string, std::string> &data);

  TuyaBleFanDevice *pick_next_device_with_work();

  std::vector<TuyaBleFanDevice *> fans_;
  uint32_t idle_disconnect_s_{30};

  esp_gatt_if_t gattc_if_{ESP_GATT_IF_NONE};
  uint16_t conn_id_{0};
  bool has_conn_id_{false};
  esp_bd_addr_t remote_bda_{0};

  SessionState session_state_{SessionState::IDLE};
  TuyaBleFanDevice *active_device_{nullptr};
  TuyaBleFanDevice *pending_switch_device_{nullptr};

  std::vector<ProbeCandidate> probe_candidates_;
  std::vector<std::pair<TuyaBleFanDevice *, uint64_t>> failed_probes_;
  bool is_probing_{false};
  ProbeCandidate active_probe_{};

  // Transient on-demand discovery scan state (cleared when scan ends)
  bool discovery_scan_active_{false};
  uint32_t discovery_scan_end_ms_{0};
  std::vector<ScanSighting> discovery_sightings_;

  // Transient unbound pairing job state
  UnboundPairJob pair_job_{};

  uint16_t write_char_handle_{0};
  uint16_t notify_char_handle_{0};
  uint16_t notify_cccd_handle_{0};

  uint8_t login_key_[16]{0};
  uint8_t session_key_[16]{0};
  bool has_session_key_{false};
  uint8_t protocol_version_{3};
  uint32_t tx_seq_num_{1};
  uint16_t dp_seq_num_{1};

  GattPacketReassembler reassembler_;
  std::deque<std::vector<uint8_t>> write_queue_;

  uint32_t state_entered_ms_{0};
  uint32_t last_activity_ms_{0};
  uint32_t last_rssi_poll_ms_{0};
  uint32_t next_reconnect_ms_{0};
  uint32_t reconnect_backoff_ms_{2000};
  bool scan_active_{false};
};

}  // namespace tuya_ble_fan
}  // namespace esphome

#endif  // USE_ESP32
