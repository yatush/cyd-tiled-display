#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <string>
#include <vector>

namespace esphome {
namespace shelly_ble_bridge {

// 16-bit BLE Service Data UUIDs (AD Type 0x16)
static constexpr uint16_t UUID_SHELLY_CMD = 0xC753;    // Hub -> Shelly command (14 B)
static constexpr uint16_t UUID_SHELLY_STATE = 0xC754;  // Shelly -> Hub state beacon (14 B)
static constexpr uint16_t UUID_SHELLY_INPUT = 0xC755;  // Shelly -> Hub detached input event (14 B)

static constexpr size_t SHELLY_BLE_PAYLOAD_SIZE = 14;
static constexpr size_t SHELLY_BLE_ADV_RAW_SIZE = 21;  // 3 B flags + 18 B service data

static constexpr uint8_t SHELLY_FLAG_ON_OR_OPEN = 0x01;
static constexpr uint8_t SHELLY_FLAG_MOTION_MASK = 0x06;  // bits 1..2: 0=stopped, 1=opening, 2=closing
static constexpr uint8_t SHELLY_FLAG_WIFI_DOWN = 0x80;

enum class ShellyBleOpcode : uint8_t {
  SW_OFF = 1,
  SW_ON = 2,
  SW_TOGGLE = 3,
  COV_OPEN = 4,
  COV_CLOSE = 5,
  COV_STOP = 6,
  COV_POS = 7,
  QUERY_STATE = 8,
};

enum class ShellyBleKind : uint8_t {
  SWITCH = 1,
  COVER = 2,
  INPUT_TOGGLE = 3,
};

struct ShellyBleCmd {
  uint32_t target_id{0};
  uint8_t channel{0};
  ShellyBleOpcode opcode{ShellyBleOpcode::SW_TOGGLE};
  uint8_t arg{0};    // 0..100 for COV_POS; 0 otherwise
  uint8_t flags{0};  // Reserved (0)
  uint16_t seq{0};
};

struct ShellyBleBeacon {
  uint32_t source_id{0};
  uint8_t channel{0};
  ShellyBleKind kind{ShellyBleKind::SWITCH};
  uint8_t state_flags{0};
  uint8_t position{255};  // 0..100 for cover; 255 otherwise
  uint16_t seq{0};
};

// Standard 32-bit FNV-1a hash
uint32_t fnv1a_32(const uint8_t *data, size_t len, uint32_t seed = 2166136261u);
uint32_t fnv1a_32(const std::string &s, uint32_t seed = 2166136261u);

// Lowercase hex MAC without separators, and its FNV-1a 32-bit device_id
std::string normalize_mac_hex(const std::string &mac);
uint32_t shelly_device_id_from_mac(const std::string &mac);

// Keyed auth tag: fnv1a_32(network_key + payload[0..9])
uint32_t compute_shelly_auth_tag(const std::string &network_key, const uint8_t payload10[10]);

// Encode/decode 14-byte BLE Service Data payloads
std::array<uint8_t, SHELLY_BLE_PAYLOAD_SIZE> encode_ble_cmd(const std::string &network_key,
                                                            const ShellyBleCmd &cmd);
bool decode_ble_cmd(const std::string &network_key, const uint8_t *data, size_t len,
                    ShellyBleCmd &out);

std::array<uint8_t, SHELLY_BLE_PAYLOAD_SIZE> encode_ble_beacon(const std::string &network_key,
                                                               const ShellyBleBeacon &beacon);
bool decode_ble_beacon(const std::string &network_key, const uint8_t *data, size_t len,
                       ShellyBleBeacon &out);

// Build 21-byte raw legacy BLE ADV packet containing Flags + 16-bit Service Data (AD Type 0x16)
std::array<uint8_t, SHELLY_BLE_ADV_RAW_SIZE> build_service_data_adv_raw(
    uint16_t uuid16, const std::array<uint8_t, SHELLY_BLE_PAYLOAD_SIZE> &payload);

// Fixed-size ring buffer to deduplicate repeated (device_id, seq) BLE advertisements
class SeqDedupRing {
 public:
  static constexpr size_t CAPACITY = 16;

  // Returns true if (device_id, seq) was NOT recently seen (within ttl_ms when ttl_ms > 0)
  // and records it. Returns false if it is a duplicate.
  bool accept(uint32_t device_id, uint16_t seq, uint32_t now_ms = 0, uint32_t ttl_ms = 0);
  void clear();

 private:
  struct Entry {
    uint32_t device_id{0};
    uint16_t seq{0};
    uint32_t seen_ms{0};
    bool valid{false};
  };
  std::array<Entry, CAPACITY> entries_{};
  size_t write_idx_{0};
};

// Bounded FIFO BLE command TX queue that coalesces duplicate (target_id, channel) entries
class ShellyTxQueue {
 public:
  static constexpr size_t MAX_ENTRIES = 16;

  // Enqueue command; if an entry for the same (target_id, channel) is already queued,
  // update it in place so rapid slider/multi-blind bursts stay fresh.
  void enqueue(const ShellyBleCmd &cmd);
  bool empty() const { return queue_.empty(); }
  size_t size() const { return queue_.size(); }
  bool pop(ShellyBleCmd &out);
  void clear() { queue_.clear(); }

 private:
  std::deque<ShellyBleCmd> queue_;
};

}  // namespace shelly_ble_bridge
}  // namespace esphome
