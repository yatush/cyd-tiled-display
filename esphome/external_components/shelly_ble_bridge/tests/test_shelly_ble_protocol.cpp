#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

#include "../shelly_ble_protocol.h"
#include "../../espnow_fan_bridge/espnow_protocol.h"

using namespace esphome::shelly_ble_bridge;

int main() {
  const std::string key = "cyd_espnow_default";
  const std::string wrong_key = "wrong_key";

  // 1. MAC normalization & FNV-1a consistency between shelly_ble_bridge and espnow_fan_bridge
  assert(normalize_mac_hex("AA:BB:CC:DD:EE:01") == "aabbccddee01");
  assert(normalize_mac_hex("aa-bb-cc-dd-ee-01") == "aabbccddee01");
  uint32_t dev_id = shelly_device_id_from_mac("AA:BB:CC:DD:EE:01");
  assert(dev_id == esphome::espnow_fan_bridge::shelly_device_id_from_mac("aabbccddee01"));

  // 2. BLE Command encode/decode + wrong-key rejection
  ShellyBleCmd cmd;
  cmd.target_id = dev_id;
  cmd.channel = 1;
  cmd.opcode = ShellyBleOpcode::COV_POS;
  cmd.arg = 65;
  cmd.flags = 0;
  cmd.seq = 42;

  auto enc_cmd = encode_ble_cmd(key, cmd);
  assert(enc_cmd.size() == 14);

  ShellyBleCmd dec_cmd{};
  assert(decode_ble_cmd(key, enc_cmd.data(), enc_cmd.size(), dec_cmd));
  assert(dec_cmd.target_id == dev_id);
  assert(dec_cmd.channel == 1);
  assert(dec_cmd.opcode == ShellyBleOpcode::COV_POS);
  assert(dec_cmd.arg == 65);
  assert(dec_cmd.seq == 42);

  assert(!decode_ble_cmd(wrong_key, enc_cmd.data(), enc_cmd.size(), dec_cmd));
  enc_cmd[5] ^= 0x01;  // tamper
  assert(!decode_ble_cmd(key, enc_cmd.data(), enc_cmd.size(), dec_cmd));

  // 3. BLE State & Input beacon encode/decode
  ShellyBleBeacon bcn;
  bcn.source_id = dev_id;
  bcn.channel = 0;
  bcn.kind = ShellyBleKind::COVER;
  bcn.state_flags = SHELLY_FLAG_ON_OR_OPEN | (1u << 1) | SHELLY_FLAG_WIFI_DOWN;
  bcn.position = 40;
  bcn.seq = 1001;

  auto enc_bcn = encode_ble_beacon(key, bcn);
  ShellyBleBeacon dec_bcn{};
  assert(decode_ble_beacon(key, enc_bcn.data(), enc_bcn.size(), dec_bcn));
  assert(dec_bcn.source_id == dev_id);
  assert(dec_bcn.channel == 0);
  assert(dec_bcn.kind == ShellyBleKind::COVER);
  assert(dec_bcn.state_flags == bcn.state_flags);
  assert(dec_bcn.position == 40);
  assert(dec_bcn.seq == 1001);
  assert(!decode_ble_beacon(wrong_key, enc_bcn.data(), enc_bcn.size(), dec_bcn));

  // 4. Raw BLE ADV packet layout (AD Flags + 16-bit Service Data 0xC753 little-endian)
  auto raw = build_service_data_adv_raw(UUID_SHELLY_CMD, encode_ble_cmd(key, cmd));
  assert(raw.size() == 21);
  assert(raw[0] == 0x02 && raw[1] == 0x01 && raw[2] == 0x06);
  assert(raw[3] == 0x11 && raw[4] == 0x16);
  assert(raw[5] == 0x53 && raw[6] == 0xC7);  // Little-endian 0xC753

  // 5. SeqDedupRing deduplication + TTL expiration
  SeqDedupRing dedup;
  assert(dedup.accept(dev_id, 10, 1000, 5000));
  assert(!dedup.accept(dev_id, 10, 2000, 5000));  // duplicate within 5s TTL rejected
  assert(!dedup.accept(dev_id, 10, 5999, 5000));  // still within 5s TTL
  assert(dedup.accept(dev_id, 10, 6000, 5000));   // expired at 5s TTL -> accepted again
  assert(dedup.accept(dev_id, 11, 6100, 5000));   // new seq accepted
  assert(dedup.accept(dev_id + 1, 10, 6100, 5000));  // different device accepted

  // 6. ShellyTxQueue FIFO + coalescing by (target_id, channel)
  ShellyTxQueue q;
  ShellyBleCmd c1{dev_id, 0, ShellyBleOpcode::COV_POS, 20, 0, 1};
  ShellyBleCmd c2{dev_id, 1, ShellyBleOpcode::SW_ON, 0, 0, 2};
  ShellyBleCmd c3{dev_id, 0, ShellyBleOpcode::COV_POS, 80, 0, 3};  // coalesces c1
  q.enqueue(c1);
  q.enqueue(c2);
  q.enqueue(c3);
  assert(q.size() == 2);

  ShellyBleCmd popped{};
  assert(q.pop(popped));
  assert(popped.channel == 0 && popped.arg == 80 && popped.seq == 3);
  assert(q.pop(popped));
  assert(popped.channel == 1 && popped.opcode == ShellyBleOpcode::SW_ON);
  assert(q.empty());

  // 7. ESP-NOW SHELLY_CMD and SHELLY_STATE frame round-trip
  esphome::espnow_fan_bridge::ShellyCmdPayload scmd;
  scmd.device_id = dev_id;
  scmd.channel = 0;
  scmd.opcode = esphome::espnow_fan_bridge::ShellyOpcode::COV_POS;
  scmd.arg = 75;
  auto frame = esphome::espnow_fan_bridge::encode_frame(
      key, esphome::espnow_fan_bridge::MsgType::SHELLY_CMD, 7,
      esphome::espnow_fan_bridge::encode_shelly_cmd(scmd).data(), 8);
  esphome::espnow_fan_bridge::FrameHeader hdr;
  std::vector<uint8_t> payload;
  assert(esphome::espnow_fan_bridge::decode_frame(key, frame.data(), frame.size(), hdr, payload));
  assert(hdr.type == esphome::espnow_fan_bridge::MsgType::SHELLY_CMD);
  esphome::espnow_fan_bridge::ShellyCmdPayload dec_scmd;
  assert(esphome::espnow_fan_bridge::decode_shelly_cmd(payload.data(), payload.size(), dec_scmd));
  assert(dec_scmd.device_id == dev_id && dec_scmd.arg == 75);

  esphome::espnow_fan_bridge::ShellyStatePayload sst;
  sst.device_id = dev_id;
  sst.channel = 1;
  sst.kind = esphome::espnow_fan_bridge::ShellyKind::SWITCH;
  sst.state_flags = 0x81;
  sst.position = 255;
  sst.ble_rssi = -62;
  auto sbytes = esphome::espnow_fan_bridge::encode_shelly_state(sst);
  esphome::espnow_fan_bridge::ShellyStatePayload dec_sst;
  assert(esphome::espnow_fan_bridge::decode_shelly_state(sbytes.data(), sbytes.size(), dec_sst));
  assert(dec_sst.device_id == dev_id && dec_sst.channel == 1 && dec_sst.ble_rssi == -62);

  std::printf("test_shelly_ble_protocol: ALL PASSED\n");
  return 0;
}
