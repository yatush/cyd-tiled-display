#include "espnow_fan_bridge.h"

#ifdef USE_ESP32

#include <esp_random.h>

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
                                      bool ha_entity_available) const {
  if (bridge_ == nullptr) return false;
  const std::string base = base_entity(entity_id);

  auto fit = fan_entities_.find(base);
  if (fit != fan_entities_.end()) {
    RemoteFanState *fan = fit->second;
    if (!fan->espnow_reachable && ha_entity_available) {
      return false;  // Seamless HA fallback (e.g. different mesh channels)
    }
    return bridge_->send_fan_action(fan, false, action, data);
  }

  auto lit = light_entities_.find(base);
  if (lit != light_entities_.end()) {
    RemoteFanState *fan = lit->second;
    if (!fan->espnow_reachable && ha_entity_available) {
      return false;  // Seamless HA fallback
    }
    return bridge_->send_fan_action(fan, true, action, data);
  }

  auto sit = shelly_entities_.find(base);
  if (sit != shelly_entities_.end()) {
    if (ha_entity_available) {
      return false;  // Normal HA tier — let HA handle it
    }
    return bridge_->send_shelly_action(sit->second, action, data);
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

void EspNowFanBridge::add_remote_shelly(const std::string &name, const std::string &mac_address,
                                        uint8_t channel, bool is_cover,
                                        const std::string &entity_id) {
  RemoteShellyState st;
  st.name = name;
  st.mac_address = normalize_mac_hex(mac_address);
  st.device_id = shelly_device_id_from_mac(st.mac_address);
  st.channel = channel;
  st.is_cover = is_cover;
  st.entity_id = entity_id;
  remote_shellys_.push_back(std::move(st));
}

void EspNowFanBridge::setup() {
  active_instance_ = this;
  EspNowFanRegistry::instance().set_bridge(this);

  for (auto &rf : remote_fans_) {
    EspNowFanRegistry::instance().register_remote_fan(&rf);
  }
  for (auto &rs : remote_shellys_) {
    EspNowFanRegistry::instance().register_remote_shelly(&rs);
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

#ifdef USE_SHELLY_BLE_BRIDGE
  if (role_ == BridgeRole::HUB) {
    shelly_ble_bridge::ShellyBleBridgeRegistry::instance().set_state_callback(
        [this](const shelly_ble_bridge::ShellyCachedState &st) {
          this->hub_broadcast_shelly_state(st);
        });
    shelly_ble_bridge::ShellyBleBridgeRegistry::instance().set_remote_light_toggle_handler(
        [this](const std::string &target_fan_device_id,
               const std::string &target_light_entity_id, uint32_t source_id,
               uint16_t source_seq) {
          return this->hub_send_remote_light_toggle(target_fan_device_id, target_light_entity_id,
                                                    source_id, source_seq);
        });
  }
#endif

  publish_channel_if_changed(true);
}

void EspNowFanBridge::dump_config() {
  ESP_LOGCONFIG(TAG, "ESP-NOW Fan Bridge:");
  ESP_LOGCONFIG(TAG, "  Role: %s", role_ == BridgeRole::HUB ? "HUB" : "CYD");
  ESP_LOGCONFIG(TAG, "  Origin ID: 0x%08X (relay TTL=%u)", static_cast<unsigned>(local_origin_id_),
                static_cast<unsigned>(DEFAULT_RELAY_TTL));
  ESP_LOGCONFIG(TAG, "  Fallback Channel: %u", fallback_channel_);
  ESP_LOGCONFIG(TAG, "  Current Channel: %u", current_wifi_channel());
  if (role_ == BridgeRole::CYD) {
    ESP_LOGCONFIG(TAG, "  Remote Fans: %u", static_cast<unsigned>(remote_fans_.size()));
    for (const auto &rf : remote_fans_) {
      ESP_LOGCONFIG(TAG, "    - %s (fan=%s, light=%s, hash=0x%08X)", rf.name.c_str(),
                    rf.fan_entity_id.c_str(), rf.light_entity_id.c_str(),
                    static_cast<unsigned>(rf.fan_key_hash));
    }
    ESP_LOGCONFIG(TAG, "  Remote Shellys: %u", static_cast<unsigned>(remote_shellys_.size()));
    for (const auto &rs : remote_shellys_) {
      ESP_LOGCONFIG(TAG, "    - %s (entity=%s, mac=%s, ch=%u, id=0x%08X, cover=%d)",
                    rs.name.c_str(), rs.entity_id.c_str(), rs.mac_address.c_str(),
                    static_cast<unsigned>(rs.channel), static_cast<unsigned>(rs.device_id),
                    rs.is_cover ? 1 : 0);
    }
  }
}

void EspNowFanBridge::ensure_espnow_initialized() {
  if (espnow_ready_) return;

  wifi_mode_t mode = WIFI_MODE_NULL;
  if (esp_wifi_get_mode(&mode) != ESP_OK || mode == WIFI_MODE_NULL) {
    return;  // Wi-Fi driver not started yet; will retry in loop()
  }

  uint8_t mac[6]{};
  if (esp_wifi_get_mac(WIFI_IF_STA, mac) == ESP_OK) {
    local_origin_id_ = fnv1a_32(mac, sizeof(mac));
  }
  if (local_origin_id_ == 0) {
    local_origin_id_ = 1;
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
  ESP_LOGI(TAG, "ESP-NOW initialized (role=%s, origin=0x%08X, ch=%u)",
           role_ == BridgeRole::HUB ? "HUB" : "CYD", static_cast<unsigned>(local_origin_id_),
           current_wifi_channel());
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
                                      const std::vector<uint8_t> &payload, uint8_t ttl,
                                      uint8_t hop_nonce, uint32_t origin_override) {
  if (!espnow_ready_) return false;
  const uint32_t origin = origin_override != 0 ? origin_override : local_origin_id_;
  if (origin_override != 0) {
    relay_dedup_.accept(origin, type, seq, hop_nonce, millis(), RELAY_DEDUP_TTL_MS);
  }
  auto frame = encode_frame(network_key_, type, seq, payload.empty() ? nullptr : payload.data(),
                            payload.size(), origin, ttl, hop_nonce);
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
  broadcast_frame(MsgType::PING, next_seq_++, encode_ping(p), 0);
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
  broadcast_frame(MsgType::PONG, req_seq, encode_ping(p), 0);
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
  ESP_LOGI(TAG, "Discovered ESP-NOW peer %02X:%02X:%02X:%02X:%02X:%02X (role=%s, ch=%u)",
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5],
           role == BridgeRole::HUB ? "HUB" : "CYD", info.channel);
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

  // 5. Hub relay queue & pending command retries (both CYD and cross-hub detached toggles)
  const uint32_t check_now = millis();
  if (role_ == BridgeRole::HUB) {
    hub_tick_relays(check_now);
  }
  cyd_tick_pending_cmds(check_now);

  // 6. CYD peer reachability timeout & UI redraw
  if (role_ == BridgeRole::CYD) {
    for (auto &rf : remote_fans_) {
      if (rf.espnow_reachable &&
          static_cast<int32_t>(check_now - rf.last_seen_ms) >
              static_cast<int32_t>(PEER_TIMEOUT_MS)) {
        ESP_LOGW(TAG, "[%s] ESP-NOW peer timed out (unreachable)", rf.name.c_str());
        rf.espnow_reachable = false;
        ui_dirty_ = true;
      }
    }
    for (auto &rs : remote_shellys_) {
      if (rs.espnow_reachable &&
          static_cast<int32_t>(check_now - rs.last_seen_ms) >
              static_cast<int32_t>(PEER_TIMEOUT_MS)) {
        ESP_LOGW(TAG, "[%s] ESP-NOW Shelly hub timed out (unreachable)", rs.name.c_str());
        rs.espnow_reachable = false;
        ui_dirty_ = true;
      }
    }
    if (ui_dirty_) {
      ui_dirty_ = false;
      EspNowFanRegistry::instance().notify_redraw();
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

  // Drop our own relayed echoes and duplicate multi-hop frames
  if (hdr.origin_id != 0 && hdr.origin_id == local_origin_id_) {
    return;
  }
  if (hdr.type != MsgType::PING && hdr.type != MsgType::PONG) {
    if (!relay_dedup_.accept(hdr.origin_id, hdr.type, hdr.seq, hdr.hop_nonce, now,
                             RELAY_DEDUP_TTL_MS)) {
      return;
    }
  }

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
      if (role_ == BridgeRole::CYD && p.role == BridgeRole::HUB) {
        for (auto &rs : remote_shellys_) {
          if (!rs.espnow_reachable) ui_dirty_ = true;
          rs.espnow_reachable = true;
          rs.last_seen_ms = now;
        }
      }
      send_pong(hdr.seq);
#ifdef USE_TUYA_BLE_FAN
      if (role_ == BridgeRole::HUB && p.role == BridgeRole::CYD) {
        hub_broadcast_all_states();
      }
#endif
#ifdef USE_SHELLY_BLE_BRIDGE
      if (role_ == BridgeRole::HUB && p.role == BridgeRole::CYD) {
        hub_broadcast_all_shelly_states();
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
        for (auto &rs : remote_shellys_) {
          if (!rs.espnow_reachable) ui_dirty_ = true;
          rs.espnow_reachable = true;
          rs.last_seen_ms = now;
        }
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
      if (role_ == BridgeRole::HUB) {
#ifdef USE_TUYA_BLE_FAN
        hub_broadcast_all_states();
#endif
#ifdef USE_SHELLY_BLE_BRIDGE
        hub_broadcast_all_shelly_states();
#endif
        hub_schedule_relay(hdr, payload, now);
      }
      break;
    }

    case MsgType::CMD: {
      CmdPayload cmd;
      if (!decode_cmd(payload.data(), payload.size(), cmd)) return;
      upsert_peer(pkt.src_mac, BridgeRole::CYD, rx_ch, now);
      if (role_ == BridgeRole::HUB) {
        bool handled = false;
#ifdef USE_TUYA_BLE_FAN
        handled = hub_handle_cmd(cmd, hdr.origin_id, hdr.seq, now);
#endif
        if (!handled) {
          hub_schedule_relay(hdr, payload, now);
        }
      }
      break;
    }

    case MsgType::ACK: {
      AckPayload ack;
      if (!decode_ack(payload.data(), payload.size(), ack)) return;
      const size_t before_cmds = pending_cmds_.size() + pending_shelly_cmds_.size();
      cyd_handle_ack(ack, now);
      const bool consumed_locally =
          (pending_cmds_.size() + pending_shelly_cmds_.size()) < before_cmds;
      if (role_ == BridgeRole::HUB && !consumed_locally) {
        hub_schedule_relay(hdr, payload, now);
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
      } else if (role_ == BridgeRole::HUB) {
        hub_schedule_relay(hdr, payload, now);
      }
      break;
    }

    case MsgType::SHELLY_CMD: {
      ShellyCmdPayload scmd;
      if (!decode_shelly_cmd(payload.data(), payload.size(), scmd)) return;
      upsert_peer(pkt.src_mac, BridgeRole::CYD, rx_ch, now);
      if (role_ == BridgeRole::HUB) {
        bool handled = false;
#ifdef USE_SHELLY_BLE_BRIDGE
        handled = hub_handle_shelly_cmd(scmd, hdr.origin_id, hdr.seq, now);
#endif
        if (!handled) {
          hub_schedule_relay(hdr, payload, now);
        }
      }
      break;
    }

    case MsgType::SHELLY_STATE: {
      ShellyStatePayload sst;
      if (!decode_shelly_state(payload.data(), payload.size(), sst)) return;
      upsert_peer(pkt.src_mac, BridgeRole::HUB, rx_ch, now);
      if (!wifi_connected_.load()) {
        hunt_.record_peer_channel(rx_ch);
      }
      if (role_ == BridgeRole::CYD) {
        cyd_handle_shelly_state(sst, now);
      } else if (role_ == BridgeRole::HUB) {
        hub_schedule_relay(hdr, payload, now);
      }
      break;
    }
  }
}

// ============================================================================
// Hub-side implementation
// ============================================================================

void EspNowFanBridge::hub_schedule_relay(const FrameHeader &hdr,
                                         const std::vector<uint8_t> &payload, uint32_t now_ms) {
  if (!espnow_ready_ || role_ != BridgeRole::HUB) return;
  if (hdr.ttl == 0) return;
  if (hdr.origin_id != 0 && hdr.origin_id == local_origin_id_) return;

  auto relayed = encode_frame(network_key_, hdr.type, hdr.seq,
                              payload.empty() ? nullptr : payload.data(), payload.size(),
                              hdr.origin_id, static_cast<uint8_t>(hdr.ttl - 1), hdr.hop_nonce);
  if (relayed.empty()) return;

  if (pending_relays_.size() >= MAX_PENDING_RELAYS) {
    pending_relays_.pop_front();
  }
  const uint32_t jitter_ms = 10u + (esp_random() % 21u);  // 10..30 ms collision avoidance
  pending_relays_.push_back(PendingRelay{std::move(relayed), now_ms + jitter_ms});
  ESP_LOGV(TAG, "Queued ESP-NOW relay type=%u origin=0x%08X seq=%u next_ttl=%u (+%ums)",
           static_cast<unsigned>(hdr.type), static_cast<unsigned>(hdr.origin_id), hdr.seq,
           static_cast<unsigned>(hdr.ttl - 1), static_cast<unsigned>(jitter_ms));
}

void EspNowFanBridge::hub_tick_relays(uint32_t now_ms) {
  if (!espnow_ready_ || pending_relays_.empty()) return;
  for (auto it = pending_relays_.begin(); it != pending_relays_.end();) {
    if (static_cast<int32_t>(now_ms - it->send_at_ms) >= 0) {
      esp_now_send(BROADCAST_MAC, it->frame.data(), it->frame.size());
      it = pending_relays_.erase(it);
    } else {
      ++it;
    }
  }
}

bool EspNowFanBridge::hub_send_remote_light_toggle(const std::string &target_fan_device_id,
                                                   const std::string &target_light_entity_id,
                                                   uint32_t source_id, uint16_t source_seq) {
  if (!espnow_ready_ || role_ != BridgeRole::HUB) return false;
  const uint32_t now_ms = millis();

  // Remote Shelly output encoded as "shelly:<mac12>:<ch>"
  if (target_fan_device_id.rfind("shelly:", 0) == 0) {
    std::string rest = target_fan_device_id.substr(7);
    size_t colon = rest.find(':');
    std::string target_mac = (colon == std::string::npos) ? rest : rest.substr(0, colon);
    uint8_t target_ch = 0;
    if (colon != std::string::npos && colon + 1 < rest.size()) {
      int parsed = std::atoi(rest.substr(colon + 1).c_str());
      if (parsed >= 0 && parsed <= 3) target_ch = static_cast<uint8_t>(parsed);
    }
    uint32_t target_dev_id = shelly_device_id_from_mac(target_mac);
    if (target_dev_id == 0) return false;

    ShellyCmdPayload scmd;
    scmd.device_id = target_dev_id;
    scmd.channel = target_ch;
    scmd.opcode = ShellyOpcode::SW_TOGGLE;
    scmd.arg = 0;
    scmd.flags = 0;

    PendingShellyCmd pending;
    pending.seq = source_seq != 0 ? source_seq : next_seq_++;
    pending.origin_override = source_id;
    pending.cmd = scmd;
    pending.created_ms = now_ms;
    pending.last_tx_ms = now_ms;
    pending.attempts = 1;

    broadcast_frame(MsgType::SHELLY_CMD, pending.seq, encode_shelly_cmd(pending.cmd),
                    DEFAULT_RELAY_TTL, 0, pending.origin_override);
    pending_shelly_cmds_.push_back(pending);
    return true;
  }

  uint32_t target_hash = 0;
  if (!target_light_entity_id.empty()) {
    target_hash = fnv1a_32(target_light_entity_id);
  } else if (!target_fan_device_id.empty()) {
    target_hash = fnv1a_32(target_fan_device_id);
  } else {
    return false;
  }

  CmdPayload cmd;
  cmd.fan_key_hash = target_hash;
  cmd.opcode = CmdOpcode::LIGHT_TOGGLE;

  PendingCmd pending;
  pending.seq = source_seq != 0 ? source_seq : next_seq_++;
  pending.origin_override = source_id;
  pending.cmd = cmd;
  pending.fan_key_hash = target_hash;
  pending.created_ms = now_ms;
  pending.last_tx_ms = now_ms;
  pending.attempts = 1;

  broadcast_frame(MsgType::CMD, pending.seq, encode_cmd(pending.cmd), DEFAULT_RELAY_TTL, 0,
                  pending.origin_override);
  pending_cmds_.push_back(pending);
  return true;
}

#ifdef USE_TUYA_BLE_FAN

tuya_ble_fan::TuyaBleFanDevice *EspNowFanBridge::hub_find_device(uint32_t fan_key_hash) {
  for (auto *dev : tuya_ble_fan::TuyaBleFanRegistry::instance().all_devices()) {
    if (dev == nullptr) continue;
    uint32_t h = compute_fan_key(dev->fan_entity_id(), dev->light_entity_id(), dev->name());
    if (h == fan_key_hash) return dev;
    if (!dev->light_entity_id().empty() && fnv1a_32(dev->light_entity_id()) == fan_key_hash) {
      return dev;
    }
    if (!dev->device_id().empty() && fnv1a_32(dev->device_id()) == fan_key_hash) {
      return dev;
    }
  }
  return nullptr;
}

bool EspNowFanBridge::hub_handle_cmd(const CmdPayload &cmd, uint32_t origin_id, uint16_t seq,
                                     uint32_t now_ms) {
  auto *dev = hub_find_device(cmd.fan_key_hash);
  if (dev == nullptr) {
    return false;  // Not managed by this hub — let multi-hop relay forward it
  }

  AckPayload ack;
  ack.ack_seq = seq;

  // Deduplicate command execution across retries when an ACK was lost,
  // so non-idempotent opcodes (like LIGHT_TOGGLE) never double-fire.
  if (origin_id != 0 &&
      !cmd_exec_dedup_.accept(origin_id, MsgType::CMD, seq, 0, now_ms, RELAY_DEDUP_TTL_MS)) {
    ESP_LOGD(TAG, "[%s] Duplicate CMD seq=%u from origin=0x%08X (re-ACKing only)",
             dev->name().c_str(), seq, static_cast<unsigned>(origin_id));
    ack.status = AckStatus::OK;
    broadcast_frame(MsgType::ACK, seq, encode_ack(ack));
    return true;
  }

  ESP_LOGI(TAG, "[%s] RX ESP-NOW CMD seq=%u opcode=%u args=(%d,%d,%d)", dev->name().c_str(), seq,
           static_cast<unsigned>(cmd.opcode), cmd.arg0, cmd.arg1, cmd.arg2);

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
    case CmdOpcode::LIGHT_TOGGLE:
      dev->set_light_power(!dev->light_on());
      break;
    default:
      ack.status = AckStatus::INVALID_CMD;
      broadcast_frame(MsgType::ACK, seq, encode_ack(ack));
      return true;
  }

  ack.status = AckStatus::OK;
  broadcast_frame(MsgType::ACK, seq, encode_ack(ack));
  return true;
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

#ifdef USE_SHELLY_BLE_BRIDGE

bool EspNowFanBridge::hub_handle_shelly_cmd(const ShellyCmdPayload &cmd, uint32_t origin_id,
                                            uint16_t seq, uint32_t now_ms) {
  auto &reg = shelly_ble_bridge::ShellyBleBridgeRegistry::instance();
  if (!reg.handles_device(cmd.device_id)) {
    return false;  // Not managed by this hub — let multi-hop relay forward it
  }
  if (origin_id != 0 &&
      !cmd_exec_dedup_.accept(origin_id, MsgType::SHELLY_CMD, seq, 0, now_ms, RELAY_DEDUP_TTL_MS)) {
    AckPayload ack;
    ack.ack_seq = seq;
    ack.status = AckStatus::OK;
    broadcast_frame(MsgType::ACK, seq, encode_ack(ack));
    return true;
  }
  bool accepted = reg.enqueue_command(cmd.device_id, cmd.channel, static_cast<uint8_t>(cmd.opcode),
                                      cmd.arg, cmd.flags, seq);
  if (!accepted) {
    return false;
  }
  AckPayload ack;
  ack.ack_seq = seq;
  ack.status = AckStatus::OK;
  broadcast_frame(MsgType::ACK, seq, encode_ack(ack));
  return true;
}

void EspNowFanBridge::hub_broadcast_shelly_state(const shelly_ble_bridge::ShellyCachedState &st) {
  if (!espnow_ready_ || !st.has_state) return;
  ShellyStatePayload out;
  out.device_id = st.device_id;
  out.channel = st.channel;
  out.kind = static_cast<ShellyKind>(st.kind);
  out.state_flags = st.state_flags;
  out.position = st.position;
  out.ble_rssi = st.ble_rssi;
  broadcast_frame(MsgType::SHELLY_STATE, next_seq_++, encode_shelly_state(out));
}

void EspNowFanBridge::hub_broadcast_all_shelly_states() {
  for (const auto &st : shelly_ble_bridge::ShellyBleBridgeRegistry::instance().all_cached_states()) {
    hub_broadcast_shelly_state(st);
  }
}

#endif  // USE_SHELLY_BLE_BRIDGE

// ============================================================================
// CYD-side implementation
// ============================================================================

RemoteFanState *EspNowFanBridge::cyd_find_remote_fan(uint32_t fan_key_hash) {
  for (auto &rf : remote_fans_) {
    if (rf.fan_key_hash == fan_key_hash) return &rf;
  }
  return nullptr;
}

RemoteShellyState *EspNowFanBridge::cyd_find_remote_shelly(uint32_t device_id, uint8_t channel) {
  for (auto &rs : remote_shellys_) {
    if (rs.device_id == device_id && rs.channel == channel) return &rs;
  }
  return nullptr;
}

void EspNowFanBridge::cyd_handle_shelly_state(const ShellyStatePayload &st, uint32_t now_ms) {
  auto *rs = cyd_find_remote_shelly(st.device_id, st.channel);
  if (rs == nullptr) return;

  const bool prev_has = rs->has_state;
  const bool prev_reach = rs->espnow_reachable;
  const uint8_t prev_flags = rs->state_flags;
  const uint8_t prev_pos = rs->position;

  rs->has_state = true;
  rs->espnow_reachable = true;
  rs->last_seen_ms = now_ms;
  rs->state_flags = st.state_flags;
  rs->position = st.position;
  rs->ble_rssi = st.ble_rssi;

  if (!prev_reach) {
    ESP_LOGI(TAG, "[%s] Shelly ESP-NOW state received (flags=0x%02X pos=%u rssi=%d)",
             rs->name.c_str(), static_cast<unsigned>(rs->state_flags),
             static_cast<unsigned>(rs->position), static_cast<int>(rs->ble_rssi));
  }

  if (!prev_has || !prev_reach || prev_flags != rs->state_flags || prev_pos != rs->position) {
    ui_dirty_ = true;
  }
}

void EspNowFanBridge::cyd_handle_state(const StatePayload &st, uint32_t now_ms) {
  auto *rf = cyd_find_remote_fan(st.fan_key_hash);
  if (rf == nullptr) return;

  const bool prev_has_state = rf->has_state;
  const bool prev_reachable = rf->espnow_reachable;
  const RemoteBleConnStatus prev_ble_status = rf->ble_status;
  const bool prev_fan_on = rf->fan_on;
  const uint8_t prev_fan_speed = rf->fan_speed;
  const bool prev_fan_reverse = rf->fan_reverse;
  const uint8_t prev_fan_preset = rf->fan_preset;
  const bool prev_light_on = rf->light_on;
  const uint16_t prev_light_brightness = rf->light_brightness;
  const uint16_t prev_light_color_temp = rf->light_color_temp;

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

  if (!prev_reachable) {
    ESP_LOGI(TAG, "[%s] ESP-NOW hub reachable (ble_status=%u, rssi=%d)", rf->name.c_str(),
             static_cast<unsigned>(rf->ble_status), static_cast<int>(rf->ble_rssi));
  }

  const bool fan_changed = !prev_has_state || prev_fan_on != rf->fan_on ||
                           prev_fan_speed != rf->fan_speed || prev_fan_reverse != rf->fan_reverse ||
                           prev_fan_preset != rf->fan_preset;
  const bool light_changed = !prev_has_state || prev_light_on != rf->light_on ||
                             prev_light_brightness != rf->light_brightness ||
                             prev_light_color_temp != rf->light_color_temp;
  const bool link_changed = !prev_reachable || prev_ble_status != rf->ble_status;

  if (!fan_changed && !light_changed && !link_changed) {
    return;  // Identical heartbeat snapshot — skip reconcile and display redraw
  }

  if (fan_changed && !rf->fan_entity_id.empty()) {
    EspNowFanRegistry::instance().notify_state_changed(rf->fan_entity_id,
                                                       rf->fan_on ? "on" : "off");
    EspNowFanRegistry::instance().notify_state_changed(rf->fan_entity_id + "|percentage",
                                                       std::to_string(rf->fan_percentage()));
    EspNowFanRegistry::instance().notify_state_changed(rf->fan_entity_id + "|direction",
                                                       rf->fan_reverse ? "reverse" : "forward");
  }
  if (light_changed && !rf->light_entity_id.empty()) {
    EspNowFanRegistry::instance().notify_state_changed(rf->light_entity_id,
                                                       rf->light_on ? "on" : "off");
  }
  ui_dirty_ = true;
}

void EspNowFanBridge::cyd_handle_ack(const AckPayload &ack, uint32_t now_ms) {
  for (auto it = pending_cmds_.begin(); it != pending_cmds_.end(); ++it) {
    if (it->seq == ack.ack_seq) {
      ESP_LOGD(TAG, "RX ESP-NOW ACK seq=%u status=%u", ack.ack_seq,
               static_cast<unsigned>(ack.status));
      if (auto *rf = cyd_find_remote_fan(it->fan_key_hash)) {
        if (!rf->espnow_reachable) {
          rf->espnow_reachable = true;
          ui_dirty_ = true;
        }
        rf->last_seen_ms = now_ms;
      }
      pending_cmds_.erase(it);
      return;
    }
  }
  for (auto it = pending_shelly_cmds_.begin(); it != pending_shelly_cmds_.end(); ++it) {
    if (it->seq == ack.ack_seq) {
      ESP_LOGD(TAG, "RX ESP-NOW Shelly ACK seq=%u status=%u", ack.ack_seq,
               static_cast<unsigned>(ack.status));
      if (auto *rs = cyd_find_remote_shelly(it->cmd.device_id, it->cmd.channel)) {
        if (!rs->espnow_reachable) {
          rs->espnow_reachable = true;
          ui_dirty_ = true;
        }
        rs->last_seen_ms = now_ms;
      }
      pending_shelly_cmds_.erase(it);
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

  ESP_LOGD(TAG, "TX ESP-NOW CMD seq=%u opcode=%u args=(%d,%d,%d)", pending.seq,
           static_cast<unsigned>(cmd.opcode), cmd.arg0, cmd.arg1, cmd.arg2);
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

void EspNowFanBridge::cyd_queue_shelly_cmd(const ShellyCmdPayload &cmd, uint32_t now_ms) {
  PendingShellyCmd pending;
  pending.seq = next_seq_++;
  pending.cmd = cmd;
  pending.created_ms = now_ms;
  pending.last_tx_ms = now_ms;
  pending.attempts = 1;

  ESP_LOGD(TAG, "TX ESP-NOW SHELLY_CMD seq=%u dev=0x%08X ch=%u op=%u arg=%u", pending.seq,
           static_cast<unsigned>(cmd.device_id), static_cast<unsigned>(cmd.channel),
           static_cast<unsigned>(cmd.opcode), static_cast<unsigned>(cmd.arg));
  broadcast_frame(MsgType::SHELLY_CMD, pending.seq, encode_shelly_cmd(pending.cmd));

  // Coalesce older pending commands for the same (device_id, channel)
  for (auto it = pending_shelly_cmds_.begin(); it != pending_shelly_cmds_.end();) {
    if (it->cmd.device_id == cmd.device_id && it->cmd.channel == cmd.channel) {
      it = pending_shelly_cmds_.erase(it);
    } else {
      ++it;
    }
  }
  pending_shelly_cmds_.push_back(pending);
}

void EspNowFanBridge::cyd_tick_pending_cmds(uint32_t now_ms) {
  for (auto it = pending_cmds_.begin(); it != pending_cmds_.end();) {
    if (static_cast<int32_t>(now_ms - it->last_tx_ms) <
        static_cast<int32_t>(CMD_RETRY_INTERVAL_MS)) {
      ++it;
      continue;
    }
    if (it->attempts >= CMD_MAX_ATTEMPTS) {
      ESP_LOGW(TAG, "ESP-NOW cmd seq=%u timed out after %u attempts", it->seq, it->attempts);
      if (auto *rf = cyd_find_remote_fan(it->fan_key_hash)) {
        if (rf->espnow_reachable) {
          rf->espnow_reachable = false;
          ui_dirty_ = true;
        }
      }
      it = pending_cmds_.erase(it);
      continue;
    }
    it->attempts++;
    it->last_tx_ms = now_ms;
    broadcast_frame(MsgType::CMD, it->seq, encode_cmd(it->cmd), DEFAULT_RELAY_TTL, it->attempts,
                    it->origin_override);
    ++it;
  }

  for (auto it = pending_shelly_cmds_.begin(); it != pending_shelly_cmds_.end();) {
    if (static_cast<int32_t>(now_ms - it->last_tx_ms) <
        static_cast<int32_t>(CMD_RETRY_INTERVAL_MS)) {
      ++it;
      continue;
    }
    if (it->attempts >= CMD_MAX_ATTEMPTS) {
      ESP_LOGW(TAG, "ESP-NOW Shelly cmd seq=%u timed out after %u attempts", it->seq, it->attempts);
      if (auto *rs = cyd_find_remote_shelly(it->cmd.device_id, it->cmd.channel)) {
        if (rs->espnow_reachable) {
          rs->espnow_reachable = false;
          ui_dirty_ = true;
        }
      }
      it = pending_shelly_cmds_.erase(it);
      continue;
    }
    it->attempts++;
    it->last_tx_ms = now_ms;
    broadcast_frame(MsgType::SHELLY_CMD, it->seq, encode_shelly_cmd(it->cmd), DEFAULT_RELAY_TTL,
                    it->attempts, it->origin_override);
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
    ui_dirty_ = true;
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
  ui_dirty_ = true;
  return true;
}

bool EspNowFanBridge::send_shelly_action(
    RemoteShellyState *sh, const std::string &action,
    const std::vector<std::pair<std::string, std::string>> &data) {
  if (sh == nullptr) return false;
  const uint32_t now = millis();

  // Strip domain prefix if present (e.g. "switch.toggle" -> "toggle")
  std::string act = action;
  size_t dot = act.find('.');
  if (dot != std::string::npos) act = act.substr(dot + 1);

  ShellyCmdPayload cmd;
  cmd.device_id = sh->device_id;
  cmd.channel = sh->channel;
  cmd.arg = 0;
  cmd.flags = 0;

  if (!sh->is_cover) {
    if (act == "toggle") {
      cmd.opcode = ShellyOpcode::SW_TOGGLE;
      sh->state_flags ^= SHELLY_FLAG_ON_OR_OPEN;
    } else if (act == "turn_on") {
      cmd.opcode = ShellyOpcode::SW_ON;
      sh->state_flags |= SHELLY_FLAG_ON_OR_OPEN;
    } else if (act == "turn_off") {
      cmd.opcode = ShellyOpcode::SW_OFF;
      sh->state_flags &= static_cast<uint8_t>(~SHELLY_FLAG_ON_OR_OPEN);
    } else {
      return false;
    }
  } else {
    if (act == "open_cover") {
      cmd.opcode = ShellyOpcode::COV_OPEN;
      sh->state_flags = static_cast<uint8_t>((sh->state_flags & ~SHELLY_FLAG_MOTION_MASK) |
                                             (1u << SHELLY_FLAG_MOTION_SHIFT) |
                                             SHELLY_FLAG_ON_OR_OPEN);
    } else if (act == "close_cover") {
      cmd.opcode = ShellyOpcode::COV_CLOSE;
      sh->state_flags = static_cast<uint8_t>((sh->state_flags & ~SHELLY_FLAG_MOTION_MASK) |
                                             (2u << SHELLY_FLAG_MOTION_SHIFT));
    } else if (act == "stop_cover") {
      cmd.opcode = ShellyOpcode::COV_STOP;
      sh->state_flags &= static_cast<uint8_t>(~SHELLY_FLAG_MOTION_MASK);
    } else if (act == "set_cover_position") {
      const auto *pos_s = find_data_value(data, "position");
      int pos = pos_s ? clamp_int(std::atoi(pos_s->c_str()), 0, 100) : 50;
      cmd.opcode = ShellyOpcode::COV_POS;
      cmd.arg = static_cast<uint8_t>(pos);
      if (sh->has_state && sh->position <= 100) {
        uint8_t motion = (pos > sh->position) ? 1 : ((pos < sh->position) ? 2 : 0);
        sh->state_flags = static_cast<uint8_t>((sh->state_flags & ~SHELLY_FLAG_MOTION_MASK) |
                                               (motion << SHELLY_FLAG_MOTION_SHIFT));
      }
      if (pos > 0) {
        sh->state_flags |= SHELLY_FLAG_ON_OR_OPEN;
      } else {
        sh->state_flags &= static_cast<uint8_t>(~SHELLY_FLAG_ON_OR_OPEN);
      }
      sh->position = static_cast<uint8_t>(pos);
    } else {
      return false;
    }
  }

  sh->has_state = true;
  cyd_queue_shelly_cmd(cmd, now);
  ui_dirty_ = true;
  return true;
}

}  // namespace espnow_fan_bridge
}  // namespace esphome

#endif  // USE_ESP32
