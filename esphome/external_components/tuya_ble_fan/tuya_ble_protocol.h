#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace esphome {
namespace tuya_ble_fan {

// Tuya BLE GATT UUIDs
constexpr uint16_t TUYA_BLE_SERVICE_UUID = 0x1910;
constexpr uint16_t TUYA_BLE_WRITE_CHAR_UUID = 0x2B11;
constexpr uint16_t TUYA_BLE_NOTIFY_CHAR_UUID = 0x2B10;
constexpr uint16_t TUYA_BLE_ADV_SERVICE_UUID = 0xFD50;
constexpr uint16_t TUYA_BLE_ADV_SERVICE_UUID_V3 = 0xA201;
constexpr uint16_t TUYA_BLE_MANUFACTURER_ID = 0x07D0;

// Tuya BLE function codes
constexpr uint16_t FUN_SENDER_DEVICE_INFO = 0x0000;
constexpr uint16_t FUN_SENDER_PAIR = 0x0001;
constexpr uint16_t FUN_SENDER_DPS = 0x0002;
constexpr uint16_t FUN_SENDER_DEVICE_STATUS = 0x0003;
constexpr uint16_t FUN_SENDER_DPS_V4 = 0x0027;

constexpr uint16_t FUN_RECEIVE_DP = 0x8001;
constexpr uint16_t FUN_RECEIVE_TIME_DP = 0x8003;
constexpr uint16_t FUN_RECEIVE_DP_V4 = 0x8006;
constexpr uint16_t FUN_RECEIVE_TIME_DP_V4 = 0x8007;

// Tuya BLE security flags
constexpr uint8_t SECURITY_FLAG_LOGIN = 0x04;
constexpr uint8_t SECURITY_FLAG_SESSION = 0x05;

// Tuya DP types
enum class TuyaDpType : uint8_t {
  RAW = 0,
  BOOL = 1,
  INT = 2,
  STRING = 3,
  ENUM = 4,
  BITMAP = 5,
};

// FlyFan Data Point IDs (Varin VA-E002 / Sofucor KBS)
constexpr uint8_t DP_LIGHT_POWER = 20;
constexpr uint8_t DP_LIGHT_BRIGHTNESS = 22;   // 10..1000
constexpr uint8_t DP_LIGHT_COLOR_TEMP = 23;   // 0..1000 (2700K..6500K)
constexpr uint8_t DP_FAN_POWER = 60;
constexpr uint8_t DP_FAN_PRESET = 61;         // 0=fresh, 1=nature
constexpr uint8_t DP_FAN_SPEED = 62;          // 1..6
constexpr uint8_t DP_FAN_DIRECTION = 63;      // 0=forward, 1=reverse
constexpr uint8_t DP_FAN_TIMER = 64;          // 0..540 minutes

struct TuyaDp {
  uint8_t id{0};
  TuyaDpType type{TuyaDpType::RAW};
  std::vector<uint8_t> value;

  static TuyaDp make_bool(uint8_t id, bool v);
  static TuyaDp make_int(uint8_t id, int32_t v);
  static TuyaDp make_enum(uint8_t id, uint8_t v);

