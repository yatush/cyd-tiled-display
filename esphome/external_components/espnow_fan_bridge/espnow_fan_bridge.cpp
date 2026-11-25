#include "espnow_fan_bridge.h"

#ifdef USE_ESP32

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"

namespace esphome {
namespace espnow_fan_bridge {

static const char *const TAG = "espnow_fan_bridge";
static constexpr uint8_t BROADCAST_MAC[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

EspNowFanBridge *EspNowFanBridge::active_instance_ = nullptr;

// ============================================================================
// EspNowFanRegistry::handle_action
// ============================================================================

bool EspNowFanRegistry::handle_action(const std::string &entity_id, const std::string &action,
                                      const std::vector<std::pair<std::string, std::string>> &data,
                                      bool ha_connected) const {
  if (bridge_ == nullptr) return false;
  const std::string base = base_entity(entity_id);

  auto fit = fan_entities_.find(base);
  if (fit != fan_entities_.end()) {
    RemoteFanState *fan = fit->second;
    if (!fan->espnow_reachable && ha_connected) {
      return false;  // Seamless HA fallback (e.g. different mesh channels)
    }
    return bridge_->send_fan_action(fan, false, action, data);
  }

  auto lit = light_entities_.find(base);
  if (lit != light_entities_.end()) {
    RemoteFanState *fan = lit->second;
    if (!fan->espnow_reachable && ha_connected) {
      return false;  // Seamless HA fallback
    }
    return bridge_->send_fan_action(fan, true, action, data);
  }

  return false;
}

// ============================================================================
// Helpers
// ============================================================================

namespace {

int clamp_int(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }

const std::string *find_data_value(const std::vector<std::pair<std::string, std::string>> &data,
                                   const char *key) {
  for (const auto &kv : data) {
    if (kv.first == key) return &kv.second;
  }
  return nullptr;
}

uint32_t compute_fan_key(const std::string &fan_entity_id, const std::string &light_entity_id,
                         const std::string &name) {
  if (!fan_entity_id.empty()) return fnv1a_32(fan_entity_id);
  if (!light_entity_id.empty()) return fnv1a_32(light_entity_id);
  return fnv1a_32(name);
}

}  // namespace

// ============================================================================
// EspNowFanBridge
// ============================================================================

void EspNowFanBridge::add_remote_fan(const std::string &name, const std::string &fan_entity_id,
                                     const std::string &light_entity_id) {
  RemoteFanState st;
  st.name = name;
  st.fan_entity_id = fan_entity_id;
  st.light_entity_id = light_entity_id;
  st.fan_key_hash = compute_fan_key(fan_entity_id, light_entity_id, name);
  remote_fans_.push_back(std::move(st));
}

void EspNowFanBridge::setup() {
  active_instance_ = this;
  EspNowFanRegistry::instance().set_bridge(this);

  for (auto &rf : remote_fans_) {
    EspNowFanRegistry::instance().register_remote_fan(&rf);
  }

  // Register Wi-Fi event hooks to track connect/disconnect and background scan completion
  esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &EspNowFanBridge::wifi_event_handler,
                             this);

  // Check initial Wi-Fi association state
  wifi_ap_record_t ap_info{};
  if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
    wifi_connected_.store(true);
  }

  ensure_espnow_initialized();

#ifdef USE_TUYA_BLE_FAN
  if (role_ == BridgeRole::HUB) {
    tuya_ble_fan::TuyaBleFanRegistry::instance().add_device_change_listener(
        [this](tuya_ble_fan::TuyaBleFanDevice *dev) { this->hub_broadcast_device_state(dev); });
  }
#endif

