#pragma once

#include "esphome/core/component.h"
#include "esphome/core/defines.h"

#ifdef USE_ESP32

#include <esp_event.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <freertos/FreeRTOS.h>
#include <freertos/portmacro.h>

#include <array>
#include <atomic>
#include <cstdint>
#include <deque>
#include <string>
#include <utility>
#include <vector>

#include "esphome/components/sensor/sensor.h"
#include "espnow_fan_registry.h"
#include "espnow_protocol.h"

#ifdef USE_TUYA_BLE_FAN
#include "esphome/components/tuya_ble_fan/tuya_ble_fan.h"
#endif

#ifdef USE_SHELLY_BLE_BRIDGE
#include "esphome/components/shelly_ble_bridge/shelly_ble_registry.h"
#endif

namespace esphome {
namespace espnow_fan_bridge {

class EspNowFanBridge : public Component {
 public:
  void set_role(BridgeRole role) { role_ = role; }
  void set_network_key(const std::string &key) { network_key_ = key; }
  void set_fallback_channel(uint8_t ch) {
    fallback_channel_ = ch < 1 ? 1 : (ch > 13 ? 13 : ch);
    hunt_.set_fallback_channel(fallback_channel_);
  }
  void set_udp_port(uint16_t port) { udp_port_ = port; }
  void set_channel_sensor(sensor::Sensor *sensor) { channel_sensor_ = sensor; }

  // CYD role: register a remote fan hosted on a headless hub
  void add_remote_fan(const std::string &name, const std::string &fan_entity_id,
                      const std::string &light_entity_id);

  // CYD role: register a backup-enabled Shelly entity reachable via headless hubs
  void add_remote_shelly(const std::string &name, const std::string &mac_address, uint8_t channel,
                         bool is_cover, const std::string &entity_id);

  void setup() override;
  void loop() override;
  void dump_config() override;
  // Run after Wi-Fi is initialized so esp_now_init() succeeds cleanly
  float get_setup_priority() const override { return setup_priority::AFTER_WIFI; }

  // CYD role: dispatch an action from PerformHaAction()
  bool send_fan_action(RemoteFanState *fan, bool is_light, const std::string &action,
                       const std::vector<std::pair<std::string, std::string>> &data);
  bool send_shelly_action(RemoteShellyState *sh, const std::string &action,
                          const std::vector<std::pair<std::string, std::string>> &data);

 protected:
  struct RxPacket {
    std::array<uint8_t, 6> src_mac{};
    uint8_t rx_channel{0};
    std::vector<uint8_t> data;
  };

  struct PeerInfo {
    std::array<uint8_t, 6> mac{};
    BridgeRole role{BridgeRole::CYD};
    uint8_t channel{1};
    uint32_t last_seen_ms{0};
  };

  struct PendingCmd {
    uint16_t seq{0};
    uint32_t origin_override{0};
    CmdPayload cmd{};
    uint32_t fan_key_hash{0};
    uint32_t created_ms{0};
    uint32_t last_tx_ms{0};
    uint8_t attempts{0};
  };

  struct PendingShellyCmd {
    uint16_t seq{0};
    uint32_t origin_override{0};
    ShellyCmdPayload cmd{};
    uint32_t created_ms{0};
    uint32_t last_tx_ms{0};
    uint8_t attempts{0};
  };

  struct PendingRelay {
    std::vector<uint8_t> frame;
    uint32_t send_at_ms{0};
  };

  static constexpr uint32_t SWEEP_DWELL_MS = 30;
  static constexpr uint32_t SWEEP_INTERVAL_MS = 30000;
  static constexpr uint32_t ROUND_ROBIN_DWELL_MS = 250;
  static constexpr uint32_t HEARTBEAT_INTERVAL_MS = 15000;
  static constexpr uint32_t PEER_TIMEOUT_MS = 65000;
  static constexpr uint32_t CMD_RETRY_INTERVAL_MS = 300;
  static constexpr uint8_t CMD_MAX_ATTEMPTS = 10;  // ~3.0s total retry window (supports 5-hop RTT)
  static constexpr uint32_t RELAY_DEDUP_TTL_MS = 5000;
  static constexpr size_t MAX_PENDING_RELAYS = 24;

  static EspNowFanBridge *active_instance_;
  static void espnow_recv_cb(const esp_now_recv_info_t *recv_info, const uint8_t *data, int len);
  static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id,
                                 void *event_data);