  bool as_bool() const;
  int32_t as_int() const;
  uint8_t as_enum() const;
};

struct TuyaDecryptedFrame {
  uint32_t seq_num{0};
  uint32_t response_to{0};
  uint16_t code{0};
  std::vector<uint8_t> data;
};

struct TuyaDeviceInfoResponse {
  uint8_t device_version_major{0};
  uint8_t device_version_minor{0};
  uint8_t protocol_version_major{3};
  uint8_t protocol_version_minor{0};
  uint8_t flag{0};
  bool is_bind{false};
  uint8_t srand[6]{0};
};

// Crypto & checksum utilities
uint16_t crc16_modbus(const uint8_t *data, size_t len);
void md5_hash(const uint8_t *data, size_t len, uint8_t out[16]);
bool aes128_cbc_encrypt(const uint8_t key[16], const uint8_t iv[16],
                        const uint8_t *in, size_t in_len,
                        std::vector<uint8_t> &out);
bool aes128_cbc_decrypt(const uint8_t key[16], const uint8_t iv[16],
                        const uint8_t *in, size_t in_len,
                        std::vector<uint8_t> &out);

// Key derivation
void derive_login_key(const std::string &local_key, uint8_t out_key[16]);
void derive_session_key(const std::string &local_key, const uint8_t srand[6], uint8_t out_key[16]);

// Varint helpers (7-bit LEB128 used in Tuya BLE packet framing)
void append_varint(std::vector<uint8_t> &out, uint32_t value);
bool read_varint(const uint8_t *data, size_t len, size_t &pos, uint32_t &out);

// Packet builder & parser
std::vector<uint8_t> build_encrypted_packet(uint32_t seq_num, uint32_t response_to,
                                            uint16_t code, const std::vector<uint8_t> &payload,
                                            uint8_t security_flag, const uint8_t key[16],
                                            const uint8_t iv[16]);

bool parse_encrypted_packet(const uint8_t *raw, size_t raw_len,
                            const uint8_t login_key[16], const uint8_t session_key[16],
                            bool has_session_key, TuyaDecryptedFrame &out);

// Chunking into 20-byte GATT packets (or custom MTU)
std::vector<std::vector<uint8_t>> fragment_gatt_packet(const std::vector<uint8_t> &encrypted_packet,
                                                       uint8_t protocol_version = 3,
                                                       size_t chunk_size = 20);

// Reassembler for incoming GATT notifications
class GattPacketReassembler {
 public:
  void reset();
  // Feed a single GATT notification chunk. Returns true when a full packet is ready in `out`.
  bool feed(const uint8_t *data, size_t len, std::vector<uint8_t> &out, uint8_t &protocol_version);

 private:
  std::vector<uint8_t> buffer_;
  uint32_t expected_len_{0};
  uint32_t expected_packet_{0};
  uint8_t protocol_version_{3};
  bool in_progress_{false};
};

// Payload builders & parsers
std::vector<uint8_t> build_pair_payload(const std::string &uuid, const std::string &local_key,
                                        const std::string &device_id);
bool parse_device_info_response(const std::vector<uint8_t> &data, TuyaDeviceInfoResponse &out);

std::vector<uint8_t> encode_dps_v3(const std::vector<TuyaDp> &dps);
std::vector<uint8_t> encode_dps_v4(uint16_t dp_seq, const std::vector<TuyaDp> &dps);
bool decode_dps_v3(const uint8_t *data, size_t len, std::vector<TuyaDp> &out);
bool decode_dps_v4(const uint8_t *data, size_t len, std::vector<TuyaDp> &out);

// Check if a BLE advertisement's 0xFD50 service data or 0x07D0 manufacturer data
// matches a Tuya fan's product_id / device_id / local_key.
bool match_tuya_advertisement(const uint8_t *service_data, size_t service_data_len,
                              const uint8_t *mfg_data, size_t mfg_data_len,
                              const std::string &product_id,
                              const std::string &device_id,
                              const std::string &local_key);

// Extract the 16-byte ASCII UUID from a bound Tuya BLE v3 advertisement:
// service_data[0xA201] (17 bytes: 0x00 + 16B hash) + mfg_data[0x07D0] (22 bytes: 6B hdr + 16B enc UUID).
bool extract_tuya_v3_uuid(const uint8_t *service_data_a201, size_t service_data_len,
                          const uint8_t *mfg_data_07d0, size_t mfg_data_len,
                          std::string &out_uuid);

struct TuyaBleAdvInfo {
  bool valid{false};
  bool bound{false};
  std::string uuid;
  std::string product_id;
};

// Parse Tuya BLE advertisement fields from 0xA201 / 0xFD50 service data and 0x07D0 manufacturer data.
TuyaBleAdvInfo parse_tuya_ble_advertisement(const uint8_t *svc_a201, size_t svc_a201_len,
                                            const uint8_t *svc_fd50, size_t svc_fd50_len,
                                            const uint8_t *mfg_07d0, size_t mfg_07d0_len);

// Unbound (bound=0) key derivation for cloud-free local pairing
void derive_unbound_login_key(const std::string &uuid, uint8_t out_key[16]);
void derive_unbound_session_key(const std::string &uuid, const uint8_t srand[6], uint8_t out_key[16]);

}  // namespace tuya_ble_fan
}  // namespace esphome