  publish_channel_if_changed(true);
}

void EspNowFanBridge::dump_config() {
  ESP_LOGCONFIG(TAG, "ESP-NOW Fan Bridge:");
  ESP_LOGCONFIG(TAG, "  Role: %s", role_ == BridgeRole::HUB ? "HUB" : "CYD");
  ESP_LOGCONFIG(TAG, "  Fallback Channel: %u", fallback_channel_);
  ESP_LOGCONFIG(TAG, "  Current Channel: %u", current_wifi_channel());
  if (role_ == BridgeRole::CYD) {
    ESP_LOGCONFIG(TAG, "  Remote Fans: %u", static_cast<unsigned>(remote_fans_.size()));
    for (const auto &rf : remote_fans_) {
      ESP_LOGCONFIG(TAG, "    - %s (fan=%s, light=%s, hash=0x%08X)", rf.name.c_str(),
                    rf.fan_entity_id.c_str(), rf.light_entity_id.c_str(), rf.fan_key_hash);
    }
  }
}

void EspNowFanBridge::ensure_espnow_initialized() {
  if (espnow_ready_) return;

  wifi_mode_t mode = WIFI_MODE_NULL;
  if (esp_wifi_get_mode(&mode) != ESP_OK || mode == WIFI_MODE_NULL) {
    return;  // Wi-Fi driver not started yet; will retry in loop()
  }

  esp_err_t err = esp_now_init();
  if (err != ESP_OK && err != ESP_ERR_ESPNOW_EXIST) {
    ESP_LOGW(TAG, "esp_now_init failed: %s", esp_err_to_name(err));
    return;
  }

  esp_now_register_recv_cb(&EspNowFanBridge::espnow_recv_cb);
  if (!ensure_broadcast_peer()) {
    ESP_LOGW(TAG, "Failed to register ESP-NOW broadcast peer");
    return;
  }

  espnow_ready_ = true;
  ESP_LOGI(TAG, "ESP-NOW initialized (role=%s, ch=%u)",
           role_ == BridgeRole::HUB ? "HUB" : "CYD", current_wifi_channel());
}

bool EspNowFanBridge::ensure_broadcast_peer() {
  if (esp_now_is_peer_exist(BROADCAST_MAC)) return true;
  esp_now_peer_info_t peer{};
  std::memcpy(peer.peer_addr, BROADCAST_MAC, 6);
  peer.channel = 0;  // Follow current Wi-Fi channel
  peer.ifidx = WIFI_IF_STA;
  peer.encrypt = false;
  return esp_now_add_peer(&peer) == ESP_OK;
}

uint8_t EspNowFanBridge::current_wifi_channel() const {
  uint8_t primary = 0;
  wifi_second_chan_t second = WIFI_SECOND_CHAN_NONE;
  if (esp_wifi_get_channel(&primary, &second) == ESP_OK && primary >= 1 && primary <= 13) {
    return primary;
  }
  return fallback_channel_;
}

void EspNowFanBridge::set_radio_channel(uint8_t ch) {
  if (ch < 1 || ch > 13) return;
  if (wifi_connected_.load()) return;  // Never change channel while associated to an AP
  if (current_wifi_channel() == ch) return;
  esp_err_t err = esp_wifi_set_channel(ch, WIFI_SECOND_CHAN_NONE);
  if (err == ESP_OK) {
    tuned_offline_channel_ = ch;
    publish_channel_if_changed();
  }
}

void EspNowFanBridge::publish_channel_if_changed(bool force) {
  uint8_t ch = current_wifi_channel();
  if (channel_sensor_ != nullptr && (force || ch != last_published_channel_)) {
    last_published_channel_ = ch;
    channel_sensor_->publish_state(static_cast<float>(ch));
  }
}

void EspNowFanBridge::wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id,
                                         void * /*event_data*/) {
  auto *self = static_cast<EspNowFanBridge *>(arg);
  if (self == nullptr || event_base != WIFI_EVENT) return;

  if (event_id == WIFI_EVENT_STA_CONNECTED) {
    self->wifi_connected_.store(true);
    self->wifi_event_dirty_.store(true);
  } else if (event_id == WIFI_EVENT_STA_DISCONNECTED) {
    self->wifi_connected_.store(false);
    self->wifi_event_dirty_.store(true);
  } else if (event_id == WIFI_EVENT_SCAN_DONE) {
    self->wifi_scan_done_flag_.store(true);
  }
}

void EspNowFanBridge::espnow_recv_cb(const esp_now_recv_info_t *recv_info, const uint8_t *data,
                                     int len) {
  auto *self = active_instance_;
  if (self == nullptr || recv_info == nullptr || data == nullptr || len <= 0 ||
      len > static_cast<int>(MAX_FRAME_SIZE)) {
    return;
  }

  RxPacket pkt;
  std::memcpy(pkt.src_mac.data(), recv_info->src_addr, 6);
  pkt.rx_channel = (recv_info->rx_ctrl != nullptr) ? recv_info->rx_ctrl->channel : 0;
  pkt.data.assign(data, data + len);

  portENTER_CRITICAL(&self->rx_mux_);
  if (self->rx_queue_.size() < 24) {
    self->rx_queue_.push_back(std::move(pkt));
  }
  portEXIT_CRITICAL(&self->rx_mux_);
}

