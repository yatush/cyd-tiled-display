#include "shelly_ble_bridge.h"

#ifdef USE_ESP32

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "esphome/core/application.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"

#ifdef USE_API
#include "esphome/components/api/api_server.h"
#endif

#ifdef USE_TUYA_BLE_FAN
#include "esphome/components/tuya_ble_fan/tuya_ble_fan.h"
#include "esphome/components/tuya_ble_fan/tuya_ble_fan_registry.h"
#endif

namespace esphome {
namespace shelly_ble_bridge {

static const char *const TAG = "shelly_ble_bridge";

namespace {

inline bool is_ha_api_connected() {
#ifdef USE_API
  return api::global_api_server != nullptr && api::global_api_server->is_connected();
#else
  return false;
#endif
}

}  // namespace

void ShellyBleBridge::add_known_name(const std::string &mac_address, const std::string &name) {
  std::string norm = normalize_mac_hex(mac_address);
  if (norm.size() != 12 || name.empty()) return;
  known_names_[shelly_device_id_from_mac(norm)] = name;
}

void ShellyBleBridge::add_shelly(const std::string &name, const std::string &mac_address,
                                 uint8_t channel, ShellyBleKind kind,
                                 const std::string &entity_id) {
  ManagedShelly item;
  item.name = name;
  item.mac_address = normalize_mac_hex(mac_address);
  item.device_id = shelly_device_id_from_mac(item.mac_address);
  item.channel = channel;
  item.kind = kind;
  item.entity_id = entity_id;
  item.static_configured = true;
  shellys_.push_back(std::move(item));
}

void ShellyBleBridge::add_detached_switch(const std::string &name, const std::string &mac_address,
                                          uint8_t input_channel,
                                          const std::string &target_fan_device_id,
                                          const std::string &target_light_entity_id) {
  DetachedSwitchBinding binding;
  binding.name = name;
  binding.mac_address = normalize_mac_hex(mac_address);
  binding.source_id = shelly_device_id_from_mac(binding.mac_address);
  binding.input_channel = input_channel;
  binding.target_fan_device_id = target_fan_device_id;
  binding.target_light_entity_id = target_light_entity_id;
  detached_switches_.push_back(std::move(binding));
}

void ShellyBleBridge::apply_detached_switches_blob(const std::string &rules) {
  detached_switches_.clear();
  size_t pos = 0;
  while (pos < rules.size()) {
    size_t nl = rules.find('\n', pos);
    std::string line = (nl == std::string::npos) ? rules.substr(pos) : rules.substr(pos, nl - pos);
    pos = (nl == std::string::npos) ? rules.size() : (nl + 1);
    if (line.empty()) continue;

    // Format: name|mac|input_channel|target_fan_device_id|target_light_entity_id
    std::vector<std::string> parts;
    size_t p = 0;
    while (true) {
      size_t bar = line.find('|', p);
      if (bar == std::string::npos) {
        parts.push_back(line.substr(p));
        break;
      }
      parts.push_back(line.substr(p, bar - p));
      p = bar + 1;
    }
    if (parts.size() < 5) continue;
    std::string norm_mac = normalize_mac_hex(parts[1]);
    if (norm_mac.size() != 12) continue;
    int ch = std::atoi(parts[2].c_str());
    if (ch < 0) ch = 0;
    if (ch > 3) ch = 3;
    add_detached_switch(parts[0].empty() ? norm_mac : parts[0], norm_mac,
                        static_cast<uint8_t>(ch), parts[3], parts[4]);
  }
}

void ShellyBleBridge::on_sync_detached_switches(std::string rules) {
  apply_detached_switches_blob(rules);
  PersistedDetachedBlob blob{};
  blob.valid = 1;
  size_t copy_len = rules.size() < (sizeof(blob.data) - 1) ? rules.size() : (sizeof(blob.data) - 1);
  if (copy_len > 0) {
    std::memcpy(blob.data, rules.data(), copy_len);
  }
  blob.data[copy_len] = '\0';
  detached_pref_.save(&blob);
  global_preferences->sync();
  ESP_LOGI(TAG, "Live-synced %u detached switch rules from HA and persisted to NVS",
           static_cast<unsigned>(detached_switches_.size()));
}

void ShellyBleBridge::setup() {
  ShellyBleBridgeRegistry::instance().set_cmd_handler(
      [this](uint32_t device_id, uint8_t channel, uint8_t opcode, uint8_t arg, uint8_t flags,
             uint16_t cmd_seq) {
        return this->enqueue_command(device_id, channel, opcode, arg, flags, cmd_seq);
      });
  ShellyBleBridgeRegistry::instance().set_device_predicate(
      [this](uint32_t device_id) { return this->handles_device(device_id); });
  ShellyBleBridgeRegistry::instance().set_snapshot_provider(
      [this]() { return this->get_cached_states(); });

  detached_pref_ = global_preferences->make_preference<PersistedDetachedBlob>(
      fnv1a_32(std::string("shelly_ds_v1")));
  PersistedDetachedBlob saved{};
  if (detached_pref_.load(&saved) && saved.valid == 1) {
    saved.data[sizeof(saved.data) - 1] = '\0';
    apply_detached_switches_blob(std::string(saved.data));
    ESP_LOGI(TAG, "Restored %u live-synced detached switch rules from NVS",
             static_cast<unsigned>(detached_switches_.size()));
  }

#ifdef USE_API_CUSTOM_SERVICES
  register_service(&ShellyBleBridge::on_sync_detached_switches, "sync_shelly_detached_switches",
                   {"rules"});
#endif

  const uint32_t now = millis();
  last_scan_check_ms_ = now;
  last_visible_publish_ms_ = now;
  publish_visible_shellys(now, true);
  ESP_LOGI(TAG, "Shelly BLE Bridge initialized (dynamic discovery active): %u static shellys, %u detached switches",
           static_cast<unsigned>(shellys_.size()),
           static_cast<unsigned>(detached_switches_.size()));
}

void ShellyBleBridge::dump_config() {
  ESP_LOGCONFIG(TAG, "Shelly BLE Bridge:");
  ESP_LOGCONFIG(TAG, "  Dynamic Discovery: ENABLED (max=%u, stale=%us)",
                static_cast<unsigned>(MAX_DYNAMIC_SHELLYS),
                static_cast<unsigned>(SHELLY_BLE_STALE_MS / 1000));
  ESP_LOGCONFIG(TAG, "  Static Shellys: %u", static_cast<unsigned>(shellys_.size()));
  for (const auto &s : shellys_) {
    ESP_LOGCONFIG(TAG, "    - %s (mac=%s id=0x%08X ch=%u kind=%u entity=%s)", s.name.c_str(),
                  s.mac_address.c_str(), static_cast<unsigned>(s.device_id),
                  static_cast<unsigned>(s.channel), static_cast<unsigned>(s.kind),
                  s.entity_id.c_str());
  }
  ESP_LOGCONFIG(TAG, "  Detached Switch Bindings: %u",
                static_cast<unsigned>(detached_switches_.size()));
  for (const auto &d : detached_switches_) {
    ESP_LOGCONFIG(TAG, "    - %s (mac=%s id=0x%08X in=%u -> fan_dev=%s light=%s)", d.name.c_str(),
                  d.mac_address.c_str(), static_cast<unsigned>(d.source_id),
                  static_cast<unsigned>(d.input_channel), d.target_fan_device_id.c_str(),
                  d.target_light_entity_id.c_str());
  }
}

void ShellyBleBridge::loop() {
  const uint32_t now = millis();
  tick_tx(now);

  // Keep passive BLE scanning running for dynamic Shelly state/input beacons even when
  // headless_hub_base.yaml configures esp32_ble_tracker with continuous: false, while
  // deferring whenever a Tuya BLE GATT connect/handshake is in flight.
  if (parent_ != nullptr && tx_state_ == TxState::IDLE &&
      static_cast<int32_t>(now - last_scan_check_ms_) >=
          static_cast<int32_t>(SCAN_RESTART_DELAY_MS)) {
    last_scan_check_ms_ = now;
#ifdef USE_TUYA_BLE_FAN
    if (tuya_ble_fan::TuyaBleFanRegistry::instance().has_in_flight_connect()) {
      return;
    }
#endif
    parent_->start_scan_if_idle();
  }

  if (visible_shellys_sensor_ != nullptr &&
      static_cast<int32_t>(now - last_visible_publish_ms_) >=
          static_cast<int32_t>(VISIBLE_PUBLISH_INTERVAL_MS)) {
    publish_visible_shellys(now, false);
  }
}

void ShellyBleBridge::on_scan_end() { last_scan_check_ms_ = millis(); }

bool ShellyBleBridge::parse_device(const esp32_ble_tracker::ESPBTDevice &device) {
  const auto uuid_state = esp32_ble_tracker::ESPBTUUID::from_uint16(UUID_SHELLY_STATE);
  const auto uuid_input = esp32_ble_tracker::ESPBTUUID::from_uint16(UUID_SHELLY_INPUT);

  for (const auto &sd : device.get_service_datas()) {
    const bool is_state = (sd.uuid == uuid_state);
    const bool is_input = (sd.uuid == uuid_input);
    if (!is_state && !is_input) continue;
    if (sd.data.size() != SHELLY_BLE_PAYLOAD_SIZE) continue;

    ShellyBleBeacon beacon;
    if (!decode_ble_beacon(network_key_, sd.data.data(), sd.data.size(), beacon)) {
      ESP_LOGD(TAG, "Dropped Shelly BLE beacon (bad auth tag)");
      continue;
    }

    if (is_state) {
      handle_state_beacon(beacon, device.get_rssi(), device.get_name());
    } else {
      handle_input_beacon(beacon, device.get_rssi());
    }
  }
  return false;  // Never claim GATT connection
}

void ShellyBleBridge::gap_event_handler(esp_gap_ble_cb_event_t event,
                                        esp_ble_gap_cb_param_t *param) {
  if (event == ESP_GAP_BLE_ADV_DATA_RAW_SET_COMPLETE_EVT) {
    if (tx_state_ == TxState::CONFIGURING) {
      adv_raw_ready_.store(true);
    }
  }
}

std::string ShellyBleBridge::resolve_display_name(uint32_t device_id,
                                                  const std::string &ble_name) const {
  auto it = known_names_.find(device_id);
  if (it != known_names_.end() && !it->second.empty()) {
    return it->second;
  }
  for (const auto &d : detached_switches_) {
    if (d.source_id == device_id && !d.name.empty()) {
      return d.name;
    }
  }
  if (!ble_name.empty()) {
    return ble_name;
  }
  char buf[24];
  std::snprintf(buf, sizeof(buf), "0x%08X", static_cast<unsigned>(device_id));
  return std::string(buf);
}

ManagedShelly *ShellyBleBridge::find_shelly(uint32_t device_id, uint8_t channel) {
  for (auto &s : shellys_) {
    if (s.device_id == device_id && s.channel == channel) {
      return &s;
    }
  }
  return nullptr;
}

ManagedShelly *ShellyBleBridge::find_or_create_shelly(uint32_t device_id, uint8_t channel,
                                                      ShellyBleKind kind, uint32_t now_ms,
                                                      const std::string &ble_name) {
  if (auto *existing = find_shelly(device_id, channel)) {
    if (!existing->static_configured && existing->name.rfind("0x", 0) == 0) {
      existing->name = resolve_display_name(device_id, ble_name);
    }
    return existing;
  }

  // Dynamic discovery: add up to MAX_DYNAMIC_SHELLYS, evicting oldest stale non-static entry if full
  if (shellys_.size() >= MAX_DYNAMIC_SHELLYS) {
    ManagedShelly *evict = nullptr;
    uint32_t oldest_age = 0;
    for (auto &s : shellys_) {
      if (s.static_configured) continue;
      uint32_t age = static_cast<uint32_t>(now_ms - s.last_seen_ms);
      if (age >= SHELLY_BLE_STALE_MS && (evict == nullptr || age > oldest_age)) {
        evict = &s;
        oldest_age = age;
      }
    }
    if (evict != nullptr) {
      evict->name = resolve_display_name(device_id, ble_name);
      evict->mac_address.clear();
      evict->device_id = device_id;
      evict->channel = channel;
      evict->kind = kind;
      evict->entity_id.clear();
      evict->has_state = false;
      return evict;
    }
    return nullptr;
  }

  ManagedShelly item;
  item.name = resolve_display_name(device_id, ble_name);
  item.device_id = device_id;
  item.channel = channel;
  item.kind = kind;
  item.static_configured = false;
  shellys_.push_back(std::move(item));
  ESP_LOGI(TAG, "Dynamically discovered Shelly '%s' (0x%08X ch=%u kind=%u)",
           shellys_.back().name.c_str(), static_cast<unsigned>(device_id),
           static_cast<unsigned>(channel), static_cast<unsigned>(kind));
  return &shellys_.back();
}

bool ShellyBleBridge::handles_device(uint32_t device_id) const {
  const uint32_t now = millis();
  for (const auto &s : shellys_) {
    if (s.device_id != device_id) continue;
    if (s.static_configured) return true;
    if (s.has_state && static_cast<uint32_t>(now - s.last_seen_ms) <= SHELLY_BLE_STALE_MS) {
      return true;
    }
  }
  return false;
}

void ShellyBleBridge::publish_visible_shellys(uint32_t now_ms, bool force) {
  last_visible_publish_ms_ = now_ms;
  if (visible_shellys_sensor_ == nullptr) return;

  struct VisibleItem {
    uint32_t device_id;
    std::string label;
    int8_t rssi;
  };
  std::vector<VisibleItem> items;
  for (const auto &s : shellys_) {
    if (!s.has_state) continue;
    if (static_cast<uint32_t>(now_ms - s.last_seen_ms) > SHELLY_BLE_STALE_MS) continue;
    bool dup = false;
    for (auto &it : items) {
      if (it.device_id == s.device_id) {
        if (s.ble_rssi > it.rssi) it.rssi = s.ble_rssi;
        dup = true;
        break;
      }
    }
    if (!dup) {
      items.push_back(VisibleItem{s.device_id, s.name, s.ble_rssi});
    }
  }

  // Sort strongest signal first
  std::sort(items.begin(), items.end(),
            [](const VisibleItem &a, const VisibleItem &b) { return a.rssi > b.rssi; });

  static constexpr size_t MAX_HA_STATE_LEN = 240;
  std::string summary;
  for (size_t i = 0; i < items.size(); ++i) {
    char buf[64];
    if (!items[i].label.empty()) {
      std::snprintf(buf, sizeof(buf), "%s (%ddBm)", items[i].label.c_str(),
                    static_cast<int>(items[i].rssi));
    } else {
      std::snprintf(buf, sizeof(buf), "0x%08X (%ddBm)", static_cast<unsigned>(items[i].device_id),
                    static_cast<int>(items[i].rssi));
    }
    std::string entry(buf);
    const size_t sep_len = summary.empty() ? 0 : 2;
    const size_t remaining = items.size() - i;
    if (summary.size() + sep_len + entry.size() > MAX_HA_STATE_LEN) {
      char tail[24];
      std::snprintf(tail, sizeof(tail), ", +%u more", static_cast<unsigned>(remaining));
      summary += tail;
      break;
    }
    if (!summary.empty()) summary += ", ";
    summary += entry;
  }
  if (summary.empty()) summary = "none";

  if (force || summary != last_visible_summary_) {
    last_visible_summary_ = summary;
    visible_shellys_sensor_->publish_state(summary);
  }
}

void ShellyBleBridge::handle_state_beacon(const ShellyBleBeacon &beacon, int rssi,
                                          const std::string &ble_name) {
  const uint32_t now = millis();
  if (!state_dedup_.accept(beacon.source_id, beacon.seq, now, DEDUP_TTL_MS)) {
    return;
  }
  const bool was_known = (find_shelly(beacon.source_id, beacon.channel) != nullptr);
  auto *s = find_or_create_shelly(beacon.source_id, beacon.channel, beacon.kind, now, ble_name);
  if (s == nullptr) {
    return;
  }

  const bool was_fresh =
      s->has_state && static_cast<uint32_t>(now - s->last_seen_ms) <= SHELLY_BLE_STALE_MS;
  s->has_state = true;
  s->kind = beacon.kind;
  s->state_flags = beacon.state_flags;
  s->position = beacon.position;
  s->ble_rssi = static_cast<int8_t>(rssi < -127 ? -127 : (rssi > 0 ? 0 : rssi));
  s->last_seen_ms = now;

  ESP_LOGD(TAG, "[%s] RX Shelly BLE state seq=%u flags=0x%02X pos=%u rssi=%d", s->name.c_str(),
           beacon.seq, static_cast<unsigned>(s->state_flags), static_cast<unsigned>(s->position),
           static_cast<int>(s->ble_rssi));

  if (!was_known || !was_fresh) {
    publish_visible_shellys(now, false);
  }

  ShellyCachedState st;
  st.device_id = s->device_id;
  st.channel = s->channel;
  st.kind = static_cast<uint8_t>(s->kind);
  st.state_flags = s->state_flags;
  st.position = s->position;
  st.ble_rssi = s->ble_rssi;
  st.has_state = true;
  ShellyBleBridgeRegistry::instance().notify_state_updated(st);
}

void ShellyBleBridge::handle_input_beacon(const ShellyBleBeacon &beacon, int rssi) {
  if (beacon.kind != ShellyBleKind::INPUT_TOGGLE) return;
  if (!input_dedup_.accept(beacon.source_id, beacon.seq, millis(), DEDUP_TTL_MS)) {
    return;
  }

  const bool wifi_down = (beacon.state_flags & SHELLY_FLAG_WIFI_DOWN) != 0;
  const bool ha_up = is_ha_api_connected();

  for (const auto &binding : detached_switches_) {
    if (binding.source_id != beacon.source_id || binding.input_channel != beacon.channel) {
      continue;
    }

    if (ha_up && !wifi_down) {
      ESP_LOGD(TAG, "[%s] Detached input seq=%u ignored (HA connected & Shelly Wi-Fi up)",
               binding.name.c_str(), beacon.seq);
      return;
    }

    ESP_LOGI(TAG, "[%s] Detached input seq=%u offline fallback (ha=%d, wifi_down=%d, rssi=%d)",
             binding.name.c_str(), beacon.seq, ha_up ? 1 : 0, wifi_down ? 1 : 0, rssi);

    bool handled_locally = false;
#ifdef USE_TUYA_BLE_FAN
    tuya_ble_fan::TuyaBleFanDevice *target = nullptr;
    for (auto *dev : tuya_ble_fan::TuyaBleFanRegistry::instance().all_devices()) {
      if (dev == nullptr) continue;
      if (!binding.target_fan_device_id.empty() &&
          dev->device_id() == binding.target_fan_device_id) {
        target = dev;
        break;
      }
      if (!binding.target_light_entity_id.empty() &&
          dev->light_entity_id() == binding.target_light_entity_id) {
        target = dev;
        break;
      }
    }
    if (target != nullptr) {
      bool next_on = !target->light_on();
      ESP_LOGI(TAG, "[%s] Toggling Tuya BLE fan light '%s' -> %s", binding.name.c_str(),
               target->name().c_str(), next_on ? "ON" : "OFF");
      target->set_light_power(next_on);
      handled_locally = true;
    }
#endif
    if (!handled_locally) {
      if (ShellyBleBridgeRegistry::instance().toggle_remote_light(
              binding.target_fan_device_id, binding.target_light_entity_id, beacon.source_id,
              beacon.seq)) {
        ESP_LOGI(TAG, "[%s] Forwarded detached light toggle over ESP-NOW (dev=%s light=%s seq=%u)",
                 binding.name.c_str(), binding.target_fan_device_id.c_str(),
                 binding.target_light_entity_id.c_str(), beacon.seq);
      } else {
        ESP_LOGW(TAG, "[%s] Linked Tuya BLE fan not found locally and ESP-NOW forward unavailable "
                      "(dev=%s light=%s)",
                 binding.name.c_str(), binding.target_fan_device_id.c_str(),
                 binding.target_light_entity_id.c_str());
      }
    }
  }
}

bool ShellyBleBridge::enqueue_command(uint32_t device_id, uint8_t channel, uint8_t opcode,
                                      uint8_t arg, uint8_t flags, uint16_t cmd_seq) {
  if (!handles_device(device_id)) {
    return false;
  }
  ShellyBleCmd cmd;
  cmd.target_id = device_id;
  cmd.channel = channel;
  cmd.opcode = static_cast<ShellyBleOpcode>(opcode);
  cmd.arg = arg;
  cmd.flags = flags;
  if (cmd_seq != 0) {
    // Reuse CYD's ESP-NOW seq so multiple hubs in BLE range transmit the exact same
    // (target_id, seq) and the Shelly deduplicates any duplicate burst automatically.
    cmd.seq = cmd_seq;
  } else {
    cmd.seq = next_seq_++;
    if (next_seq_ == 0) next_seq_ = 1;
  }

  tx_queue_.enqueue(cmd);
  ESP_LOGI(TAG, "Queued Shelly BLE cmd target=0x%08X ch=%u op=%u arg=%u seq=%u (q=%u)",
           static_cast<unsigned>(device_id), static_cast<unsigned>(channel),
           static_cast<unsigned>(opcode), static_cast<unsigned>(arg), cmd.seq,
           static_cast<unsigned>(tx_queue_.size()));
  return true;
}

std::vector<ShellyCachedState> ShellyBleBridge::get_cached_states() const {
  const uint32_t now = millis();
  std::vector<ShellyCachedState> out;
  out.reserve(shellys_.size());
  for (const auto &s : shellys_) {
    if (!s.has_state) continue;
    if (!s.static_configured &&
        static_cast<uint32_t>(now - s.last_seen_ms) > SHELLY_BLE_STALE_MS) {
      continue;
    }
    ShellyCachedState st;
    st.device_id = s.device_id;
    st.channel = s.channel;
    st.kind = static_cast<uint8_t>(s.kind);
    st.state_flags = s.state_flags;
    st.position = s.position;
    st.ble_rssi = s.ble_rssi;
    st.has_state = true;
    out.push_back(st);
  }
  return out;
}

void ShellyBleBridge::start_next_tx(uint32_t now_ms) {
  ShellyBleCmd cmd;
  if (!tx_queue_.pop(cmd)) return;

  auto payload = encode_ble_cmd(network_key_, cmd);
  auto raw_adv = build_service_data_adv_raw(UUID_SHELLY_CMD, payload);

  adv_raw_ready_.store(false);
  esp_err_t err = esp_ble_gap_config_adv_data_raw(raw_adv.data(), raw_adv.size());
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "esp_ble_gap_config_adv_data_raw failed: %d", static_cast<int>(err));
    last_tx_done_ms_ = now_ms;
    return;
  }

