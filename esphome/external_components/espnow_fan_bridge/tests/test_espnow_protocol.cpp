#include "espnow_protocol.h"
#include "espnow_fan_registry.h"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <iostream>

using namespace esphome::espnow_fan_bridge;

static void test_frame_roundtrip_and_auth() {
  const std::string key = "my_secret_key_1234";
  CmdPayload cmd;
  cmd.fan_key_hash = fnv1a_32("fan.bedroom_fan");
  cmd.opcode = CmdOpcode::LIGHT_STATE;
  cmd.arg0 = 1;
  cmd.arg1 = 750;
  cmd.arg2 = 420;

  auto payload = encode_cmd(cmd);
  auto frame = encode_frame(key, MsgType::CMD, 42, payload.data(), payload.size());
  assert(frame.size() == FRAME_HEADER_SIZE + payload.size());

  FrameHeader hdr;
  std::vector<uint8_t> out_payload;
  assert(decode_frame(key, frame.data(), frame.size(), hdr, out_payload));
  assert(hdr.type == MsgType::CMD);
  assert(hdr.seq == 42);

  CmdPayload decoded;
  assert(decode_cmd(out_payload.data(), out_payload.size(), decoded));
  assert(decoded.fan_key_hash == cmd.fan_key_hash);
  assert(decoded.opcode == CmdOpcode::LIGHT_STATE);
  assert(decoded.arg0 == 1);
  assert(decoded.arg1 == 750);
  assert(decoded.arg2 == 420);

  // Wrong network key must be rejected
  assert(!decode_frame("wrong_key", frame.data(), frame.size(), hdr, out_payload));

  // Corrupted payload byte must be rejected
  auto corrupted = frame;
  corrupted.back() ^= 0x01;
  assert(!decode_frame(key, corrupted.data(), corrupted.size(), hdr, out_payload));
}

static void test_state_and_ack_codecs() {
  const std::string key = "net_key";
  StatePayload st;
  st.fan_key_hash = fnv1a_32("fan.living_room_fan");
  st.ble_conn_status = 4;
  st.ble_rssi = -62;
  st.fan_on = 1;
  st.fan_speed = 5;
  st.fan_reverse = 1;
  st.fan_preset = 1;
  st.fan_timer = 120;
  st.light_on = 1;
  st.light_brightness = 800;
  st.light_color_temp = 333;

  auto payload = encode_state(st);
  auto frame = encode_frame(key, MsgType::STATE, 7, payload.data(), payload.size());
  FrameHeader hdr;
  std::vector<uint8_t> out_payload;
  assert(decode_frame(key, frame.data(), frame.size(), hdr, out_payload));
  StatePayload out;
  assert(decode_state(out_payload.data(), out_payload.size(), out));
  assert(out.fan_key_hash == st.fan_key_hash);
  assert(out.ble_conn_status == 4);
  assert(out.ble_rssi == -62);
  assert(out.fan_on == 1);
  assert(out.fan_speed == 5);
  assert(out.fan_reverse == 1);
  assert(out.fan_preset == 1);
  assert(out.fan_timer == 120);
  assert(out.light_on == 1);
  assert(out.light_brightness == 800);
  assert(out.light_color_temp == 333);

  AckPayload ack{99, AckStatus::UNKNOWN_FAN};
  auto ack_buf = encode_ack(ack);
  AckPayload ack_out;
  assert(decode_ack(ack_buf.data(), ack_buf.size(), ack_out));
  assert(ack_out.ack_seq == 99);
  assert(ack_out.status == AckStatus::UNKNOWN_FAN);
}