bool EspNowFanBridge::broadcast_frame(MsgType type, uint16_t seq,
                                      const std::vector<uint8_t> &payload) {
  if (!espnow_ready_) return false;
  auto frame = encode_frame(network_key_, type, seq, payload.empty() ? nullptr : payload.data(),
                            payload.size());
  if (frame.empty()) return false;
  esp_err_t err = esp_now_send(BROADCAST_MAC, frame.data(), frame.size());
  return err == ESP_OK;
}

void EspNowFanBridge::send_ping() {
  PingPayload p;
  p.role = role_;
  p.channel = current_wifi_channel();
#ifdef USE_TUYA_BLE_FAN
  p.fan_count = static_cast<uint8_t>(tuya_ble_fan::TuyaBleFanRegistry::instance().all_devices().size());
#else
  p.fan_count = static_cast<uint8_t>(remote_fans_.size());
#endif
  broadcast_frame(MsgType::PING, next_seq_++, encode_ping(p));
}

void EspNowFanBridge::send_pong(uint16_t req_seq) {
  PingPayload p;
  p.role = role_;
  p.channel = current_wifi_channel();
#ifdef USE_TUYA_BLE_FAN
  p.fan_count = static_cast<uint8_t>(tuya_ble_fan::TuyaBleFanRegistry::instance().all_devices().size());
#else
  p.fan_count = static_cast<uint8_t>(remote_fans_.size());
#endif
  broadcast_frame(MsgType::PONG, req_seq, encode_ping(p));
}

void EspNowFanBridge::send_sync_req() {
  SyncReqPayload req;
  req.role = role_;
  req.channel = current_wifi_channel();
  broadcast_frame(MsgType::SYNC_REQ, next_seq_++, encode_sync_req(req));
}

void EspNowFanBridge::upsert_peer(const std::array<uint8_t, 6> &mac, BridgeRole role, uint8_t ch,
                                  uint32_t now_ms) {
  for (auto &p : peers_) {
    if (p.mac == mac) {
      p.role = role;
      if (ch >= 1 && ch <= 13) p.channel = ch;
      p.last_seen_ms = now_ms;
      return;
    }
  }
  PeerInfo info;
  info.mac = mac;
  info.role = role;
  info.channel = (ch >= 1 && ch <= 13) ? ch : current_wifi_channel();
  info.last_seen_ms = now_ms;
  peers_.push_back(info);
}

