#pragma once
#include "mock/Arduino.h"
#include <functional>
// Run loop() once per simulated ms for `ms` milliseconds.
// Returns how many ms the given output pin was HIGH, and how many on/off edges it had.
struct PinStats { int high_ms = 0; int edges = 0; };
static PinStats run_for(uint32_t ms, int watch_pin = 4) {
  PinStats st; int last = sim::pin_out[watch_pin];
  uint32_t end = sim::now_ms + ms;
  while ((int32_t)(sim::now_ms - end) < 0) {
    loop();
    int v = sim::pin_out[watch_pin];
    st.high_ms += v; st.edges += v != last; last = v;
    sim::now_ms++;
  }
  return st;
}
static void press(int pin, bool down) { sim::pin_in[pin] = down ? LOW : HIGH; }
static int count_sent(const std::string& ip, int port, const std::string& data) {
  int n = 0;
  for (auto& p : sim::sent) n += p.ip == ip && p.port == port && p.data == data;
  return n;
}
static int count_sent_prefix(int port, const std::string& prefix) {
  int n = 0;
  for (auto& p : sim::sent) n += p.port == port && p.data.rfind(prefix, 0) == 0;
  return n;
}
static void reset_sim() {
  sim::now_ms = 1; sim::pin_out.clear(); sim::pin_in.clear(); sim::pin_mode.clear();
  sim::sent.clear(); sim::inbox.clear(); sim::serial_out.clear();
  sim::wifi_connected = true; sim::mdns_resolves = true;
}