  void ensure_espnow_initialized();
  bool ensure_broadcast_peer();
  void ensure_udp_initialized();
  void close_udp();
  bool send_udp_broadcast(const std::vector<uint8_t> &frame);
  void poll_udp_rx();
  uint8_t current_wifi_channel() const;
  void set_radio_channel(uint8_t ch);
  void publish_channel_if_changed(bool force = false);

  bool broadcast_frame(MsgType type, uint16_t seq, const std::vector<uint8_t> &payload,
                       uint8_t ttl = DEFAULT_RELAY_TTL, uint8_t hop_nonce = 0,
                       uint32_t origin_override = 0);
  void send_ping();
  void send_pong(uint16_t req_seq);
  void send_sync_req();

  void process_rx_packet(const RxPacket &pkt);
  void upsert_peer(const std::array<uint8_t, 6> &mac, BridgeRole role, uint8_t ch, uint32_t now_ms);

  // Hub-side relay & cross-hub helpers
  void hub_schedule_relay(const FrameHeader &hdr, const std::vector<uint8_t> &payload,
                          uint32_t now_ms);
  void hub_tick_relays(uint32_t now_ms);
  bool hub_send_remote_light_toggle(const std::string &target_fan_device_id,
                                    const std::string &target_light_entity_id, uint32_t source_id,
                                    uint16_t source_seq);

  // Hub-side device helpers
#ifdef USE_TUYA_BLE_FAN
  bool hub_handle_cmd(const CmdPayload &cmd, uint32_t origin_id, uint16_t seq, uint32_t now_ms);
  void hub_broadcast_device_state(tuya_ble_fan::TuyaBleFanDevice *dev);
  void hub_broadcast_all_states();
  tuya_ble_fan::TuyaBleFanDevice *hub_find_device(uint32_t fan_key_hash);
#endif

#ifdef USE_SHELLY_BLE_BRIDGE
  bool hub_handle_shelly_cmd(const ShellyCmdPayload &cmd, uint32_t origin_id, uint16_t seq,
                             uint32_t now_ms);
  void hub_broadcast_shelly_state(const shelly_ble_bridge::ShellyCachedState &st);
  void hub_broadcast_all_shelly_states();
#endif

  // CYD-side helpers (and shared ACK/retry handling)
  void cyd_handle_state(const StatePayload &st, uint32_t now_ms);
  void cyd_handle_shelly_state(const ShellyStatePayload &st, uint32_t now_ms);
  void cyd_handle_ack(const AckPayload &ack, uint32_t now_ms);
  void cyd_tick_pending_cmds(uint32_t now_ms);
  RemoteFanState *cyd_find_remote_fan(uint32_t fan_key_hash);
  RemoteShellyState *cyd_find_remote_shelly(uint32_t device_id, uint8_t channel);
  void cyd_queue_cmd(const CmdPayload &cmd, uint32_t now_ms);
  void cyd_queue_shelly_cmd(const ShellyCmdPayload &cmd, uint32_t now_ms);

  BridgeRole role_{BridgeRole::CYD};
  std::string network_key_{"cyd_espnow_default"};
  uint8_t fallback_channel_{1};
  uint16_t udp_port_{42110};
  int udp_sock_{-1};
  sensor::Sensor *channel_sensor_{nullptr};

  bool espnow_ready_{false};
  uint32_t local_origin_id_{0};
  uint8_t last_published_channel_{0};
  uint16_t next_seq_{1};

  std::atomic<bool> wifi_connected_{false};
  std::atomic<bool> has_ip_{false};
  std::atomic<bool> wifi_event_dirty_{false};
  std::atomic<bool> wifi_scan_done_flag_{false};

  ChannelHuntState hunt_{1};
  uint32_t last_sweep_ms_{0};
  uint32_t last_heartbeat_ms_{0};
  uint32_t last_channel_poll_ms_{0};
  uint8_t tuned_offline_channel_{0};

  portMUX_TYPE rx_mux_ = portMUX_INITIALIZER_UNLOCKED;
  std::deque<RxPacket> rx_queue_;

  FrameDedupRing relay_dedup_;
  FrameDedupRing cmd_exec_dedup_;
  std::deque<PendingRelay> pending_relays_;

  std::vector<PeerInfo> peers_;
  std::vector<RemoteFanState> remote_fans_;
  std::vector<RemoteShellyState> remote_shellys_;
  std::vector<PendingCmd> pending_cmds_;
  std::vector<PendingShellyCmd> pending_shelly_cmds_;
  bool ui_dirty_{false};
};

}  // namespace espnow_fan_bridge
}  // namespace esphome

#endif  // USE_ESP32
