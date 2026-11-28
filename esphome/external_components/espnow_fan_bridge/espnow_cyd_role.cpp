#include "espnow_fan_bridge_internal.h"

#ifdef USE_ESP32

namespace esphome {
namespace espnow_fan_bridge {

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

RemoteClimateState *EspNowFanBridge::cyd_find_remote_climate(uint32_t climate_key_hash) {
  for (auto &rc : remote_climates_) {
    if (rc.climate_key_hash == climate_key_hash) return &rc;
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

void EspNowFanBridge::cyd_handle_climate_state(const ClimateStatePayload &st, uint32_t now_ms) {
  auto *rc = cyd_find_remote_climate(st.climate_key_hash);
  if (rc == nullptr) return;

  const bool prev_has = rc->has_state;
  const bool prev_reach = rc->espnow_reachable;
  const uint8_t prev_mode = rc->hvac_mode;
  const uint8_t prev_temp = rc->target_temp_x2;
  const uint8_t prev_fan = rc->fan_mode;
  const uint8_t prev_swing = rc->swing_mode;
  const int16_t prev_cur = rc->current_temp_x10;

  rc->has_state = true;
  rc->espnow_reachable = true;
  rc->last_seen_ms = now_ms;
  rc->hvac_mode = st.hvac_mode;
  if (st.hvac_mode != 0) {
    rc->last_active_mode = st.hvac_mode;
  }
  rc->target_temp_x2 = st.target_temp_x2;
  rc->fan_mode = st.fan_mode;
  rc->swing_mode = st.swing_mode;
  rc->current_temp_x10 = st.current_temp_x10;

  if (!prev_reach) {
    ESP_LOGI(TAG, "[%s] Climate ESP-NOW state received (mode=%s temp=%.1f fan=%s swing=%s)",
             rc->name.c_str(), RemoteClimateState::hvac_mode_str(rc->hvac_mode),
             rc->target_temp_x2 * 0.5f, RemoteClimateState::fan_mode_str(rc->fan_mode),
             RemoteClimateState::swing_mode_str(rc->swing_mode));
  }

  const bool changed = !prev_has || !prev_reach || prev_mode != rc->hvac_mode ||
                       prev_temp != rc->target_temp_x2 || prev_fan != rc->fan_mode ||
                       prev_swing != rc->swing_mode || prev_cur != rc->current_temp_x10;
  if (!changed) return;

  if (!rc->entity_id.empty()) {
    EspNowFanRegistry::instance().notify_state_changed(
        rc->entity_id, RemoteClimateState::hvac_mode_str(rc->hvac_mode));
  }
  ui_dirty_ = true;
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
  for (auto it = pending_climate_cmds_.begin(); it != pending_climate_cmds_.end(); ++it) {
    if (it->seq == ack.ack_seq) {
      ESP_LOGD(TAG, "RX ESP-NOW Climate ACK seq=%u status=%u", ack.ack_seq,
               static_cast<unsigned>(ack.status));
      if (auto *rc = cyd_find_remote_climate(it->cmd.climate_key_hash)) {
        if (!rc->espnow_reachable) {
          rc->espnow_reachable = true;
          ui_dirty_ = true;
        }
        rc->last_seen_ms = now_ms;
      }
      pending_climate_cmds_.erase(it);
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

void EspNowFanBridge::cyd_queue_climate_cmd(const ClimateCmdPayload &cmd, uint32_t now_ms) {
  PendingClimateCmd pending;
  pending.seq = next_seq_++;
  pending.cmd = cmd;
  pending.created_ms = now_ms;
  pending.last_tx_ms = now_ms;
  pending.attempts = 1;

  ESP_LOGD(TAG, "TX ESP-NOW CLIMATE_CMD seq=%u key=0x%08X mask=0x%02X mode=%u temp=%.1f",
           pending.seq, static_cast<unsigned>(cmd.climate_key_hash),
           static_cast<unsigned>(cmd.field_mask), static_cast<unsigned>(cmd.hvac_mode),
           cmd.target_temp_x2 * 0.5f);
  broadcast_frame(MsgType::CLIMATE_CMD, pending.seq, encode_climate_cmd(pending.cmd));

  // Coalesce older pending commands for the same climate + field_mask
  for (auto it = pending_climate_cmds_.begin(); it != pending_climate_cmds_.end();) {
    if (it->cmd.climate_key_hash == cmd.climate_key_hash &&
        it->cmd.field_mask == cmd.field_mask) {
      it = pending_climate_cmds_.erase(it);
    } else {
      ++it;
    }
  }
  pending_climate_cmds_.push_back(pending);
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

  for (auto it = pending_climate_cmds_.begin(); it != pending_climate_cmds_.end();) {
    if (static_cast<int32_t>(now_ms - it->last_tx_ms) <
        static_cast<int32_t>(CMD_RETRY_INTERVAL_MS)) {
      ++it;
      continue;
    }
    if (it->attempts >= CMD_MAX_ATTEMPTS) {
      ESP_LOGW(TAG, "ESP-NOW Climate cmd seq=%u timed out after %u attempts", it->seq,
               it->attempts);
      if (auto *rc = cyd_find_remote_climate(it->cmd.climate_key_hash)) {
        if (rc->espnow_reachable) {
          rc->espnow_reachable = false;
          ui_dirty_ = true;
        }
      }
      it = pending_climate_cmds_.erase(it);
      continue;
    }
    it->attempts++;
    it->last_tx_ms = now_ms;
    broadcast_frame(MsgType::CLIMATE_CMD, it->seq, encode_climate_cmd(it->cmd), DEFAULT_RELAY_TTL,
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

namespace {

uint8_t parse_hvac_mode(const std::string &s, bool &valid) {
  valid = true;
  if (s == "off") return static_cast<uint8_t>(ClimateHvacMode::OFF);
  if (s == "cool") return static_cast<uint8_t>(ClimateHvacMode::COOL);
  if (s == "heat") return static_cast<uint8_t>(ClimateHvacMode::HEAT);
  if (s == "dry") return static_cast<uint8_t>(ClimateHvacMode::DRY);
  if (s == "fan_only") return static_cast<uint8_t>(ClimateHvacMode::FAN_ONLY);
  if (s == "auto" || s == "heat_cool") return static_cast<uint8_t>(ClimateHvacMode::AUTO);
  valid = false;
  return 0;
}

uint8_t parse_fan_mode(const std::string &s, bool &valid) {
  valid = true;
  if (s == "auto") return static_cast<uint8_t>(ClimateFanMode::AUTO);
  if (s == "low") return static_cast<uint8_t>(ClimateFanMode::LOW);
  if (s == "medium" || s == "middle") return static_cast<uint8_t>(ClimateFanMode::MEDIUM);
  if (s == "high") return static_cast<uint8_t>(ClimateFanMode::HIGH);
  if (s == "quiet") return static_cast<uint8_t>(ClimateFanMode::QUIET);
  if (s == "turbo" || s == "focus") return static_cast<uint8_t>(ClimateFanMode::TURBO);
  valid = false;
  return 0;
}

uint8_t parse_swing_mode(const std::string &s, bool &valid) {
  valid = true;
  if (s == "off") return static_cast<uint8_t>(ClimateSwingMode::OFF);
  if (s == "vertical") return static_cast<uint8_t>(ClimateSwingMode::VERTICAL);
  if (s == "horizontal") return static_cast<uint8_t>(ClimateSwingMode::HORIZONTAL);
  if (s == "both") return static_cast<uint8_t>(ClimateSwingMode::BOTH);
  valid = false;
  return 0;
}

}  // namespace

bool EspNowFanBridge::send_climate_action(
    RemoteClimateState *cl, const std::string &action,
    const std::vector<std::pair<std::string, std::string>> &data) {
  if (cl == nullptr) return false;
  const uint32_t now = millis();

  // Strip domain prefix if present (e.g. "climate.set_hvac_mode" -> "set_hvac_mode")
  std::string act = action;
  size_t dot = act.find('.');
  if (dot != std::string::npos) act = act.substr(dot + 1);

  ClimateCmdPayload cmd;
  cmd.climate_key_hash = cl->climate_key_hash;
  cmd.field_mask = 0;
  cmd.hvac_mode = cl->hvac_mode;
  cmd.target_temp_x2 = cl->target_temp_x2;
  cmd.fan_mode = cl->fan_mode;
  cmd.swing_mode = cl->swing_mode;

  if (act == "turn_off") {
    cmd.field_mask |= CLIMATE_FIELD_HVAC_MODE;
    cmd.hvac_mode = static_cast<uint8_t>(ClimateHvacMode::OFF);
    cl->hvac_mode = cmd.hvac_mode;
  } else if (act == "turn_on") {
    cmd.field_mask |= CLIMATE_FIELD_HVAC_MODE;
    cmd.hvac_mode = cl->last_active_mode != 0 ? cl->last_active_mode
                                              : static_cast<uint8_t>(ClimateHvacMode::COOL);
    cl->hvac_mode = cmd.hvac_mode;
  } else if (act == "toggle") {
    cmd.field_mask |= CLIMATE_FIELD_HVAC_MODE;
    if (cl->hvac_mode == 0) {
      cmd.hvac_mode = cl->last_active_mode != 0 ? cl->last_active_mode
                                                : static_cast<uint8_t>(ClimateHvacMode::COOL);
    } else {
      cmd.hvac_mode = static_cast<uint8_t>(ClimateHvacMode::OFF);
    }
    cl->hvac_mode = cmd.hvac_mode;
  } else if (act == "set_hvac_mode") {
    const auto *mode_s = find_data_value(data, "hvac_mode");
    if (mode_s == nullptr) return false;
    bool ok = false;
    uint8_t m = parse_hvac_mode(*mode_s, ok);
    if (!ok) return false;
    cmd.field_mask |= CLIMATE_FIELD_HVAC_MODE;
    cmd.hvac_mode = m;
    cl->hvac_mode = m;
    if (m != 0) cl->last_active_mode = m;
  } else if (act == "set_temperature") {
    const auto *temp_s = find_data_value(data, "temperature");
    if (temp_s != nullptr) {
      float temp = static_cast<float>(std::atof(temp_s->c_str()));
      int t2 = clamp_int(static_cast<int>(temp * 2.0f + 0.5f), 20, 80);
      cmd.field_mask |= CLIMATE_FIELD_TARGET_TEMP;
      cmd.target_temp_x2 = static_cast<uint8_t>(t2);
      cl->target_temp_x2 = cmd.target_temp_x2;
    }
    const auto *mode_s = find_data_value(data, "hvac_mode");
    if (mode_s != nullptr) {
      bool ok = false;
      uint8_t m = parse_hvac_mode(*mode_s, ok);
      if (ok) {
        cmd.field_mask |= CLIMATE_FIELD_HVAC_MODE;
        cmd.hvac_mode = m;
        cl->hvac_mode = m;
        if (m != 0) cl->last_active_mode = m;
      }
    }
    if (cmd.field_mask == 0) return false;
  } else if (act == "set_fan_mode") {
    const auto *fan_s = find_data_value(data, "fan_mode");
    if (fan_s == nullptr) return false;
    bool ok = false;
    uint8_t fm = parse_fan_mode(*fan_s, ok);
    if (!ok) return false;
    cmd.field_mask |= CLIMATE_FIELD_FAN_MODE;
    cmd.fan_mode = fm;
    cl->fan_mode = fm;
  } else if (act == "set_swing_mode") {
    const auto *swing_s = find_data_value(data, "swing_mode");
    if (swing_s == nullptr) return false;
    bool ok = false;
    uint8_t sm = parse_swing_mode(*swing_s, ok);
    if (!ok) return false;
    cmd.field_mask |= CLIMATE_FIELD_SWING_MODE;
    cmd.swing_mode = sm;
    cl->swing_mode = sm;
  } else {
    return false;
  }

  cl->has_state = true;
  cyd_queue_climate_cmd(cmd, now);
  if (!cl->entity_id.empty()) {
    EspNowFanRegistry::instance().notify_state_changed(
        cl->entity_id, RemoteClimateState::hvac_mode_str(cl->hvac_mode));
  }
  ui_dirty_ = true;
  return true;
}

}  // namespace espnow_fan_bridge
}  // namespace esphome

#endif  // USE_ESP32
