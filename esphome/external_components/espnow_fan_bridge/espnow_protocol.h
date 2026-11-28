#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace esphome {
namespace espnow_fan_bridge {

static constexpr uint8_t PROTOCOL_MAGIC_0 = 0x43;  // 'C'
static constexpr uint8_t PROTOCOL_MAGIC_1 = 0x46;  // 'F'
static constexpr uint8_t PROTOCOL_VERSION = 2;
static constexpr size_t FRAME_HEADER_SIZE = 18;
static constexpr size_t MAX_FRAME_SIZE = 128;
static constexpr uint8_t DEFAULT_RELAY_TTL = 5;

enum class MsgType : uint8_t {
  PING = 1,
  PONG = 2,
  CMD = 3,
  ACK = 4,
  STATE = 5,
  SYNC_REQ = 6,
  SHELLY_CMD = 0x10,
  SHELLY_STATE = 0x11,
  CLIMATE_CMD = 0x20,
  CLIMATE_STATE = 0x21,
};

enum class BridgeRole : uint8_t {
  HUB = 1,
  CYD = 2,
};

enum class CmdOpcode : uint8_t {
  FAN_POWER = 1,
  FAN_SPEED = 2,
  FAN_PERCENT = 3,
  FAN_DIRECTION = 4,
  FAN_PRESET = 5,
  FAN_TIMER = 6,
  LIGHT_POWER = 10,
  LIGHT_BRIGHTNESS = 11,
  LIGHT_COLOR_TEMP = 12,
  LIGHT_STATE = 13,
  LIGHT_TOGGLE = 14,
};

enum class ShellyOpcode : uint8_t {
  SW_OFF = 1,
  SW_ON = 2,
  SW_TOGGLE = 3,
  COV_OPEN = 4,
  COV_CLOSE = 5,
  COV_STOP = 6,
  COV_POS = 7,
  QUERY_STATE = 8,
};

enum class ShellyKind : uint8_t {
  SWITCH = 1,
  COVER = 2,
  INPUT_TOGGLE = 3,
};

static constexpr uint8_t SHELLY_FLAG_ON_OR_OPEN = 0x01;
static constexpr uint8_t SHELLY_FLAG_MOTION_MASK = 0x06;  // bits 1..2: 0=stopped, 1=opening, 2=closing
static constexpr uint8_t SHELLY_FLAG_MOTION_SHIFT = 1;
static constexpr uint8_t SHELLY_FLAG_WIFI_DOWN = 0x80;

enum class AckStatus : uint8_t {
  OK = 0,
  UNKNOWN_FAN = 1,
  INVALID_CMD = 2,
};

struct FrameHeader {
  MsgType type{MsgType::PING};
  uint16_t seq{0};
  uint32_t net_tag{0};
  uint16_t payload_len{0};
  uint32_t origin_id{0};
  uint8_t ttl{0};
  uint8_t hop_nonce{0};
};

struct PingPayload {
  BridgeRole role{BridgeRole::HUB};
  uint8_t channel{1};
  uint8_t fan_count{0};
};

struct CmdPayload {
  uint32_t fan_key_hash{0};
  CmdOpcode opcode{CmdOpcode::FAN_POWER};
  int16_t arg0{0};
  int16_t arg1{0};
  int16_t arg2{0};
};

struct AckPayload {
  uint16_t ack_seq{0};
  AckStatus status{AckStatus::OK};
};

struct StatePayload {
  uint32_t fan_key_hash{0};
  uint8_t ble_conn_status{0};  // 0=DISCONNECTED..4=CONNECTED
  int8_t ble_rssi{-127};
  uint8_t fan_on{0};
  uint8_t fan_speed{1};        // 1..6
  uint8_t fan_reverse{0};
  uint8_t fan_preset{0};       // 0=fresh, 1=nature
  uint16_t fan_timer{0};       // 0..540
  uint8_t light_on{0};
  uint16_t light_brightness{1000};  // 10..1000
  uint16_t light_color_temp{500};   // 0..1000
};

struct SyncReqPayload {
  BridgeRole role{BridgeRole::CYD};
  uint8_t channel{1};
};

struct ShellyCmdPayload {
  uint32_t device_id{0};
  uint8_t channel{0};
  ShellyOpcode opcode{ShellyOpcode::SW_TOGGLE};
  uint8_t arg{0};    // 0..100 for COV_POS; 0 otherwise
  uint8_t flags{0};  // Reserved (0)
};

struct ShellyStatePayload {
  uint32_t device_id{0};
  uint8_t channel{0};
  ShellyKind kind{ShellyKind::SWITCH};
  uint8_t state_flags{0};  // bit0=on/open, bits1-2=motion, bit7=wifi_down
  uint8_t position{255};   // 0..100 for cover; 255 otherwise
  int8_t ble_rssi{-127};
};

// Climate field bitmask & compact wire enums (Issue #74)
static constexpr uint8_t CLIMATE_FIELD_HVAC_MODE = 0x01;
static constexpr uint8_t CLIMATE_FIELD_TARGET_TEMP = 0x02;
static constexpr uint8_t CLIMATE_FIELD_FAN_MODE = 0x04;
static constexpr uint8_t CLIMATE_FIELD_SWING_MODE = 0x08;
static constexpr int16_t CLIMATE_TEMP_INVALID = -32768;  // INT16_MIN

enum class ClimateHvacMode : uint8_t {
  OFF = 0,
  COOL = 1,
  HEAT = 2,
  DRY = 3,
  FAN_ONLY = 4,
  AUTO = 5,
};

enum class ClimateFanMode : uint8_t {
  AUTO = 0,
  LOW = 1,
  MEDIUM = 2,
  HIGH = 3,
  QUIET = 4,
  TURBO = 5,
};

enum class ClimateSwingMode : uint8_t {
  OFF = 0,
  VERTICAL = 1,
  HORIZONTAL = 2,
  BOTH = 3,
};

struct ClimateCmdPayload {
  uint32_t climate_key_hash{0};
  uint8_t field_mask{0};
  uint8_t hvac_mode{0};
  uint8_t target_temp_x2{48};  // 0.5C steps (e.g., 24.0C = 48)
  uint8_t fan_mode{0};
  uint8_t swing_mode{0};
};

struct ClimateStatePayload {
  uint32_t climate_key_hash{0};
  uint8_t hvac_mode{0};
  uint8_t target_temp_x2{48};
  uint8_t fan_mode{0};
  uint8_t swing_mode{0};
  int16_t current_temp_x10{CLIMATE_TEMP_INVALID};
};

// Deterministic 32-bit FNV-1a hash used for fan entity keys, Shelly device IDs, and auth tags
uint32_t fnv1a_32(const uint8_t *data, size_t len, uint32_t seed = 2166136261u);
uint32_t fnv1a_32(const std::string &s, uint32_t seed = 2166136261u);

// Normalize MAC string to lowercase hex without colons/dashes and compute Shelly device_id
std::string normalize_mac_hex(const std::string &mac);
uint32_t shelly_device_id_from_mac(const std::string &mac);

// Compute keyed authentication tag over (network_key, type, seq, origin_id, ttl, hop_nonce, payload)
uint32_t compute_net_tag(const std::string &network_key, MsgType type, uint16_t seq,
                         uint32_t origin_id, uint8_t ttl, uint8_t hop_nonce,
                         const uint8_t *payload, size_t payload_len);

// Encode/decode full ESP-NOW frames
std::vector<uint8_t> encode_frame(const std::string &network_key, MsgType type, uint16_t seq,
                                  const uint8_t *payload, size_t payload_len,
                                  uint32_t origin_id = 0, uint8_t ttl = DEFAULT_RELAY_TTL,
                                  uint8_t hop_nonce = 0);
bool decode_frame(const std::string &network_key, const uint8_t *data, size_t len,
                  FrameHeader &out_header, std::vector<uint8_t> &out_payload);

// Bounded TTL-expiring dedup ring for multi-hop relay & command execution deduplication
class FrameDedupRing {
 public:
  static constexpr size_t CAPACITY = 64;

