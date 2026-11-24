#include <cassert>
#include <cstring>
#include <iostream>
#include <vector>

#include "tuya_ble_protocol.h"

using namespace esphome::tuya_ble_fan;

static void test_crc16() {
  const uint8_t msg[] = {'1', '2', '3', '4', '5', '6', '7', '8', '9'};
  assert(crc16_modbus(msg, sizeof(msg)) == 0x4B37);
}

static void test_packet_encrypt_decrypt_and_chunking() {
  const std::string local_key = "0123456789abcdef";
  const uint8_t srand_bytes[6] = {0x11, 0x22, 0x33, 0x44, 0x55, 0x66};

  uint8_t login_key[16];
  uint8_t session_key[16];
  derive_login_key(local_key, login_key);
  derive_session_key(local_key, srand_bytes, session_key);

  const uint8_t iv[16] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16};
  auto dps = encode_dps_v4(7, {
      TuyaDp::make_bool(DP_FAN_POWER, true),
      TuyaDp::make_int(DP_FAN_SPEED, 4),
      TuyaDp::make_enum(DP_FAN_DIRECTION, 1),
      TuyaDp::make_bool(DP_LIGHT_POWER, true),
      TuyaDp::make_int(DP_LIGHT_BRIGHTNESS, 750),
      TuyaDp::make_int(DP_LIGHT_COLOR_TEMP, 500),
      TuyaDp::make_int(DP_FAN_TIMER, 120),
  });

  auto enc = build_encrypted_packet(42, 0, FUN_SENDER_DPS_V4, dps, SECURITY_FLAG_SESSION, session_key, iv);
  assert(!enc.empty());

  auto chunks = fragment_gatt_packet(enc, 4, 20);
  assert(chunks.size() >= 3);
  for (const auto &c : chunks) {
    assert(c.size() <= 20);
  }

  GattPacketReassembler reassembler;
  std::vector<uint8_t> reassembled;
  uint8_t proto_ver = 0;
  bool done = false;
  for (size_t i = 0; i < chunks.size(); i++) {
    bool ready = reassembler.feed(chunks[i].data(), chunks[i].size(), reassembled, proto_ver);
    if (i + 1 < chunks.size()) {
      assert(!ready);
    } else {
      assert(ready);
      done = true;
    }
  }
  assert(done);
  assert(proto_ver == 4);
  assert(reassembled == enc);

  TuyaDecryptedFrame frame;
  assert(parse_encrypted_packet(reassembled.data(), reassembled.size(), login_key, session_key, true, frame));
  assert(frame.seq_num == 42);
  assert(frame.code == FUN_SENDER_DPS_V4);
  assert(frame.data == dps);

  // Decode v4 DPs (skip 3-byte dp_seq + flag header)
  std::vector<TuyaDp> decoded;
  assert(decode_dps_v4(frame.data.data() + 3, frame.data.size() - 3, decoded));
  assert(decoded.size() == 7);
  assert(decoded[0].id == DP_FAN_POWER && decoded[0].as_bool() == true);
  assert(decoded[1].id == DP_FAN_SPEED && decoded[1].as_int() == 4);
  assert(decoded[2].id == DP_FAN_DIRECTION && decoded[2].as_enum() == 1);
  assert(decoded[3].id == DP_LIGHT_POWER && decoded[3].as_bool() == true);
  assert(decoded[4].id == DP_LIGHT_BRIGHTNESS && decoded[4].as_int() == 750);
  assert(decoded[5].id == DP_LIGHT_COLOR_TEMP && decoded[5].as_int() == 500);
  assert(decoded[6].id == DP_FAN_TIMER && decoded[6].as_int() == 120);

  // Corrupt ciphertext must fail CRC verification
  reassembled.back() ^= 0xFF;
  assert(!parse_encrypted_packet(reassembled.data(), reassembled.size(), login_key, session_key, true, frame));
}

