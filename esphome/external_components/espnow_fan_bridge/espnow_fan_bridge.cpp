#include "espnow_fan_bridge_internal.h"

#ifdef USE_ESP32

namespace esphome {
namespace espnow_fan_bridge {

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
    const bool use_backup = !ha_entity_available || sit->second->wifi_down_fallback();
    if (!use_backup) {
      return false;  // Normal HA tier — let HA handle it
    }
    return bridge_->send_shelly_action(sit->second, action, data);
  }

  return false;
}

// ============================================================================
// Helpers
// ============================================================================


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

  // Register Wi-Fi & IP event hooks to track connect/disconnect, IPv4 readiness, and scan completion
  esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &EspNowFanBridge::wifi_event_handler,
                             this);
  esp_event_handler_register(IP_EVENT, ESP_EVENT_ANY_ID, &EspNowFanBridge::wifi_event_handler,
                             this);

  // Check initial Wi-Fi association & IPv4 state
  wifi_ap_record_t ap_info{};
  if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
    wifi_connected_.store(true);
  }
  esp_netif_t *sta_netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
  if (sta_netif != nullptr) {
    esp_netif_ip_info_t ip_info{};
    if (esp_netif_get_ip_info(sta_netif, &ip_info) == ESP_OK && ip_info.ip.addr != 0) {
      has_ip_.store(true);
    }
  }

  ensure_espnow_initialized();
  if (has_ip_.load()) {
    ensure_udp_initialized();
  }

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
  ESP_LOGCONFIG(TAG, "  LAN UDP Mirror Port: %u%s", static_cast<unsigned>(udp_port_),
                udp_port_ == 0 ? " (disabled)" : "");
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
  if (self == nullptr) return;

  if (event_base == WIFI_EVENT) {
    if (event_id == WIFI_EVENT_STA_CONNECTED) {
      self->wifi_connected_.store(true);
      self->wifi_event_dirty_.store(true);
    } else if (event_id == WIFI_EVENT_STA_DISCONNECTED) {
      self->wifi_connected_.store(false);
      self->has_ip_.store(false);
      self->wifi_event_dirty_.store(true);
    } else if (event_id == WIFI_EVENT_SCAN_DONE) {
      self->wifi_scan_done_flag_.store(true);
    }
  } else if (event_base == IP_EVENT) {
    if (event_id == IP_EVENT_STA_GOT_IP) {
      self->wifi_connected_.store(true);
      self->has_ip_.store(true);
      self->wifi_event_dirty_.store(true);
    } else if (event_id == IP_EVENT_STA_LOST_IP) {
      self->has_ip_.store(false);
    }
  }
}

void EspNowFanBridge::ensure_udp_initialized() {
  if (udp_port_ == 0 || udp_sock_ >= 0 || !has_ip_.load()) return;

  int sock = ::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  if (sock < 0) {
    ESP_LOGW(TAG, "Failed to create LAN UDP mirror socket");
    return;
  }

  int yes = 1;
  ::setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
  ::setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &yes, sizeof(yes));

  int flags = ::fcntl(sock, F_GETFL, 0);
  if (flags >= 0) {
    ::fcntl(sock, F_SETFL, flags | O_NONBLOCK);
  }

  struct sockaddr_in bind_addr{};
  bind_addr.sin_family = AF_INET;
  bind_addr.sin_port = htons(udp_port_);
  bind_addr.sin_addr.s_addr = htonl(INADDR_ANY);
  if (::bind(sock, reinterpret_cast<struct sockaddr *>(&bind_addr), sizeof(bind_addr)) < 0) {
    ESP_LOGW(TAG, "Failed to bind LAN UDP mirror socket on port %u",
             static_cast<unsigned>(udp_port_));
    ::close(sock);
    return;
  }

  udp_sock_ = sock;
  ESP_LOGI(TAG, "LAN UDP broadcast mirror listening on port %u", static_cast<unsigned>(udp_port_));
}

void EspNowFanBridge::close_udp() {
  if (udp_sock_ >= 0) {
    ::close(udp_sock_);
    udp_sock_ = -1;
  }
}

bool EspNowFanBridge::send_udp_broadcast(const std::vector<uint8_t> &frame) {
  if (udp_port_ == 0 || frame.empty() || !has_ip_.load()) return false;
  if (udp_sock_ < 0) {
    ensure_udp_initialized();
    if (udp_sock_ < 0) return false;
  }

  struct sockaddr_in dest{};
  dest.sin_family = AF_INET;
  dest.sin_port = htons(udp_port_);
  dest.sin_addr.s_addr = htonl(INADDR_BROADCAST);
  ssize_t sent = ::sendto(udp_sock_, frame.data(), frame.size(), 0,
                          reinterpret_cast<struct sockaddr *>(&dest), sizeof(dest));
  return sent == static_cast<ssize_t>(frame.size());
}

void EspNowFanBridge::poll_udp_rx() {
  if (udp_sock_ < 0) return;

  uint8_t buf[MAX_FRAME_SIZE];
  for (int i = 0; i < 16; i++) {
    struct sockaddr_in from{};
    socklen_t from_len = sizeof(from);
    ssize_t n = ::recvfrom(udp_sock_, buf, sizeof(buf), 0,
                           reinterpret_cast<struct sockaddr *>(&from), &from_len);
    if (n <= 0) break;

    RxPacket pkt;
    uint32_t ip_be = from.sin_addr.s_addr;
    pkt.src_mac = {0x02,
                   0x55,
                   static_cast<uint8_t>(ip_be & 0xFF),
                   static_cast<uint8_t>((ip_be >> 8) & 0xFF),
                   static_cast<uint8_t>((ip_be >> 16) & 0xFF),
                   static_cast<uint8_t>((ip_be >> 24) & 0xFF)};
    pkt.rx_channel = current_wifi_channel();
    pkt.data.assign(buf, buf + n);
    process_rx_packet(pkt);
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
  bool udp_ok = send_udp_broadcast(frame);
  return err == ESP_OK || udp_ok;
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

  // 1. Drain ESP-NOW RX queue safely on main thread
  std::deque<RxPacket> batch;
  portENTER_CRITICAL(&rx_mux_);
  batch.swap(rx_queue_);
  portEXIT_CRITICAL(&rx_mux_);

  for (const auto &pkt : batch) {
    process_rx_packet(pkt);
  }

  // 1b. Poll LAN UDP broadcast mirror when Wi-Fi has an IPv4 address
  if (has_ip_.load()) {
    ensure_udp_initialized();
    poll_udp_rx();
  } else if (udp_sock_ >= 0) {
    close_udp();
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

  // Drop our own echoes (ESP-NOW relay or UDP broadcast loopback) and duplicate frames
  if (hdr.origin_id != 0 && hdr.origin_id == local_origin_id_) {
    return;
  }
  if (!relay_dedup_.accept(hdr.origin_id, hdr.type, hdr.seq, hdr.hop_nonce, now,
                           RELAY_DEDUP_TTL_MS)) {
    return;
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


}  // namespace espnow_fan_bridge
}  // namespace esphome

#endif  // USE_ESP32