  tx_state_ = TxState::CONFIGURING;
  tx_state_ms_ = now_ms;
}

void ShellyBleBridge::tick_tx(uint32_t now_ms) {
  if (tx_state_ == TxState::IDLE) {
    if (!tx_queue_.empty() &&
        static_cast<int32_t>(now_ms - last_tx_done_ms_) >= static_cast<int32_t>(TX_GAP_MS)) {
      start_next_tx(now_ms);
    }
    return;
  }

  if (tx_state_ == TxState::CONFIGURING) {
    if (adv_raw_ready_.exchange(false) ||
        static_cast<int32_t>(now_ms - tx_state_ms_) >= static_cast<int32_t>(TX_CONFIG_TIMEOUT_MS)) {
      esp_ble_adv_params_t adv_params{};
      adv_params.adv_int_min = 0x20;  // 20 ms
      adv_params.adv_int_max = 0x30;  // 30 ms
      adv_params.adv_type = ADV_TYPE_NONCONN_IND;
      adv_params.own_addr_type = BLE_ADDR_TYPE_PUBLIC;
      adv_params.channel_map = ADV_CHNL_ALL;
      adv_params.adv_filter_policy = ADV_FILTER_ALLOW_SCAN_ANY_CON_ANY;

      esp_err_t err = esp_ble_gap_start_advertising(&adv_params);
      if (err != ESP_OK) {
        ESP_LOGW(TAG, "esp_ble_gap_start_advertising failed: %d", static_cast<int>(err));
        tx_state_ = TxState::IDLE;
        last_tx_done_ms_ = now_ms;
        return;
      }
      tx_state_ = TxState::ADVERTISING;
      tx_state_ms_ = now_ms;
    }
    return;
  }

  if (tx_state_ == TxState::ADVERTISING) {
    if (static_cast<int32_t>(now_ms - tx_state_ms_) >= static_cast<int32_t>(TX_BURST_MS)) {
      esp_ble_gap_stop_advertising();
      tx_state_ = TxState::IDLE;
      last_tx_done_ms_ = now_ms;
    }
  }
}

}  // namespace shelly_ble_bridge
}  // namespace esphome

#endif  // USE_ESP32