static void test_v3_dps_and_pair_and_device_info() {
  auto v3 = encode_dps_v3({
      TuyaDp::make_bool(DP_FAN_POWER, false),
      TuyaDp::make_enum(DP_FAN_PRESET, 1),
  });
  std::vector<TuyaDp> decoded;
  assert(decode_dps_v3(v3.data(), v3.size(), decoded));
  assert(decoded.size() == 2);
  assert(decoded[0].id == DP_FAN_POWER && decoded[0].as_bool() == false);
  assert(decoded[1].id == DP_FAN_PRESET && decoded[1].as_enum() == 1);

  auto pair_payload = build_pair_payload("", "abcdef1234567890", "bf1234567890abcdef1234");
  assert(pair_payload.size() == 44);
  assert(std::memcmp(pair_payload.data(), "bf1234567890abcd", 16) == 0);
  assert(std::memcmp(pair_payload.data() + 16, "abcdef", 6) == 0);
  assert(std::memcmp(pair_payload.data() + 22, "bf1234567890abcdef1234", 22) == 0);

  std::vector<uint8_t> dev_info = {1, 2, 4, 1, 0, 1, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF};
  TuyaDeviceInfoResponse parsed;
  assert(parse_device_info_response(dev_info, parsed));
  assert(parsed.protocol_version_major == 4);
  assert(parsed.is_bind == true);
  assert(parsed.srand[0] == 0xAA && parsed.srand[5] == 0xFF);
}

static void test_advertisement_matching() {
  const std::string pid = "vfqiwthdnlkynebk";
  const std::string dev_office = "bf_office_fan_0001";
  const std::string dev_living = "bf_living_fan_0002";
  const std::string key = "1234567890abcdef";

  // 0xFD50 service data with raw product_id
  std::vector<uint8_t> svc = {0x01, 0x30};
  svc.insert(svc.end(), pid.begin(), pid.end());

  // 0x07D0 mfg data with encrypted office device_id
  uint8_t key_iv[16];
  md5_hash(svc.data() + 2, svc.size() - 2, key_iv);
  std::vector<uint8_t> enc_uuid;
  assert(aes128_cbc_encrypt(key_iv, key_iv, reinterpret_cast<const uint8_t *>(dev_office.data()), 16, enc_uuid));
  std::vector<uint8_t> mfg = {0x00, 0x00};
  mfg.insert(mfg.end(), enc_uuid.begin(), enc_uuid.begin() + 16);

  // Must match office fan and NOT living room fan even though both share the same product_id!
  assert(match_tuya_advertisement(svc.data(), svc.size(), mfg.data(), mfg.size(), pid, dev_office, key));
  assert(!match_tuya_advertisement(svc.data(), svc.size(), mfg.data(), mfg.size(), pid, dev_living, key));
}

static void test_v3_a201_uuid_extraction() {
  // Real captured advertisement bytes from Varin VA-E002 / FlyFan (B8:06:0D:54:04:F6)
  const uint8_t sdata_a201[17] = {
      0x00, 0x1B, 0xDB, 0x4F, 0x8E, 0x99, 0xA1, 0xED,
      0x27, 0x00, 0x20, 0xA2, 0xAF, 0x58, 0x77, 0x93, 0x72,
  };
  const uint8_t mfg_07d0[22] = {
      0x89, 0x03, 0x00, 0x00, 0x0C, 0x00,
      0xEB, 0x6D, 0x0F, 0xFD, 0x34, 0xCD, 0x46, 0x7A,
      0xE1, 0x6F, 0xDD, 0xE3, 0x4D, 0xCE, 0xDD, 0x77,
  };

  std::string uuid;
  assert(extract_tuya_v3_uuid(sdata_a201, sizeof(sdata_a201), mfg_07d0, sizeof(mfg_07d0), uuid));
  assert(uuid == "9fdb2c8416a6872a");
}

int main() {
  test_crc16();
  test_packet_encrypt_decrypt_and_chunking();
  test_v3_dps_and_pair_and_device_info();
  test_advertisement_matching();
  test_v3_a201_uuid_extraction();
  std::cout << "All Tuya BLE protocol tests passed!" << std::endl;
  return 0;
}
