#include "espnow_protocol.h"

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
}

int main() {
  test_frame_roundtrip_and_auth();
  test_state_and_ack_codecs();
  test_channel_hunt_single_multi_and_pruning();
  std::cout << "All espnow_protocol tests passed!\n";
  return 0;
}