  // Returns true if (origin_id, type, seq, hop_nonce) was NOT seen within ttl_ms and records it.
  bool accept(uint32_t origin_id, MsgType type, uint16_t seq, uint8_t hop_nonce, uint32_t now_ms,
              uint32_t ttl_ms);
  void clear();

 private:
  struct Entry {
    uint32_t origin_id{0};
    uint16_t seq{0};
    uint8_t type{0};
    uint8_t hop_nonce{0};
    uint32_t seen_ms{0};
    bool valid{false};
  };
  std::array<Entry, CAPACITY> entries_{};
  size_t write_idx_{0};
};

// Payload encoders / decoders
std::vector<uint8_t> encode_ping(const PingPayload &p);
bool decode_ping(const uint8_t *data, size_t len, PingPayload &out);

std::vector<uint8_t> encode_cmd(const CmdPayload &p);
bool decode_cmd(const uint8_t *data, size_t len, CmdPayload &out);

std::vector<uint8_t> encode_ack(const AckPayload &p);
bool decode_ack(const uint8_t *data, size_t len, AckPayload &out);

std::vector<uint8_t> encode_state(const StatePayload &p);
bool decode_state(const uint8_t *data, size_t len, StatePayload &out);

std::vector<uint8_t> encode_sync_req(const SyncReqPayload &p);
bool decode_sync_req(const uint8_t *data, size_t len, SyncReqPayload &out);

std::vector<uint8_t> encode_shelly_cmd(const ShellyCmdPayload &p);
bool decode_shelly_cmd(const uint8_t *data, size_t len, ShellyCmdPayload &out);

std::vector<uint8_t> encode_shelly_state(const ShellyStatePayload &p);
bool decode_shelly_state(const uint8_t *data, size_t len, ShellyStatePayload &out);

std::vector<uint8_t> encode_climate_cmd(const ClimateCmdPayload &p);
bool decode_climate_cmd(const uint8_t *data, size_t len, ClimateCmdPayload &out);

std::vector<uint8_t> encode_climate_state(const ClimateStatePayload &p);
bool decode_climate_state(const uint8_t *data, size_t len, ClimateStatePayload &out);

// Pure state machine for offline channel hunting, 2-miss pruning, and multi-channel round-robin
class ChannelHuntState {
 public:
  static constexpr uint8_t MIN_CHANNEL = 1;
  static constexpr uint8_t MAX_CHANNEL = 13;
  static constexpr uint8_t MAX_MISSED_SWEEPS = 2;

