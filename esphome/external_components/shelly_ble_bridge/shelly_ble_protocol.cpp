#include "shelly_ble_protocol.h"

namespace esphome {
namespace shelly_ble_bridge {

namespace {

inline void write_u16_le(uint8_t *dst, uint16_t v) {
  dst[0] = static_cast<uint8_t>(v & 0xFF);
  dst[1] = static_cast<uint8_t>((v >> 8) & 0xFF);
}

inline void write_u32_le(uint8_t *dst, uint32_t v) {
  dst[0] = static_cast<uint8_t>(v & 0xFF);
  dst[1] = static_cast<uint8_t>((v >> 8) & 0xFF);
  dst[2] = static_cast<uint8_t>((v >> 16) & 0xFF);
  dst[3] = static_cast<uint8_t>((v >> 24) & 0xFF);
}

inline uint16_t read_u16_le(const uint8_t *src) {
  return static_cast<uint16_t>(src[0]) | (static_cast<uint16_t>(src[1]) << 8);
}

inline uint32_t read_u32_le(const uint8_t *src) {
  return static_cast<uint32_t>(src[0]) | (static_cast<uint32_t>(src[1]) << 8) |
         (static_cast<uint32_t>(src[2]) << 16) | (static_cast<uint32_t>(src[3]) << 24);
}

}  // namespace

uint32_t fnv1a_32(const uint8_t *data, size_t len, uint32_t seed) {
  uint32_t h = seed;
  for (size_t i = 0; i < len; ++i) {
    h ^= static_cast<uint32_t>(data[i]);
    h *= 16777619u;
  }
  return h;
}

uint32_t fnv1a_32(const std::string &s, uint32_t seed) {
  return fnv1a_32(reinterpret_cast<const uint8_t *>(s.data()), s.size(), seed);
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

uint32_t compute_shelly_auth_tag(const std::string &network_key, const uint8_t payload10[10]) {
  uint32_t h = fnv1a_32(network_key);
  return fnv1a_32(payload10, 10, h);
}

std::array<uint8_t, SHELLY_BLE_PAYLOAD_SIZE> encode_ble_cmd(const std::string &network_key,
                                                            const ShellyBleCmd &cmd) {
  std::array<uint8_t, SHELLY_BLE_PAYLOAD_SIZE> out{};
  write_u32_le(&out[0], cmd.target_id);
  out[4] = cmd.channel;
  out[5] = static_cast<uint8_t>(cmd.opcode);
  out[6] = cmd.arg;
  out[7] = cmd.flags;
  write_u16_le(&out[8], cmd.seq);
  uint32_t tag = compute_shelly_auth_tag(network_key, out.data());
  write_u32_le(&out[10], tag);
  return out;
}

bool decode_ble_cmd(const std::string &network_key, const uint8_t *data, size_t len,
                    ShellyBleCmd &out) {
  if (data == nullptr || len != SHELLY_BLE_PAYLOAD_SIZE) return false;
  uint32_t expected_tag = compute_shelly_auth_tag(network_key, data);
  uint32_t actual_tag = read_u32_le(data + 10);
  if (expected_tag != actual_tag) return false;

  out.target_id = read_u32_le(data);
  out.channel = data[4];
  out.opcode = static_cast<ShellyBleOpcode>(data[5]);
  out.arg = data[6];
  out.flags = data[7];
  out.seq = read_u16_le(data + 8);
  return true;
}

std::array<uint8_t, SHELLY_BLE_PAYLOAD_SIZE> encode_ble_beacon(const std::string &network_key,
                                                               const ShellyBleBeacon &beacon) {
  std::array<uint8_t, SHELLY_BLE_PAYLOAD_SIZE> out{};
  write_u32_le(&out[0], beacon.source_id);
  out[4] = beacon.channel;
  out[5] = static_cast<uint8_t>(beacon.kind);
  out[6] = beacon.state_flags;
  out[7] = beacon.position;
  write_u16_le(&out[8], beacon.seq);
  uint32_t tag = compute_shelly_auth_tag(network_key, out.data());
  write_u32_le(&out[10], tag);
  return out;
}

bool decode_ble_beacon(const std::string &network_key, const uint8_t *data, size_t len,
                       ShellyBleBeacon &out) {
  if (data == nullptr || len != SHELLY_BLE_PAYLOAD_SIZE) return false;
  uint32_t expected_tag = compute_shelly_auth_tag(network_key, data);
  uint32_t actual_tag = read_u32_le(data + 10);
  if (expected_tag != actual_tag) return false;

  out.source_id = read_u32_le(data);
  out.channel = data[4];
  out.kind = static_cast<ShellyBleKind>(data[5]);
  out.state_flags = data[6];
  out.position = data[7];
  out.seq = read_u16_le(data + 8);
  return true;
}

std::array<uint8_t, SHELLY_BLE_ADV_RAW_SIZE> build_service_data_adv_raw(
    uint16_t uuid16, const std::array<uint8_t, SHELLY_BLE_PAYLOAD_SIZE> &payload) {
  std::array<uint8_t, SHELLY_BLE_ADV_RAW_SIZE> raw{};
  // AD Structure 1: Flags (LE General Discoverable, BR/EDR Not Supported)
  raw[0] = 0x02;
  raw[1] = 0x01;
  raw[2] = 0x06;
  // AD Structure 2: Service Data - 16-bit UUID (AD Type 0x16)
  raw[3] = static_cast<uint8_t>(1 + 2 + SHELLY_BLE_PAYLOAD_SIZE);  // 17 (0x11)
  raw[4] = 0x16;
  raw[5] = static_cast<uint8_t>(uuid16 & 0xFF);
  raw[6] = static_cast<uint8_t>((uuid16 >> 8) & 0xFF);
  for (size_t i = 0; i < SHELLY_BLE_PAYLOAD_SIZE; ++i) {
    raw[7 + i] = payload[i];
  }
  return raw;
}

bool SeqDedupRing::accept(uint32_t device_id, uint16_t seq, uint32_t now_ms, uint32_t ttl_ms) {
  for (auto &e : entries_) {
    if (!e.valid) continue;
    if (ttl_ms > 0 && static_cast<uint32_t>(now_ms - e.seen_ms) >= ttl_ms) {
      e.valid = false;
      continue;
    }
    if (e.device_id == device_id && e.seq == seq) {
      return false;
    }
  }
  entries_[write_idx_] = Entry{device_id, seq, now_ms, true};
  write_idx_ = (write_idx_ + 1) % CAPACITY;
  return true;
}

void SeqDedupRing::clear() {
  for (auto &e : entries_) {
    e.valid = false;
  }
  write_idx_ = 0;
}

void ShellyTxQueue::enqueue(const ShellyBleCmd &cmd) {
  for (auto &existing : queue_) {
    if (existing.target_id == cmd.target_id && existing.channel == cmd.channel) {
      existing = cmd;
      return;
    }
  }
  if (queue_.size() >= MAX_ENTRIES) {
    queue_.pop_front();
  }
  queue_.push_back(cmd);
}

bool ShellyTxQueue::pop(ShellyBleCmd &out) {
  if (queue_.empty()) return false;
  out = queue_.front();
  queue_.pop_front();
  return true;
}

}  // namespace shelly_ble_bridge
}  // namespace esphome