void EspNowFanBridge::loop() {
  const uint32_t now = millis();

  if (!espnow_ready_) {
    ensure_espnow_initialized();
    if (!espnow_ready_) return;
  }

  // 1. Drain RX queue safely on main thread
  std::deque<RxPacket> batch;
  portENTER_CRITICAL(&rx_mux_);
  batch.swap(rx_queue_);
  portEXIT_CRITICAL(&rx_mux_);

  for (const auto &pkt : batch) {
    process_rx_packet(pkt);
  }

  // 2. React to Wi-Fi connect/disconnect/scan events
  const bool online = wifi_connected_.load();
  if (wifi_event_dirty_.exchange(false)) {
    if (online) {
      ESP_LOGI(TAG, "Wi-Fi connected on ch %u; resuming AP channel", current_wifi_channel());
      hunt_.clear_active_channels();
      publish_channel_if_changed(true);
      send_ping();
      if (role_ == BridgeRole::CYD) {
        send_sync_req();
      }
    } else {
      ESP_LOGI(TAG, "Wi-Fi disconnected; parking on fallback ch %u and starting sweep",
               fallback_channel_);
      set_radio_channel(fallback_channel_);
      send_ping();
      hunt_.start_sweep(now);
      last_sweep_ms_ = now;
    }
  }

  if (wifi_scan_done_flag_.exchange(false) && !online) {
    // Restore our offline ESP-NOW channel right after ESPHome's background Wi-Fi scan
    uint8_t target = hunt_.active_channel(now, ROUND_ROBIN_DWELL_MS);
    set_radio_channel(target);
    if (now - last_sweep_ms_ >= SWEEP_INTERVAL_MS) {
      hunt_.start_sweep(now);
      last_sweep_ms_ = now;
    }
  }

  // 3. Offline channel hunting & multi-channel round-robin
  if (!online) {
    if (hunt_.is_sweeping()) {
      bool should_ping = false;
      uint8_t ch = hunt_.tick_sweep(now, SWEEP_DWELL_MS, should_ping);
      if (ch >= 1 && ch <= 13) {
        set_radio_channel(ch);
        if (should_ping) {
          send_ping();
        }
      }
      if (!hunt_.is_sweeping()) {
        // Sweep just finished: tune to resting/round-robin channel
        uint8_t target = hunt_.active_channel(now, ROUND_ROBIN_DWELL_MS);
        set_radio_channel(target);
        if (role_ == BridgeRole::CYD) {
          send_sync_req();
        }
      }
    } else {
      if (now - last_sweep_ms_ >= SWEEP_INTERVAL_MS) {
        hunt_.start_sweep(now);
        last_sweep_ms_ = now;
      } else {
        uint8_t target = hunt_.active_channel(now, ROUND_ROBIN_DWELL_MS);
        if (target != tuned_offline_channel_) {
          set_radio_channel(target);
        }
      }
    }
  }

  // 4. Periodic heartbeat & channel sensor refresh
  if (now - last_heartbeat_ms_ >= HEARTBEAT_INTERVAL_MS) {
    last_heartbeat_ms_ = now;
    if (!hunt_.is_sweeping()) {
      send_ping();
      if (role_ == BridgeRole::CYD) {
        send_sync_req();
      }
    }
  }

  if (now - last_channel_poll_ms_ >= 5000) {
    last_channel_poll_ms_ = now;
    publish_channel_if_changed();
  }

  // 5. CYD pending command retries & peer reachability timeout
  if (role_ == BridgeRole::CYD) {
    cyd_tick_pending_cmds(now);
    bool any_changed = false;
    for (auto &rf : remote_fans_) {
      if (rf.espnow_reachable && (now - rf.last_seen_ms > PEER_TIMEOUT_MS)) {
        rf.espnow_reachable = false;
        any_changed = true;
      }
    }
    if (any_changed) {
      EspNowFanRegistry::instance().notify_state_changed("", "");
    }
  }
}

void EspNowFanBridge::process_rx_packet(const RxPacket &pkt) {
  FrameHeader hdr;
  std::vector<uint8_t> payload;
  if (!decode_frame(network_key_, pkt.data.data(), pkt.data.size(), hdr, payload)) {
    return;  // Wrong magic, version, or network key
  }

  const uint32_t now = millis();
  const uint8_t rx_ch =
      (pkt.rx_channel >= 1 && pkt.rx_channel <= 13) ? pkt.rx_channel : current_wifi_channel();

  switch (hdr.type) {
    case MsgType::PING: {
      PingPayload p;
      if (!decode_ping(payload.data(), payload.size(), p)) return;
      if (p.role == role_) return;  // Ignore same-role pings
      uint8_t peer_ch = (p.channel >= 1 && p.channel <= 13) ? p.channel : rx_ch;
      upsert_peer(pkt.src_mac, p.role, peer_ch, now);
      if (!wifi_connected_.load()) {
        hunt_.record_peer_channel(peer_ch);
      }
      send_pong(hdr.seq);
#ifdef USE_TUYA_BLE_FAN
      if (role_ == BridgeRole::HUB && p.role == BridgeRole::CYD) {
        hub_broadcast_all_states();
      }
#endif
      break;
    }

    case MsgType::PONG: {
      PingPayload p;
      if (!decode_ping(payload.data(), payload.size(), p)) return;
      if (p.role == role_) return;
      uint8_t peer_ch = (p.channel >= 1 && p.channel <= 13) ? p.channel : rx_ch;
      upsert_peer(pkt.src_mac, p.role, peer_ch, now);
      if (!wifi_connected_.load()) {
        hunt_.record_peer_channel(peer_ch);
      }
      if (role_ == BridgeRole::CYD && p.role == BridgeRole::HUB) {
        send_sync_req();
      }
      break;
    }

    case MsgType::SYNC_REQ: {
      SyncReqPayload req;
      if (!decode_sync_req(payload.data(), payload.size(), req)) return;
      upsert_peer(pkt.src_mac, req.role, req.channel, now);
      if (!wifi_connected_.load()) {
        hunt_.record_peer_channel(req.channel ? req.channel : rx_ch);
      }
#ifdef USE_TUYA_BLE_FAN
      if (role_ == BridgeRole::HUB) {
        hub_broadcast_all_states();
      }
#endif
      break;
    }

    case MsgType::CMD: {
      CmdPayload cmd;
      if (!decode_cmd(payload.data(), payload.size(), cmd)) return;
      upsert_peer(pkt.src_mac, BridgeRole::CYD, rx_ch, now);
#ifdef USE_TUYA_BLE_FAN
      if (role_ == BridgeRole::HUB) {
        hub_handle_cmd(cmd, hdr.seq);
      }
#endif
      break;
    }

    case MsgType::ACK: {
      AckPayload ack;
      if (!decode_ack(payload.data(), payload.size(), ack)) return;
      if (role_ == BridgeRole::CYD) {
        cyd_handle_ack(ack, now);
      }
      break;
    }

    case MsgType::STATE: {
      StatePayload st;
      if (!decode_state(payload.data(), payload.size(), st)) return;
      upsert_peer(pkt.src_mac, BridgeRole::HUB, rx_ch, now);
      if (!wifi_connected_.load()) {
        hunt_.record_peer_channel(rx_ch);
      }
      if (role_ == BridgeRole::CYD) {
        cyd_handle_state(st, now);
      }
      break;
    }
  }
}