static void test_channel_hunt_single_multi_and_pruning() {
  ChannelHuntState hunt(1);
  // Before any peer is found, rests on fallback channel 1
  assert(hunt.active_channel(0, 250) == 1);

  // Sweep 1: discover peers on channel 6 and channel 11
  uint32_t t = 1000;
  hunt.start_sweep(t);
  assert(hunt.is_sweeping());
  int visited = 0;
  while (hunt.is_sweeping()) {
    bool should_ping = false;
    uint8_t ch = hunt.tick_sweep(t, 30, should_ping);
    if (ch > 0) {
      assert(should_ping);
      visited++;
      if (ch == 6 || ch == 11) {
        hunt.record_peer_channel(ch);
      }
    }
    t += 30;
  }
  assert(visited == 13);
  auto chans = hunt.active_channels();
  assert(chans.size() == 2 && chans[0] == 6 && chans[1] == 11);

  // Round-robin between 6 and 11 every 250ms
  assert(hunt.active_channel(5000, 250) == 6);
  assert(hunt.active_channel(5100, 250) == 6);
  assert(hunt.active_channel(5250, 250) == 11);
  assert(hunt.active_channel(5500, 250) == 6);

  // Sweep 2: channel 11 goes silent (1 miss -> still kept)
  t = 40000;
  hunt.start_sweep(t);
  while (hunt.is_sweeping()) {
    bool should_ping = false;
    uint8_t ch = hunt.tick_sweep(t, 30, should_ping);
    if (ch == 6) hunt.record_peer_channel(6);
    t += 30;
  }
  assert(hunt.active_channels().size() == 2);

  // Sweep 3: channel 11 silent again (2 misses -> pruned!)
  t = 80000;
  hunt.start_sweep(t);
  while (hunt.is_sweeping()) {
    bool should_ping = false;
    uint8_t ch = hunt.tick_sweep(t, 30, should_ping);
    if (ch == 6) hunt.record_peer_channel(6);
    t += 30;
  }
  chans = hunt.active_channels();
  assert(chans.size() == 1 && chans[0] == 6);
  // Single channel stays permanently parked on 6
  assert(hunt.active_channel(90000, 250) == 6);
  assert(hunt.active_channel(95000, 250) == 6);

  // Two more sweeps with no peers -> falls back to fallback_channel (1)
  for (int s = 0; s < 2; ++s) {
    t += 40000;
    hunt.start_sweep(t);
    while (hunt.is_sweeping()) {
      bool should_ping = false;
      hunt.tick_sweep(t, 30, should_ping);
      t += 30;
    }
  }
  assert(hunt.active_channels().empty());
  assert(hunt.active_channel(t + 100, 250) == 1);

  // Reconnecting to Wi-Fi must cancel any in-progress offline sweep so heartbeats resume
  hunt.start_sweep(t + 200);
  assert(hunt.is_sweeping());
  hunt.clear_active_channels();
  assert(!hunt.is_sweeping());
  assert(hunt.active_channels().empty());
}

