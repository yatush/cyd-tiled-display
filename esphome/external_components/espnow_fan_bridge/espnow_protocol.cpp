#include "espnow_protocol.h"

#include <algorithm>

namespace esphome {
namespace espnow_fan_bridge {

namespace {

inline void push_u16(std::vector<uint8_t> &buf, uint16_t v) {
  buf.push_back(static_cast<uint8_t>(v & 0xFF));
  buf.push_back(static_cast<uint8_t>((v >> 8) & 0xFF));
}

inline void push_i16(std::vector<uint8_t> &buf, int16_t v) {
  push_u16(buf, static_cast<uint16_t>(v));
}

inline void push_u32(std::vector<uint8_t> &buf, uint32_t v) {
  buf.push_back(static_cast<uint8_t>(v & 0xFF));
  buf.push_back(static_cast<uint8_t>((v >> 8) & 0xFF));
  buf.push_back(static_cast<uint8_t>((v >> 16) & 0xFF));
  buf.push_back(static_cast<uint8_t>((v >> 24) & 0xFF));
}

inline uint16_t read_u16(const uint8_t *p) {
  return static_cast<uint16_t>(p[0]) | (static_cast<uint16_t>(p[1]) << 8);
}

inline int16_t read_i16(const uint8_t *p) { return static_cast<int16_t>(read_u16(p)); }

inline uint32_t read_u32(const uint8_t *p) {
  return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
         (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
}

}  // namespace

uint32_t fnv1a_32(const uint8_t *data, size_t len, uint32_t seed) {
  uint32_t hash = seed;
  for (size_t i = 0; i < len; ++i) {
    hash ^= static_cast<uint32_t>(data[i]);
    hash *= 16777619u;
  }
  return hash;
}

uint32_t fnv1a_32(const std::string &s, uint32_t seed) {
  return fnv1a_32(reinterpret_cast<const uint8_t *>(s.data()), s.size(), seed);
}

uint32_t compute_net_tag(const std::string &network_key, MsgType type, uint16_t seq,
                         const uint8_t *payload, size_t payload_len) {
  uint32_t h = fnv1a_32(network_key);
  uint8_t meta[4] = {
      PROTOCOL_VERSION,
      static_cast<uint8_t>(type),
      static_cast<uint8_t>(seq & 0xFF),
      static_cast<uint8_t>((seq >> 8) & 0xFF),
  };
  h = fnv1a_32(meta, sizeof(meta), h);
  if (payload != nullptr && payload_len > 0) {
    h = fnv1a_32(payload, payload_len, h);
  }
  // Mix key again at end to reduce length-extension collisions
  h = fnv1a_32(network_key, h);
  return h;
}

std::vector<uint8_t> encode_frame(const std::string &network_key, MsgType type, uint16_t seq,
                                  const uint8_t *payload, size_t payload_len) {
  std::vector<uint8_t> out;
  if (payload_len > MAX_FRAME_SIZE - FRAME_HEADER_SIZE) {
    return out;
  }
  out.reserve(FRAME_HEADER_SIZE + payload_len);
  out.push_back(PROTOCOL_MAGIC_0);
  out.push_back(PROTOCOL_MAGIC_1);
  out.push_back(PROTOCOL_VERSION);
  out.push_back(static_cast<uint8_t>(type));
  push_u16(out, seq);
  uint32_t tag = compute_net_tag(network_key, type, seq, payload, payload_len);
  push_u32(out, tag);
  push_u16(out, static_cast<uint16_t>(payload_len));
  if (payload != nullptr && payload_len > 0) {
    out.insert(out.end(), payload, payload + payload_len);
  }
  return out;
}

bool decode_frame(const std::string &network_key, const uint8_t *data, size_t len,
                  FrameHeader &out_header, std::vector<uint8_t> &out_payload) {
  if (data == nullptr || len < FRAME_HEADER_SIZE) return false;
  if (data[0] != PROTOCOL_MAGIC_0 || data[1] != PROTOCOL_MAGIC_1) return false;
  if (data[2] != PROTOCOL_VERSION) return false;

  MsgType type = static_cast<MsgType>(data[3]);
  uint16_t seq = read_u16(data + 4);
  uint32_t tag = read_u32(data + 6);
  uint16_t payload_len = read_u16(data + 10);

  if (len != FRAME_HEADER_SIZE + payload_len) return false;
  const uint8_t *payload_ptr = payload_len > 0 ? (data + FRAME_HEADER_SIZE) : nullptr;
  uint32_t expected_tag = compute_net_tag(network_key, type, seq, payload_ptr, payload_len);
  if (tag != expected_tag) return false;

  out_header.type = type;
  out_header.seq = seq;
  out_header.net_tag = tag;
  out_header.payload_len = payload_len;
  out_payload.assign(data + FRAME_HEADER_SIZE, data + len);
  return true;
}

std::vector<uint8_t> encode_ping(const PingPayload &p) {
  return {static_cast<uint8_t>(p.role), p.channel, p.fan_count};
}

bool decode_ping(const uint8_t *data, size_t len, PingPayload &out) {
  if (data == nullptr || len < 3) return false;
  out.role = static_cast<BridgeRole>(data[0]);
  out.channel = data[1];
  out.fan_count = data[2];
  return true;
}

std::vector<uint8_t> encode_cmd(const CmdPayload &p) {
  std::vector<uint8_t> buf;
  buf.reserve(11);
  push_u32(buf, p.fan_key_hash);
  buf.push_back(static_cast<uint8_t>(p.opcode));
  push_i16(buf, p.arg0);
  push_i16(buf, p.arg1);
  push_i16(buf, p.arg2);
  return buf;
}

bool decode_cmd(const uint8_t *data, size_t len, CmdPayload &out) {
  if (data == nullptr || len < 11) return false;
  out.fan_key_hash = read_u32(data);
  out.opcode = static_cast<CmdOpcode>(data[4]);
  out.arg0 = read_i16(data + 5);
  out.arg1 = read_i16(data + 7);
  out.arg2 = read_i16(data + 9);
  return true;
}

std::vector<uint8_t> encode_ack(const AckPayload &p) {
  std::vector<uint8_t> buf;
  buf.reserve(3);
  push_u16(buf, p.ack_seq);
  buf.push_back(static_cast<uint8_t>(p.status));
  return buf;
}

bool decode_ack(const uint8_t *data, size_t len, AckPayload &out) {
  if (data == nullptr || len < 3) return false;
  out.ack_seq = read_u16(data);
  out.status = static_cast<AckStatus>(data[2]);
  return true;
}

std::vector<uint8_t> encode_state(const StatePayload &p) {
  std::vector<uint8_t> buf;
  buf.reserve(17);
  push_u32(buf, p.fan_key_hash);
  buf.push_back(p.ble_conn_status);
  buf.push_back(static_cast<uint8_t>(p.ble_rssi));
  buf.push_back(p.fan_on);
  buf.push_back(p.fan_speed);
  buf.push_back(p.fan_reverse);
  buf.push_back(p.fan_preset);
  push_u16(buf, p.fan_timer);
  buf.push_back(p.light_on);
  push_u16(buf, p.light_brightness);
  push_u16(buf, p.light_color_temp);
  return buf;
}

bool decode_state(const uint8_t *data, size_t len, StatePayload &out) {
  if (data == nullptr || len < 17) return false;
  out.fan_key_hash = read_u32(data);
  out.ble_conn_status = data[4];
  out.ble_rssi = static_cast<int8_t>(data[5]);
  out.fan_on = data[6];
  out.fan_speed = data[7];
  out.fan_reverse = data[8];
  out.fan_preset = data[9];
  out.fan_timer = read_u16(data + 10);
  out.light_on = data[12];
  out.light_brightness = read_u16(data + 13);
  out.light_color_temp = read_u16(data + 15);
  return true;
}

std::vector<uint8_t> encode_sync_req(const SyncReqPayload &p) {
  return {static_cast<uint8_t>(p.role), p.channel};
}

bool decode_sync_req(const uint8_t *data, size_t len, SyncReqPayload &out) {
  if (data == nullptr || len < 2) return false;
  out.role = static_cast<BridgeRole>(data[0]);
  out.channel = data[1];
  return true;
}

std::string normalize_mac_hex(const std::string &mac) {
  std::string out;
  out.reserve(12);
  for (char c : mac) {
    if (c >= '0' && c <= '9') {
      out.push_back(c);
    } else if (c >= 'a' && c <= 'f') {
      out.push_back(c);
    } else if (c >= 'A' && c <= 'F') {
      out.push_back(static_cast<char>(c - 'A' + 'a'));
    }
  }
  return out;
}

uint32_t shelly_device_id_from_mac(const std::string &mac) {
  return fnv1a_32(normalize_mac_hex(mac));
}

std::vector<uint8_t> encode_shelly_cmd(const ShellyCmdPayload &p) {
  std::vector<uint8_t> buf;
  buf.reserve(8);
  push_u32(buf, p.device_id);
  buf.push_back(p.channel);
  buf.push_back(static_cast<uint8_t>(p.opcode));
  buf.push_back(p.arg);
  buf.push_back(p.flags);
  return buf;
}

bool decode_shelly_cmd(const uint8_t *data, size_t len, ShellyCmdPayload &out) {
  if (data == nullptr || len < 8) return false;
  out.device_id = read_u32(data);
  out.channel = data[4];
  out.opcode = static_cast<ShellyOpcode>(data[5]);
  out.arg = data[6];
  out.flags = data[7];
  return true;
}

std::vector<uint8_t> encode_shelly_state(const ShellyStatePayload &p) {
  std::vector<uint8_t> buf;
  buf.reserve(9);
  push_u32(buf, p.device_id);
  buf.push_back(p.channel);
  buf.push_back(static_cast<uint8_t>(p.kind));
  buf.push_back(p.state_flags);
  buf.push_back(p.position);
  buf.push_back(static_cast<uint8_t>(p.ble_rssi));
  return buf;
}

bool decode_shelly_state(const uint8_t *data, size_t len, ShellyStatePayload &out) {
  if (data == nullptr || len < 9) return false;
  out.device_id = read_u32(data);
  out.channel = data[4];
  out.kind = static_cast<ShellyKind>(data[5]);
  out.state_flags = data[6];
  out.position = data[7];
  out.ble_rssi = static_cast<int8_t>(data[8]);
  return true;
}

// ============================================================================
// ChannelHuntState
// ============================================================================

void ChannelHuntState::start_sweep(uint32_t now_ms) {
  sweeping_ = true;
  sweep_channel_ = 0;  // First tick_sweep() will enter MIN_CHANNEL
  sweep_step_started_ms_ = now_ms;
  for (auto &t : tracked_) {
    t.seen_in_current_sweep = false;
  }
}

uint8_t ChannelHuntState::tick_sweep(uint32_t now_ms, uint32_t dwell_ms, bool &should_ping) {
  should_ping = false;
  if (!sweeping_) return 0;

  if (sweep_channel_ == 0) {
    sweep_channel_ = MIN_CHANNEL;
    sweep_step_started_ms_ = now_ms;
    should_ping = true;
    return sweep_channel_;
  }

  if (now_ms - sweep_step_started_ms_ < dwell_ms) {
    return 0;
  }

  if (sweep_channel_ >= MAX_CHANNEL) {
    finish_sweep();
    return 0;
  }

  sweep_channel_++;
  sweep_step_started_ms_ = now_ms;
  should_ping = true;
  return sweep_channel_;
}

void ChannelHuntState::record_peer_channel(uint8_t channel) {
  uint8_t ch = clamp_channel(channel);
  for (auto &t : tracked_) {
    if (t.channel == ch) {
      t.missed_sweeps = 0;
      t.seen_in_current_sweep = true;
      return;
    }
  }
  TrackedChannel entry;
  entry.channel = ch;
  entry.missed_sweeps = 0;
  entry.seen_in_current_sweep = true;
  tracked_.push_back(entry);
  std::sort(tracked_.begin(), tracked_.end(),
            [](const TrackedChannel &a, const TrackedChannel &b) { return a.channel < b.channel; });
}

void ChannelHuntState::finish_sweep() {
  sweeping_ = false;
  sweep_channel_ = 0;
  for (auto it = tracked_.begin(); it != tracked_.end();) {
    if (it->seen_in_current_sweep) {
      it->missed_sweeps = 0;
      ++it;
    } else {
      it->missed_sweeps++;
      if (it->missed_sweeps >= MAX_MISSED_SWEEPS) {
        it = tracked_.erase(it);
      } else {
        ++it;
      }
    }
  }
  if (rr_index_ >= tracked_.size()) {
    rr_index_ = 0;
  }
}

uint8_t ChannelHuntState::active_channel(uint32_t now_ms, uint32_t round_robin_dwell_ms) {
  if (tracked_.empty()) {
    return fallback_channel_;
  }
  if (tracked_.size() == 1) {
    return tracked_[0].channel;
  }
  if (rr_last_switch_ms_ == 0) {
    rr_last_switch_ms_ = now_ms;
  } else if (now_ms - rr_last_switch_ms_ >= round_robin_dwell_ms) {
    rr_index_ = (rr_index_ + 1) % tracked_.size();
    rr_last_switch_ms_ = now_ms;
  }
  if (rr_index_ >= tracked_.size()) {
    rr_index_ = 0;
  }
  return tracked_[rr_index_].channel;
}

std::vector<uint8_t> ChannelHuntState::active_channels() const {
  std::vector<uint8_t> res;
  res.reserve(tracked_.size());
  for (const auto &t : tracked_) {
    res.push_back(t.channel);
  }
  return res;
}

void ChannelHuntState::clear_active_channels() {
  tracked_.clear();
  rr_index_ = 0;
  rr_last_switch_ms_ = 0;
}

}  // namespace espnow_fan_bridge
}  // namespace esphome