// ============================================================================
// Hub-side implementation
// ============================================================================

#ifdef USE_TUYA_BLE_FAN

tuya_ble_fan::TuyaBleFanDevice *EspNowFanBridge::hub_find_device(uint32_t fan_key_hash) {
  for (auto *dev : tuya_ble_fan::TuyaBleFanRegistry::instance().all_devices()) {
    if (dev == nullptr) continue;
    uint32_t h = compute_fan_key(dev->fan_entity_id(), dev->light_entity_id(), dev->name());
    if (h == fan_key_hash) return dev;
  }
  return nullptr;
}

void EspNowFanBridge::hub_handle_cmd(const CmdPayload &cmd, uint16_t seq) {
  auto *dev = hub_find_device(cmd.fan_key_hash);
  AckPayload ack;
  ack.ack_seq = seq;

  if (dev == nullptr) {
    ack.status = AckStatus::UNKNOWN_FAN;
    broadcast_frame(MsgType::ACK, seq, encode_ack(ack));
    return;
  }

  switch (cmd.opcode) {
    case CmdOpcode::FAN_POWER:
      dev->set_fan_power(cmd.arg0 != 0);
      break;
    case CmdOpcode::FAN_SPEED:
      dev->set_fan_speed(clamp_int(cmd.arg0, 1, 6));
      break;
    case CmdOpcode::FAN_PERCENT:
      dev->set_fan_percentage(clamp_int(cmd.arg0, 0, 100));
      break;
    case CmdOpcode::FAN_DIRECTION:
      dev->set_fan_direction(cmd.arg0 != 0);
      break;
    case CmdOpcode::FAN_PRESET:
      dev->set_fan_preset(static_cast<uint8_t>(cmd.arg0));
      break;
    case CmdOpcode::FAN_TIMER:
      dev->set_fan_timer(clamp_int(cmd.arg0, 0, 540));
      break;
    case CmdOpcode::LIGHT_POWER:
      dev->set_light_power(cmd.arg0 != 0);
      break;
    case CmdOpcode::LIGHT_BRIGHTNESS:
      dev->set_light_brightness(clamp_int(cmd.arg0, 10, 1000));
      break;
    case CmdOpcode::LIGHT_COLOR_TEMP:
      dev->set_light_color_temp(clamp_int(cmd.arg0, 0, 1000));
      break;
    case CmdOpcode::LIGHT_STATE:
      dev->set_light_state(cmd.arg0 != 0, clamp_int(cmd.arg1, 10, 1000),
                           clamp_int(cmd.arg2, 0, 1000));
      break;
    default:
      ack.status = AckStatus::INVALID_CMD;
      broadcast_frame(MsgType::ACK, seq, encode_ack(ack));
      return;
  }

  ack.status = AckStatus::OK;
  broadcast_frame(MsgType::ACK, seq, encode_ack(ack));
  hub_broadcast_device_state(dev);
}