static void test_v2_multihop_and_dedup() {
  const std::string key = "cyd_espnow_default";
  const uint32_t origin = 0x1234ABCDu;

  CmdPayload toggle_cmd;
  toggle_cmd.fan_key_hash = fnv1a_32("light.bedroom_fan_light");
  toggle_cmd.opcode = CmdOpcode::LIGHT_TOGGLE;
  auto payload = encode_cmd(toggle_cmd);

  // Encode frame with DEFAULT_RELAY_TTL (5) and hop_nonce=0
  auto f = encode_frame(key, MsgType::CMD, 77, payload.data(), payload.size(), origin,
                        DEFAULT_RELAY_TTL, 0);
  assert(f.size() == FRAME_HEADER_SIZE + payload.size());

  FrameHeader hdr;
  std::vector<uint8_t> out;
  assert(decode_frame(key, f.data(), f.size(), hdr, out));
  assert(hdr.type == MsgType::CMD);
  assert(hdr.seq == 77);
  assert(hdr.origin_id == origin);
  assert(hdr.ttl == DEFAULT_RELAY_TTL);
  assert(hdr.hop_nonce == 0);

  CmdPayload dec_cmd;
  assert(decode_cmd(out.data(), out.size(), dec_cmd));
  assert(dec_cmd.opcode == CmdOpcode::LIGHT_TOGGLE);
  assert(dec_cmd.fan_key_hash == toggle_cmd.fan_key_hash);

  // Tampering TTL or origin_id without re-signing must fail auth
  auto bad_ttl = f;
  bad_ttl[16] = 4;
  assert(!decode_frame(key, bad_ttl.data(), bad_ttl.size(), hdr, out));
  auto bad_origin = f;
  bad_origin[12] ^= 0x01;
  assert(!decode_frame(key, bad_origin.data(), bad_origin.size(), hdr, out));
  assert(!decode_frame("wrong_key", f.data(), f.size(), hdr, out));

  // Relaying with decremented TTL re-signs cleanly down to ttl=0
  auto hop1 = encode_frame(key, hdr.type, hdr.seq, out.data(), out.size(), hdr.origin_id,
                           hdr.ttl - 1, hdr.hop_nonce);
  assert(decode_frame(key, hop1.data(), hop1.size(), hdr, out));
  assert(hdr.ttl == DEFAULT_RELAY_TTL - 1);

  // FrameDedupRing: duplicate rejected within TTL, retry with new hop_nonce accepted, expires at TTL
  FrameDedupRing dedup;
  assert(dedup.accept(origin, MsgType::CMD, 77, 0, 1000, 5000));
  assert(!dedup.accept(origin, MsgType::CMD, 77, 0, 2000, 5000));  // duplicate relay dropped
  assert(dedup.accept(origin, MsgType::CMD, 77, 1, 2300, 5000));   // retry attempt 1 relayed!
  assert(!dedup.accept(origin, MsgType::CMD, 77, 1, 3000, 5000));  // duplicate retry dropped
  assert(dedup.accept(origin, MsgType::CMD, 77, 0, 6000, 5000));   // expired at 5s TTL
}

static void test_shelly_wifi_down_instant_fallback() {
  EspNowFanRegistry reg;
  RemoteShellyState sh;
  sh.name = "Office Light";
  sh.entity_id = "light.office";
  sh.has_state = true;
  sh.espnow_reachable = true;
  sh.state_flags = 0x01;  // ON, Wi-Fi UP (bit 7 = 0)
  reg.register_remote_shelly(&sh);

  RemoteBleConnStatus ble_st = RemoteBleConnStatus::DISCONNECTED;
  std::string text;
  bool bin = false;

  // HA available + Shelly Wi-Fi UP -> normal HA tier (NONE)
  assert(!sh.wifi_down_fallback());
  assert(reg.get_display_mode("light.office", true, ble_st) == EspNowDisplayMode::NONE);
  assert(!reg.get_text_state("light.office", true, text));
  assert(!reg.get_binary_state("light.office", true, bin));

  // Shelly drops off Wi-Fi (bit 7 = 0x80) while HA still thinks entity is available -> instant backup!
  sh.state_flags = 0x81;  // ON + WIFI_DOWN
  assert(sh.wifi_down_fallback());
  assert(reg.get_display_mode("light.office", true, ble_st) == EspNowDisplayMode::ACTIVE);
  assert(ble_st == RemoteBleConnStatus::CONNECTED);
  assert(reg.get_text_state("light.office", true, text) && text == "on");
  assert(reg.get_binary_state("light.office", true, bin) && bin == true);

  // Shelly reconnects to Wi-Fi (bit 7 clears) -> instant return to normal HA tier
  sh.state_flags = 0x00;  // OFF, Wi-Fi UP
  assert(!sh.wifi_down_fallback());
  assert(reg.get_display_mode("light.office", true, ble_st) == EspNowDisplayMode::NONE);
  assert(!reg.get_text_state("light.office", true, text));
}

int main() {
  test_frame_roundtrip_and_auth();
  test_state_and_ack_codecs();
  test_channel_hunt_single_multi_and_pruning();
  test_v2_multihop_and_dedup();
  test_shelly_wifi_down_instant_fallback();
  std::cout << "All espnow_protocol tests passed!\n";
  return 0;
}