  explicit ChannelHuntState(uint8_t fallback_channel = 1)
      : fallback_channel_(clamp_channel(fallback_channel)) {}

  void set_fallback_channel(uint8_t ch) { fallback_channel_ = clamp_channel(ch); }
  uint8_t fallback_channel() const { return fallback_channel_; }

  // Begin a 1..13 channel discovery sweep
  void start_sweep(uint32_t now_ms);
  bool is_sweeping() const { return sweeping_; }

  // Advance sweep timer; returns the channel to tune to (or 0 if no change needed).
  // Sets `should_ping` to true whenever a fresh channel step is entered.
  uint8_t tick_sweep(uint32_t now_ms, uint32_t dwell_ms, bool &should_ping);

  // Record that a valid peer responded on `channel` during the current sweep or normal RX
  void record_peer_channel(uint8_t channel);

  // Current resting/round-robin channel when offline and not sweeping
  uint8_t active_channel(uint32_t now_ms, uint32_t round_robin_dwell_ms);

  std::vector<uint8_t> active_channels() const;
  void clear_active_channels();

 private:
  struct TrackedChannel {
    uint8_t channel{1};
    uint8_t missed_sweeps{0};
    bool seen_in_current_sweep{false};
  };

  static uint8_t clamp_channel(uint8_t ch) {
    if (ch < MIN_CHANNEL) return MIN_CHANNEL;
    if (ch > MAX_CHANNEL) return MAX_CHANNEL;
    return ch;
  }

  void finish_sweep();

  uint8_t fallback_channel_{1};
  bool sweeping_{false};
  uint8_t sweep_channel_{0};
  uint32_t sweep_step_started_ms_{0};

  std::vector<TrackedChannel> tracked_;
  size_t rr_index_{0};
  uint32_t rr_last_switch_ms_{0};
};

}  // namespace espnow_fan_bridge
}  // namespace esphome
