#include "shelly_ble_bridge.h"

#ifdef USE_ESP32

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

void ShellyBleBridge::setup() {
  ShellyBleBridgeRegistry::instance().set_cmd_handler(
      [this](uint32_t device_id, uint8_t channel, uint8_t opcode, uint8_t arg, uint8_t flags) {
        return this->enqueue_command(device_id, channel, opcode, arg, flags);
      });
  ShellyBleBridgeRegistry::instance().set_snapshot_provider(
      [this]() { return this->get_cached_states(); });
  last_scan_check_ms_ = millis();
  ESP_LOGI(TAG, "Shelly BLE Bridge initialized: %u shellys, %u detached switches",
           static_cast<unsigned>(shellys_.size()),
           static_cast<unsigned>(detached_switches_.size()));
}

void ShellyBleBridge::dump_config() {
  ESP_LOGCONFIG(TAG, "Shelly BLE Bridge:");
  ESP_LOGCONFIG(TAG, "  Managed Shellys: %u", static_cast<unsigned>(shellys_.size()));
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

  // Keep passive BLE scanning running for Shelly state/input beacons even when
  // headless_hub_base.yaml configures esp32_ble_tracker with continuous: false.
  // ESP32BLETracker::notify_scan_end_() only notifies listeners_ (not ESPBTClient
  // clients_), so we periodically check and call start_scan_if_idle() (which is
  // a no-op when scanning is already active), while deferring whenever a Tuya
  // BLE GATT connect/handshake is in flight.
  if ((!shellys_.empty() || !detached_switches_.empty()) && parent_ != nullptr &&
      tx_state_ == TxState::IDLE &&
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
      handle_state_beacon(beacon, device.get_rssi());
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

ManagedShelly *ShellyBleBridge::find_shelly(uint32_t device_id, uint8_t channel) {
  for (auto &s : shellys_) {
    if (s.device_id == device_id && s.channel == channel) {
      return &s;
    }
  }
  return nullptr;
}

bool ShellyBleBridge::handles_device(uint32_t device_id) const {
  for (const auto &s : shellys_) {
    if (s.device_id == device_id) return true;
  }
  return false;
}

void ShellyBleBridge::handle_state_beacon(const ShellyBleBeacon &beacon, int rssi) {
  if (!state_dedup_.accept(beacon.source_id, beacon.seq, millis(), DEDUP_TTL_MS)) {
    return;
  }
  auto *s = find_shelly(beacon.source_id, beacon.channel);
  if (s == nullptr) {
    ESP_LOGV(TAG, "Ignoring state beacon from unassigned Shelly 0x%08X ch=%u",
             static_cast<unsigned>(beacon.source_id), static_cast<unsigned>(beacon.channel));
    return;
  }

  s->has_state = true;
  s->kind = beacon.kind;
  s->state_flags = beacon.state_flags;
  s->position = beacon.position;
  s->ble_rssi = static_cast<int8_t>(rssi < -127 ? -127 : (rssi > 0 ? 0 : rssi));
  s->last_seen_ms = millis();

  ESP_LOGD(TAG, "[%s] RX Shelly BLE state seq=%u flags=0x%02X pos=%u rssi=%d", s->name.c_str(),
           beacon.seq, static_cast<unsigned>(s->state_flags), static_cast<unsigned>(s->position),
           static_cast<int>(s->ble_rssi));

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
    } else {
      ESP_LOGW(TAG, "[%s] Linked Tuya BLE fan not found on this hub (dev=%s light=%s)",
               binding.name.c_str(), binding.target_fan_device_id.c_str(),
               binding.target_light_entity_id.c_str());
    }
#endif
  }
}

bool ShellyBleBridge::enqueue_command(uint32_t device_id, uint8_t channel, uint8_t opcode,
                                      uint8_t arg, uint8_t flags) {
  if (!handles_device(device_id)) {
    return false;
  }
  ShellyBleCmd cmd;
  cmd.target_id = device_id;
  cmd.channel = channel;
  cmd.opcode = static_cast<ShellyBleOpcode>(opcode);
  cmd.arg = arg;
  cmd.flags = flags;
  cmd.seq = next_seq_++;
  if (next_seq_ == 0) next_seq_ = 1;

  tx_queue_.enqueue(cmd);
  ESP_LOGI(TAG, "Queued Shelly BLE cmd target=0x%08X ch=%u op=%u arg=%u seq=%u (q=%u)",
           static_cast<unsigned>(device_id), static_cast<unsigned>(channel),
           static_cast<unsigned>(opcode), static_cast<unsigned>(arg), cmd.seq,
           static_cast<unsigned>(tx_queue_.size()));
  return true;
}

std::vector<ShellyCachedState> ShellyBleBridge::get_cached_states() const {
  std::vector<ShellyCachedState> out;
  out.reserve(shellys_.size());
  for (const auto &s : shellys_) {
    if (!s.has_state) continue;
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
