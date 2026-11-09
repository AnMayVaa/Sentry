// Simulates the real Phase8_RX_Node.ino on a PC.
#include "mock/Arduino.h"
#include "../Phase8_RX_Node/Phase8_RX_Node.ino"
#include "sim_helpers.h"
#include "testkit.h"

// Each test boots a fresh copy of the sketch's globals.
static void boot() {
  reset_sim();
  node_state = STATE_IDLE; target_resolved = false; router_mac_known = false; mdns_started = false;
  button = sentry::Button(30, SOS_HOLD_MS); siren = sentry::PatternPlayer(); sos_retry = sentry::Retry();
  setup();
  run_for(1000);       // boot beeps, mDNS
  sim::sent.clear();
}
static const char* PI_IP = "192.168.1.10";
static const char* BCAST = "255.255.255.255";

TEST(hold_2s_sends_sos_three_times_to_pi_and_stations) {
  boot();
  press(BUTTON_PIN, true);
  PinStats hold = run_for(1900);
  CHECK(count_sent_prefix(5000, "SOS_ALERT") == 0);  // not yet
  CHECK(sim::pin_out[LED_PIN] == 1);                  // LED solid = keep holding
  CHECK(hold.high_ms == 0);                           // no sound while charging
  run_for(800);
  press(BUTTON_PIN, false);
  run_for(500);
  CHECK(count_sent(PI_IP, 5000, "SOS_ALERT,Bath Room\n") == 3);
  CHECK(count_sent(BCAST, 5005, "SOS_ALERT:Bath Room") == 3);
  CHECK(node_state == STATE_SOS_ACTIVE);
  PinStats s = run_for(4000);
  CHECK(s.edges >= 10);                               // SOS rhythm is sounding
  CHECK(sim::serial_out.find("SOS_ALERT,Bath Room\n") != std::string::npos);  // USB mode too
}
TEST(short_press_in_idle_does_not_send_sos) {
  boot();
  press(BUTTON_PIN, true); run_for(600); press(BUTTON_PIN, false); run_for(3000);
  CHECK(count_sent_prefix(5000, "SOS_ALERT") == 0);
  CHECK(node_state == STATE_IDLE);
}
TEST(press_silences_sos_siren_but_all_copies_still_go_out) {
  boot();
  press(BUTTON_PIN, true); run_for(2050); press(BUTTON_PIN, false); run_for(60);
  press(BUTTON_PIN, true); run_for(40);                               // press again
  CHECK(node_state == STATE_IDLE);                                    // silenced on press
  PinStats after = run_for(3000); press(BUTTON_PIN, false); run_for(50);
  CHECK(node_state == STATE_IDLE);
  CHECK(after.high_ms == 0);
  CHECK(count_sent(PI_IP, 5000, "SOS_ALERT,Bath Room\n") == 3);
}
TEST(sos_falls_back_to_broadcast_when_pi_not_found) {
  reset_sim(); sim::mdns_resolves = false;
  node_state = STATE_IDLE; target_resolved = false; mdns_started = false;
  button = sentry::Button(30, SOS_HOLD_MS); siren = sentry::PatternPlayer(); sos_retry = sentry::Retry();
  setup(); run_for(500); sim::sent.clear();
  press(BUTTON_PIN, true); run_for(2100); press(BUTTON_PIN, false); run_for(800);
  CHECK(count_sent(BCAST, 5000, "SOS_ALERT,Bath Room\n") == 3);
  CHECK(count_sent(BCAST, 5005, "SOS_ALERT:Bath Room") == 3);
}
TEST(fall_alert_rings_until_remote_silence) {
  boot();
  sim::inbox[5005].push_back("FALL_ALERT:[192.168.1.50] Bath Room");
  PinStats ring = run_for(2000);
  CHECK(node_state == STATE_FALL_ALARM);
  CHECK(ring.edges >= 14);                    // 250 ms cycle -> ~16 edges in 2 s
  sim::inbox[5005].push_back("FALL_SILENCE");
  run_for(5);
  PinStats quiet = run_for(2000);
  CHECK(quiet.high_ms == 0);
  CHECK(node_state == STATE_IDLE);
}
TEST(button_silences_fall_and_long_hold_then_is_not_an_sos) {
  boot();
  sim::inbox[5005].push_back("FALL_ALERT:Bath Room");
  run_for(500);
  press(BUTTON_PIN, true); run_for(3000); press(BUTTON_PIN, false); run_for(1000);
  CHECK(node_state == STATE_IDLE);
  CHECK(count_sent_prefix(5000, "SOS_ALERT") == 0);
}
TEST(rx_ignores_sos_broadcasts_meant_for_stations) {
  boot();
  sim::inbox[5005].push_back("SOS_ALERT:Bed Room");
  PinStats s = run_for(1000);
  CHECK(node_state == STATE_IDLE); CHECK(s.high_ms == 0);
}
TEST(csi_frame_is_sent_as_one_line) {
  boot();
  wifi_csi_info_t info{}; int8_t buf[128];
  for (int i = 0; i < 128; i++) buf[i] = (int8_t)(i - 64);
  memcpy(info.mac, dedicated_tx_mac, 6); info.buf = buf; info.len = 128; info.rx_ctrl.rssi = -40;
  sim::csi_cb(nullptr, &info);
  run_for(2);
  bool found = false;
  for (auto& p : sim::sent) if (p.port == 5000 && p.data.rfind("CSI_DATA,Bath Room,", 0) == 0) {
    found = true;
    CHECK(p.data.back() == '\n');
    CHECK(p.data.find(",-64,-63,") != std::string::npos);
    CHECK(p.data.find(",63\n") != std::string::npos);
  }
  CHECK(found);
  // Frames from other transmitters are dropped
  sim::sent.clear(); info.mac[0] ^= 0xFF; sim::csi_cb(nullptr, &info); run_for(2);
  CHECK(count_sent_prefix(5000, "CSI_DATA") == 0);
}
TEST(heartbeats_every_5s) {
  boot();
  run_for(11000);
  CHECK(count_sent(PI_IP, 5000, "HEARTBEAT\n") == 2);
  CHECK(count_sent(PI_IP, 5002, "ALARM_READY:192.168.1.50\n") == 2);
}
TEST(boot_without_wifi_does_not_hang_and_button_works) {
  reset_sim(); sim::wifi_connected = false;
  node_state = STATE_IDLE; target_resolved = false; mdns_started = false;
  button = sentry::Button(30, SOS_HOLD_MS); siren = sentry::PatternPlayer(); sos_retry = sentry::Retry();
  setup();                       // must return after the Wi-Fi wait
  CHECK(sim::now_ms < 25000);
  press(BUTTON_PIN, true); run_for(200); press(BUTTON_PIN, false);
  PinStats s = run_for(600);
  CHECK(s.high_ms == 0);         // "no Wi-Fi" status flash is silent...
}
int main() { return run_all("rx_node"); }
