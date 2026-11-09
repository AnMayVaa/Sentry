// Simulates the real Phase8_Alert_Station.ino on a PC.
#include "mock/Arduino.h"
#include "../Phase8_Alert_Station/Phase8_Alert_Station.ino"
#include "sim_helpers.h"
#include "testkit.h"

static void boot() {
  reset_sim();
  setup();
  run_for(1000);    // connect beeps
  sim::sent.clear();
}
static void udp_in(const char* msg) { sim::inbox[ALARM_UDP_PORT].push_back(msg); }

TEST(fall_alert_rings_fast_until_button) {
  boot();
  udp_in("FALL_ALERT:[192.168.1.20] Bath Room");
  PinStats r = run_for(2000);
  CHECK(state == ST_RINGING); CHECK(ringing_kind == sentry::MSG_FALL);
  CHECK(strcmp(ringing_loc, "Bath Room") == 0);
  CHECK(r.edges >= 14);
  press(BUTTON_PIN, true); run_for(40);
  CHECK(state == ST_IDLE);                    // silenced on press, not on release
  PinStats q = run_for(3000); press(BUTTON_PIN, false); run_for(100);
  CHECK(q.high_ms == 0);                      // and holding on does not start the self-test
}
TEST(sos_sounds_different_from_fall) {
  boot();
  udp_in("FALL_ALERT:Bath Room"); PinStats fall = run_for(3000);
  udp_in("FALL_SILENCE"); run_for(10);
  udp_in("SOS_ALERT:Bed Room"); PinStats sos = run_for(3000);
  CHECK(ringing_kind == sentry::MSG_SOS);
  CHECK(fall.edges > sos.edges + 5);          // SOS is a slower Morse rhythm
}
TEST(sos_outranks_fall) {
  boot();
  udp_in("SOS_ALERT:Bed Room"); run_for(100);
  udp_in("FALL_ALERT:Bath Room"); run_for(100);
  CHECK(ringing_kind == sentry::MSG_SOS); CHECK(strcmp(ringing_loc, "Bed Room") == 0);
}
TEST(copies_of_a_silenced_alert_do_not_restart_it) {
  boot();
  udp_in("SOS_ALERT:Bath Room"); run_for(100);
  press(BUTTON_PIN, true); run_for(50); press(BUTTON_PIN, false); run_for(50);
  CHECK(state == ST_IDLE);
  udp_in("SOS_ALERT:Bath Room");                 // RX retry
  udp_in("SOS_ALERT:[192.168.1.20] Bath Room");  // Pi re-broadcast of the same SOS
  PinStats q = run_for(1000);
  CHECK(state == ST_IDLE); CHECK(q.high_ms == 0);
  udp_in("SOS_ALERT:Bed Room"); run_for(100);    // another room still gets through
  CHECK(state == ST_RINGING);
  udp_in("FALL_SILENCE"); run_for(9000);
  udp_in("SOS_ALERT:Bath Room"); run_for(100);   // a new SOS later rings again
  CHECK(state == ST_RINGING);
}
TEST(remote_silence_stops_it) {
  boot();
  udp_in("FALL_ALERT:Bath Room"); run_for(500);
  udp_in("FALL_SILENCE"); run_for(10);
  CHECK(state == ST_IDLE); CHECK(sim::pin_out[BUZZER_PIN] == 0);
}
TEST(long_press_idle_is_self_test) {
  boot();
  press(BUTTON_PIN, true); PinStats hold = run_for(2100); press(BUTTON_PIN, false);
  PinStats t = run_for(1500);
  CHECK(hold.high_ms + t.high_ms >= 900);   // ~1 s test beep
  CHECK(state == ST_IDLE);
  CHECK(count_sent_prefix(HEARTBEAT_UDP_PORT, "ALARM_READY:") >= 1);
}
TEST(heartbeat_every_5s_to_pi) {
  boot();
  run_for(10500);
  CHECK(count_sent("255.255.255.255", 5002, "ALARM_READY:192.168.1.50") == 2);
}
TEST(idle_led_shows_wifi_state) {
  boot();
  PinStats ok = run_for(6000, LED_PIN);
  CHECK(ok.edges == 4);                      // 2 tiny blinks in 6 s
  sim::wifi_connected = false;
  PinStats bad = run_for(3000, LED_PIN);
  CHECK(bad.edges >= 10);                    // double blink every second
  CHECK(sim::pin_out[BUZZER_PIN] == 0);
}
TEST(ignores_unrelated_traffic) {
  boot();
  udp_in("ROUTER_STIMULUS"); udp_in("ALARM_READY:1.2.3.4"); udp_in("garbage\xff\xfe");
  PinStats s = run_for(1000);
  CHECK(state == ST_IDLE); CHECK(s.high_ms == 0);
}
TEST(buzzer_pin_low_when_idle_active_high) {
  boot();
  run_for(100);
  CHECK(sim::pin_mode[BUZZER_PIN] == OUTPUT);
  CHECK(sim::pin_out[BUZZER_PIN] == 0);
}
int main() { return run_all("alert_station"); }