void EspNowFanBridge::hub_broadcast_device_state(tuya_ble_fan::TuyaBleFanDevice *dev) {
  if (!espnow_ready_ || dev == nullptr) return;
  StatePayload st;
  st.fan_key_hash = compute_fan_key(dev->fan_entity_id(), dev->light_entity_id(), dev->name());
  st.ble_conn_status = static_cast<uint8_t>(dev->conn_status());
  st.ble_rssi = static_cast<int8_t>(clamp_int(dev->last_rssi(), -127, 0));
  st.fan_on = dev->fan_on() ? 1 : 0;
  st.fan_speed = static_cast<uint8_t>(clamp_int(dev->fan_speed(), 1, 6));
  st.fan_reverse = dev->fan_reverse() ? 1 : 0;
  st.fan_preset = dev->fan_preset();
  st.fan_timer = static_cast<uint16_t>(clamp_int(dev->fan_timer(), 0, 540));
  st.light_on = dev->light_on() ? 1 : 0;
  st.light_brightness = static_cast<uint16_t>(clamp_int(dev->light_brightness(), 10, 1000));
  st.light_color_temp = static_cast<uint16_t>(clamp_int(dev->light_color_temp(), 0, 1000));

  broadcast_frame(MsgType::STATE, next_seq_++, encode_state(st));
}

void EspNowFanBridge::hub_broadcast_all_states() {
  for (auto *dev : tuya_ble_fan::TuyaBleFanRegistry::instance().all_devices()) {
    hub_broadcast_device_state(dev);
  }
}

#endif  // USE_TUYA_BLE_FAN

// ============================================================================
// CYD-side implementation
// ============================================================================

RemoteFanState *EspNowFanBridge::cyd_find_remote_fan(uint32_t fan_key_hash) {
  for (auto &rf : remote_fans_) {
    if (rf.fan_key_hash == fan_key_hash) return &rf;
  }
  return nullptr;
}

void EspNowFanBridge::cyd_handle_state(const StatePayload &st, uint32_t now_ms) {
  auto *rf = cyd_find_remote_fan(st.fan_key_hash);
  if (rf == nullptr) return;

  rf->has_state = true;
  rf->espnow_reachable = true;
  rf->last_seen_ms = now_ms;
  rf->ble_status = static_cast<RemoteBleConnStatus>(st.ble_conn_status <= 4 ? st.ble_conn_status : 0);
  rf->ble_rssi = st.ble_rssi;
  rf->fan_on = st.fan_on != 0;
  rf->fan_speed = st.fan_speed >= 1 && st.fan_speed <= 6 ? st.fan_speed : 1;
  rf->fan_reverse = st.fan_reverse != 0;
  rf->fan_preset = st.fan_preset;
  rf->fan_timer = st.fan_timer;
  rf->light_on = st.light_on != 0;
  rf->light_brightness = st.light_brightness;
  rf->light_color_temp = st.light_color_temp;

  if (!rf->fan_entity_id.empty()) {
    EspNowFanRegistry::instance().notify_state_changed(rf->fan_entity_id,
                                                       rf->fan_on ? "on" : "off");
    EspNowFanRegistry::instance().notify_state_changed(rf->fan_entity_id + "|percentage",
                                                       std::to_string(rf->fan_percentage()));
    EspNowFanRegistry::instance().notify_state_changed(rf->fan_entity_id + "|direction",
                                                       rf->fan_reverse ? "reverse" : "forward");
  }
  if (!rf->light_entity_id.empty()) {
    EspNowFanRegistry::instance().notify_state_changed(rf->light_entity_id,
                                                       rf->light_on ? "on" : "off");
  }
}

void EspNowFanBridge::cyd_handle_ack(const AckPayload &ack, uint32_t now_ms) {
  for (auto it = pending_cmds_.begin(); it != pending_cmds_.end(); ++it) {
    if (it->seq == ack.ack_seq) {
      if (auto *rf = cyd_find_remote_fan(it->fan_key_hash)) {
        rf->espnow_reachable = true;
        rf->last_seen_ms = now_ms;
      }
      pending_cmds_.erase(it);
      return;
    }
  }
}

