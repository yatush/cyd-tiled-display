#include "espnow_fan_bridge_internal.h"

#ifdef USE_ESP32

namespace esphome {
namespace espnow_fan_bridge {

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

#ifdef USE_ESPNOW_CLIMATE

namespace {

uint8_t esphome_mode_to_wire(climate::ClimateMode mode) {
  switch (mode) {
    case climate::CLIMATE_MODE_COOL:
      return static_cast<uint8_t>(ClimateHvacMode::COOL);
    case climate::CLIMATE_MODE_HEAT:
      return static_cast<uint8_t>(ClimateHvacMode::HEAT);
    case climate::CLIMATE_MODE_DRY:
      return static_cast<uint8_t>(ClimateHvacMode::DRY);
    case climate::CLIMATE_MODE_FAN_ONLY:
      return static_cast<uint8_t>(ClimateHvacMode::FAN_ONLY);
    case climate::CLIMATE_MODE_HEAT_COOL:
    case climate::CLIMATE_MODE_AUTO:
      return static_cast<uint8_t>(ClimateHvacMode::AUTO);
    case climate::CLIMATE_MODE_OFF:
    default:
      return static_cast<uint8_t>(ClimateHvacMode::OFF);
  }
}

climate::ClimateMode wire_mode_to_esphome(uint8_t m) {
  switch (static_cast<ClimateHvacMode>(m)) {
    case ClimateHvacMode::COOL:
      return climate::CLIMATE_MODE_COOL;
    case ClimateHvacMode::HEAT:
      return climate::CLIMATE_MODE_HEAT;
    case ClimateHvacMode::DRY:
      return climate::CLIMATE_MODE_DRY;
    case ClimateHvacMode::FAN_ONLY:
      return climate::CLIMATE_MODE_FAN_ONLY;
    case ClimateHvacMode::AUTO:
      return climate::CLIMATE_MODE_HEAT_COOL;
    case ClimateHvacMode::OFF:
    default:
      return climate::CLIMATE_MODE_OFF;
  }
}

uint8_t esphome_fan_mode_to_wire(const optional<climate::ClimateFanMode> &fm) {
  if (!fm.has_value()) return static_cast<uint8_t>(ClimateFanMode::AUTO);
  switch (*fm) {
    case climate::CLIMATE_FAN_LOW:
      return static_cast<uint8_t>(ClimateFanMode::LOW);
    case climate::CLIMATE_FAN_MEDIUM:
    case climate::CLIMATE_FAN_MIDDLE:
      return static_cast<uint8_t>(ClimateFanMode::MEDIUM);
    case climate::CLIMATE_FAN_HIGH:
      return static_cast<uint8_t>(ClimateFanMode::HIGH);
    case climate::CLIMATE_FAN_QUIET:
      return static_cast<uint8_t>(ClimateFanMode::QUIET);
    case climate::CLIMATE_FAN_FOCUS:
      return static_cast<uint8_t>(ClimateFanMode::TURBO);
    case climate::CLIMATE_FAN_AUTO:
    default:
      return static_cast<uint8_t>(ClimateFanMode::AUTO);
  }
}

climate::ClimateFanMode wire_fan_mode_to_esphome(uint8_t m) {
  switch (static_cast<ClimateFanMode>(m)) {
    case ClimateFanMode::LOW:
      return climate::CLIMATE_FAN_LOW;
    case ClimateFanMode::MEDIUM:
      return climate::CLIMATE_FAN_MEDIUM;
    case ClimateFanMode::HIGH:
      return climate::CLIMATE_FAN_HIGH;
    case ClimateFanMode::QUIET:
      return climate::CLIMATE_FAN_QUIET;
    case ClimateFanMode::TURBO:
      return climate::CLIMATE_FAN_FOCUS;
    case ClimateFanMode::AUTO:
    default:
      return climate::CLIMATE_FAN_AUTO;
  }
}

uint8_t esphome_swing_mode_to_wire(climate::ClimateSwingMode sm) {
  switch (sm) {
    case climate::CLIMATE_SWING_VERTICAL:
      return static_cast<uint8_t>(ClimateSwingMode::VERTICAL);
    case climate::CLIMATE_SWING_HORIZONTAL:
      return static_cast<uint8_t>(ClimateSwingMode::HORIZONTAL);
    case climate::CLIMATE_SWING_BOTH:
      return static_cast<uint8_t>(ClimateSwingMode::BOTH);
    case climate::CLIMATE_SWING_OFF:
    default:
      return static_cast<uint8_t>(ClimateSwingMode::OFF);
  }
}

climate::ClimateSwingMode wire_swing_mode_to_esphome(uint8_t m) {
  switch (static_cast<ClimateSwingMode>(m)) {
    case ClimateSwingMode::VERTICAL:
      return climate::CLIMATE_SWING_VERTICAL;
    case ClimateSwingMode::HORIZONTAL:
      return climate::CLIMATE_SWING_HORIZONTAL;
    case ClimateSwingMode::BOTH:
      return climate::CLIMATE_SWING_BOTH;
    case ClimateSwingMode::OFF:
    default:
      return climate::CLIMATE_SWING_OFF;
  }
}

}  // namespace

bool EspNowFanBridge::hub_handle_climate_cmd(const ClimateCmdPayload &cmd, uint32_t origin_id,
                                             uint16_t seq, uint32_t now_ms) {
  LocalClimateEntry *target = nullptr;
  for (auto &lc : local_climates_) {
    if (lc.climate_key_hash == cmd.climate_key_hash && lc.clim != nullptr) {
      target = &lc;
      break;
    }
  }
  if (target == nullptr) {
    return false;  // Not managed by this hub — let multi-hop relay forward it
  }

  AckPayload ack;
  ack.ack_seq = seq;
  ack.status = AckStatus::OK;

  if (origin_id != 0 &&
      !cmd_exec_dedup_.accept(origin_id, MsgType::CLIMATE_CMD, seq, 0, now_ms,
                              RELAY_DEDUP_TTL_MS)) {
    ESP_LOGD(TAG, "[%s] Duplicate CLIMATE_CMD seq=%u from origin=0x%08X (re-ACKing only)",
             target->name.c_str(), seq, static_cast<unsigned>(origin_id));
    broadcast_frame(MsgType::ACK, seq, encode_ack(ack));
    return true;
  }

  ESP_LOGI(TAG, "[%s] RX ESP-NOW CLIMATE_CMD seq=%u mask=0x%02X mode=%u temp=%.1f fan=%u swing=%u",
           target->name.c_str(), seq, static_cast<unsigned>(cmd.field_mask),
           static_cast<unsigned>(cmd.hvac_mode), cmd.target_temp_x2 * 0.5f,
           static_cast<unsigned>(cmd.fan_mode), static_cast<unsigned>(cmd.swing_mode));

  auto call = target->clim->make_call();
  if ((cmd.field_mask & CLIMATE_FIELD_HVAC_MODE) != 0) {
    call.set_mode(wire_mode_to_esphome(cmd.hvac_mode));
  }
  if ((cmd.field_mask & CLIMATE_FIELD_TARGET_TEMP) != 0) {
    call.set_target_temperature(static_cast<float>(cmd.target_temp_x2) * 0.5f);
  }
  if ((cmd.field_mask & CLIMATE_FIELD_FAN_MODE) != 0) {
    call.set_fan_mode(wire_fan_mode_to_esphome(cmd.fan_mode));
  }
  if ((cmd.field_mask & CLIMATE_FIELD_SWING_MODE) != 0) {
    call.set_swing_mode(wire_swing_mode_to_esphome(cmd.swing_mode));
  }
  call.perform();

  broadcast_frame(MsgType::ACK, seq, encode_ack(ack));
  // Note: call.perform() triggers publish_state() -> add_on_state_callback -> hub_broadcast_climate_state
  return true;
}

void EspNowFanBridge::hub_broadcast_climate_state(const LocalClimateEntry &entry) {
  if (!espnow_ready_ || entry.clim == nullptr) return;
  ClimateStatePayload st;
  st.climate_key_hash = entry.climate_key_hash;
  st.hvac_mode = esphome_mode_to_wire(entry.clim->mode);
  if (!std::isnan(entry.clim->target_temperature)) {
    int t2 = clamp_int(static_cast<int>(entry.clim->target_temperature * 2.0f + 0.5f), 20, 80);
    st.target_temp_x2 = static_cast<uint8_t>(t2);
  } else {
    st.target_temp_x2 = 48;  // 24.0C fallback
  }
  st.fan_mode = esphome_fan_mode_to_wire(entry.clim->fan_mode);
  st.swing_mode = esphome_swing_mode_to_wire(entry.clim->swing_mode);
  if (!std::isnan(entry.clim->current_temperature)) {
    int c10 = clamp_int(static_cast<int>(entry.clim->current_temperature * 10.0f +
                                         (entry.clim->current_temperature >= 0.0f ? 0.5f : -0.5f)),
                        -500, 1000);
    st.current_temp_x10 = static_cast<int16_t>(c10);
  } else {
    st.current_temp_x10 = CLIMATE_TEMP_INVALID;
  }
  broadcast_frame(MsgType::CLIMATE_STATE, next_seq_++, encode_climate_state(st));
}

void EspNowFanBridge::hub_broadcast_all_climate_states() {
  for (const auto &lc : local_climates_) {
    hub_broadcast_climate_state(lc);
  }
}

#endif  // USE_ESPNOW_CLIMATE


}  // namespace espnow_fan_bridge
}  // namespace esphome

#endif  // USE_ESP32
