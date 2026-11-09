#pragma once
#include "Arduino.h"
class WiFiUDP : public Print {
 public:
  uint8_t begin(uint16_t port) { port_ = port; return 1; }
  void stop() {}
  int parsePacket() {
    auto& q = sim::inbox[port_];
    if (q.empty()) return 0;
    cur_ = q.front();
    q.pop_front();
    return (int)cur_.size();
  }
  int read(char* buf, size_t len) {
    size_t n = cur_.size() < len ? cur_.size() : len;
    memcpy(buf, cur_.data(), n);
    cur_.clear();
    return (int)n;
  }
  int beginPacket(IPAddress ip, uint16_t port) { out_ip_ = ip.toString().str(); out_port_ = port; out_.clear(); return 1; }
  size_t write(const uint8_t* b, size_t n) override { out_.append((const char*)b, n); return n; }
  using Print::write;
  int endPacket() { sim::sent.push_back({out_ip_, out_port_, out_}); return 1; }
 private:
  uint16_t port_ = 0;
  std::string cur_, out_, out_ip_;
  int out_port_ = 0;
};