void EspNowFanBridge::cyd_queue_cmd(const CmdPayload &cmd, uint32_t now_ms) {
  PendingCmd pending;
  pending.seq = next_seq_++;
  pending.cmd = cmd;
  pending.fan_key_hash = cmd.fan_key_hash;
  pending.created_ms = now_ms;
  pending.last_tx_ms = now_ms;
  pending.attempts = 1;

  broadcast_frame(MsgType::CMD, pending.seq, encode_cmd(pending.cmd));

  // Coalesce any older pending command for the same fan + opcode
  for (auto it = pending_cmds_.begin(); it != pending_cmds_.end();) {
    if (it->fan_key_hash == cmd.fan_key_hash && it->cmd.opcode == cmd.opcode) {
      it = pending_cmds_.erase(it);
    } else {
      ++it;
    }
  }
  pending_cmds_.push_back(pending);
}

void EspNowFanBridge::cyd_tick_pending_cmds(uint32_t now_ms) {
  for (auto it = pending_cmds_.begin(); it != pending_cmds_.end();) {
    if (now_ms - it->last_tx_ms < CMD_RETRY_INTERVAL_MS) {
      ++it;
      continue;
    }
    if (it->attempts >= CMD_MAX_ATTEMPTS) {
      ESP_LOGW(TAG, "ESP-NOW cmd seq=%u timed out after %u attempts", it->seq, it->attempts);
      if (auto *rf = cyd_find_remote_fan(it->fan_key_hash)) {
        rf->espnow_reachable = false;
        EspNowFanRegistry::instance().notify_state_changed("", "");
      }
      it = pending_cmds_.erase(it);
      continue;
    }
    it->attempts++;
    it->last_tx_ms = now_ms;
    broadcast_frame(MsgType::CMD, it->seq, encode_cmd(it->cmd));
    ++it;
  }
}

bool EspNowFanBridge::send_fan_action(RemoteFanState *fan, bool is_light,
                                      const std::string &action,
                                      const std::vector<std::pair<std::string, std::string>> &data) {
  if (fan == nullptr) return false;
  const uint32_t now = millis();

  // Strip domain prefix if present (e.g. "fan.turn_on" -> "turn_on")
  std::string act = action;
  size_t dot = act.find('.');
  if (dot != std::string::npos) act = act.substr(dot + 1);

  CmdPayload cmd;
  cmd.fan_key_hash = fan->fan_key_hash;

  if (!is_light) {
    if (act == "toggle") {
      fan->fan_on = !fan->fan_on;
      cmd.opcode = CmdOpcode::FAN_POWER;
      cmd.arg0 = fan->fan_on ? 1 : 0;
    } else if (act == "turn_on") {
      fan->fan_on = true;
      if (const auto *pct_s = find_data_value(data, "percentage")) {
        int pct = clamp_int(std::atoi(pct_s->c_str()), 0, 100);
        fan->fan_speed = pct == 0 ? 1 : static_cast<uint8_t>(clamp_int((pct * 6 + 50) / 100, 1, 6));
        cmd.opcode = CmdOpcode::FAN_PERCENT;
        cmd.arg0 = static_cast<int16_t>(pct);
      } else {
        cmd.opcode = CmdOpcode::FAN_POWER;
        cmd.arg0 = 1;
      }
    } else if (act == "turn_off") {
      fan->fan_on = false;
      cmd.opcode = CmdOpcode::FAN_POWER;
      cmd.arg0 = 0;
    } else if (act == "set_percentage") {
      const auto *pct_s = find_data_value(data, "percentage");
      int pct = pct_s ? clamp_int(std::atoi(pct_s->c_str()), 0, 100) : 50;
      fan->fan_on = pct > 0;
      if (pct > 0) {
        fan->fan_speed = static_cast<uint8_t>(clamp_int((pct * 6 + 50) / 100, 1, 6));
      }
      cmd.opcode = CmdOpcode::FAN_PERCENT;
      cmd.arg0 = static_cast<int16_t>(pct);
    } else if (act == "increase_speed") {
      fan->fan_on = true;
      fan->fan_speed = static_cast<uint8_t>(clamp_int(fan->fan_speed + 1, 1, 6));
      cmd.opcode = CmdOpcode::FAN_SPEED;
      cmd.arg0 = fan->fan_speed;
    } else if (act == "decrease_speed") {
      if (fan->fan_speed > 1) {
        fan->fan_speed--;
        cmd.opcode = CmdOpcode::FAN_SPEED;
        cmd.arg0 = fan->fan_speed;
      } else {
        fan->fan_on = false;
        cmd.opcode = CmdOpcode::FAN_POWER;
        cmd.arg0 = 0;
      }
    } else if (act == "set_direction") {
      const auto *dir_s = find_data_value(data, "direction");
      bool rev = dir_s != nullptr && (*dir_s == "reverse");
      fan->fan_reverse = rev;
      cmd.opcode = CmdOpcode::FAN_DIRECTION;
      cmd.arg0 = rev ? 1 : 0;
    } else if (act == "set_preset_mode") {
      const auto *preset_s = find_data_value(data, "preset_mode");
      uint8_t preset = (preset_s != nullptr && *preset_s == "nature") ? 1 : 0;
      fan->fan_preset = preset;
      cmd.opcode = CmdOpcode::FAN_PRESET;
      cmd.arg0 = preset;
    } else {
      return false;
    }

    fan->has_state = true;
    cyd_queue_cmd(cmd, now);
    if (!fan->fan_entity_id.empty()) {
      EspNowFanRegistry::instance().notify_state_changed(fan->fan_entity_id,
                                                         fan->fan_on ? "on" : "off");
      EspNowFanRegistry::instance().notify_state_changed(fan->fan_entity_id + "|percentage",
                                                         std::to_string(fan->fan_percentage()));
      EspNowFanRegistry::instance().notify_state_changed(fan->fan_entity_id + "|direction",
                                                         fan->fan_reverse ? "reverse" : "forward");
    }
    return true;
  }

  // Light actions
  if (act == "toggle") {
    fan->light_on = !fan->light_on;
    cmd.opcode = CmdOpcode::LIGHT_POWER;
    cmd.arg0 = fan->light_on ? 1 : 0;
  } else if (act == "turn_off") {
    fan->light_on = false;
    cmd.opcode = CmdOpcode::LIGHT_POWER;
    cmd.arg0 = 0;
  } else if (act == "turn_on") {
    fan->light_on = true;
    const auto *b_pct_s = find_data_value(data, "brightness_pct");
    const auto *b_255_s = find_data_value(data, "brightness");
    const auto *k_s = find_data_value(data, "color_temp_kelvin");
    const auto *m_s = find_data_value(data, "color_temp");

    bool has_b = false;
    bool has_ct = false;
    if (b_pct_s) {
      int pct = clamp_int(std::atoi(b_pct_s->c_str()), 1, 100);
      fan->light_brightness = static_cast<uint16_t>(clamp_int(pct * 10, 10, 1000));
      has_b = true;
    } else if (b_255_s) {
      int b255 = clamp_int(std::atoi(b_255_s->c_str()), 1, 255);
      fan->light_brightness = static_cast<uint16_t>(clamp_int((b255 * 1000 + 127) / 255, 10, 1000));
      has_b = true;
    }
    if (k_s) {
      int k = clamp_int(std::atoi(k_s->c_str()), 2700, 6500);
      fan->light_color_temp =
          static_cast<uint16_t>(clamp_int(((k - 2700) * 1000) / (6500 - 2700), 0, 1000));
      has_ct = true;
    } else if (m_s) {
      int m = clamp_int(std::atoi(m_s->c_str()), 153, 370);
      int k = clamp_int(1000000 / m, 2700, 6500);
      fan->light_color_temp =
          static_cast<uint16_t>(clamp_int(((k - 2700) * 1000) / (6500 - 2700), 0, 1000));
      has_ct = true;
    }

    if (has_b || has_ct) {
      cmd.opcode = CmdOpcode::LIGHT_STATE;
      cmd.arg0 = 1;
      cmd.arg1 = static_cast<int16_t>(fan->light_brightness);
      cmd.arg2 = static_cast<int16_t>(fan->light_color_temp);
    } else {
      cmd.opcode = CmdOpcode::LIGHT_POWER;
      cmd.arg0 = 1;
    }
  } else {
    return false;
  }

  fan->has_state = true;
  cyd_queue_cmd(cmd, now);
  if (!fan->light_entity_id.empty()) {
    EspNowFanRegistry::instance().notify_state_changed(fan->light_entity_id,
                                                       fan->light_on ? "on" : "off");
  }
  return true;
}

}  // namespace espnow_fan_bridge
}  // namespace esphome

#endif  // USE_ESP32
