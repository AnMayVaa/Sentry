// Minimal PC stand-in for the Arduino-ESP32 API, just enough to compile and
// simulate the Phase 8 sketches. NOT a full emulator: it checks our logic
// (button, alarms, UDP messages), not Wi-Fi radio behaviour.
#pragma once
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <string>
#include <vector>
#include <deque>
#include <map>

#define HIGH 1
#define LOW 0
#define INPUT 0x01
#define OUTPUT 0x03
#define INPUT_PULLUP 0x05

namespace sim {
extern bool mdns_resolves;
extern uint32_t now_ms;
extern std::map<int, int> pin_out;     // what the sketch wrote
extern std::map<int, int> pin_in;      // what digitalRead returns
extern std::map<int, int> pin_mode;
extern bool verbose;
struct Packet { std::string ip; int port; std::string data; };
extern std::vector<Packet> sent;                    // every UDP packet the sketch sent
extern std::map<int, std::deque<std::string>> inbox; // per local port
extern bool wifi_connected;
extern std::string serial_out;
}

inline uint32_t millis() { return sim::now_ms; }
inline void delay(uint32_t ms) { sim::now_ms += ms; }
inline void pinMode(int pin, int mode) { sim::pin_mode[pin] = mode; }
inline void digitalWrite(int pin, int v) { sim::pin_out[pin] = v ? 1 : 0; }
inline int digitalRead(int pin) {
  auto it = sim::pin_in.find(pin);
  if (it != sim::pin_in.end()) return it->second;
  return sim::pin_mode[pin] == INPUT_PULLUP ? HIGH : LOW;
}

class String {
 public:
  String() {}
  String(const char* c) : s_(c ? c : "") {}
  String(const std::string& s) : s_(s) {}
  String(int v) : s_(std::to_string(v)) {}
  const char* c_str() const { return s_.c_str(); }
  size_t length() const { return s_.size(); }
  void trim() {
    size_t a = s_.find_first_not_of(" \t\r\n");
    size_t b = s_.find_last_not_of(" \t\r\n");
    s_ = (a == std::string::npos) ? "" : s_.substr(a, b - a + 1);
  }
  bool startsWith(const String& p) const { return s_.rfind(p.s_, 0) == 0; }
  bool operator==(const char* o) const { return s_ == o; }
  bool operator==(const String& o) const { return s_ == o.s_; }
  String operator+(const String& o) const { return String(s_ + o.s_); }
  String operator+(const char* o) const { return String(s_ + o); }
  friend String operator+(const char* a, const String& b) { return String(std::string(a) + b.s_); }
  const std::string& str() const { return s_; }
 private:
  std::string s_;
};

class Print {
 public:
  virtual ~Print() {}
  virtual size_t write(const uint8_t* b, size_t n) = 0;
  size_t write(const char* b, size_t n) { return write((const uint8_t*)b, n); }
  size_t print(const char* s) { return write((const uint8_t*)s, strlen(s)); }
  size_t print(const String& s) { return print(s.c_str()); }
  size_t println(const char* s = "") { size_t n = print(s); return n + print("\n"); }
  size_t println(const String& s) { return println(s.c_str()); }
  template <class T> size_t println(const T& printable) { return println(printable.toString()); }  // IPAddress
  template <class T> size_t print(const T& printable) { return print(printable.toString()); }
  size_t printf(const char* fmt, ...) __attribute__((format(printf, 2, 3))) {
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    return n > 0 ? write((const uint8_t*)buf, (size_t)n) : 0;
  }
};

class IPAddress {
 public:
  IPAddress() : a_{0, 0, 0, 0} {}
  IPAddress(uint8_t a, uint8_t b, uint8_t c, uint8_t d) : a_{a, b, c, d} {}
  bool operator==(const IPAddress& o) const { return memcmp(a_, o.a_, 4) == 0; }
  String toString() const {
    char b[20];
    snprintf(b, sizeof(b), "%u.%u.%u.%u", a_[0], a_[1], a_[2], a_[3]);
    return String(b);
  }
 private:
  uint8_t a_[4];
};

class HardwareSerialMock : public Print {
 public:
  void begin(unsigned long) {}
  size_t write(const uint8_t* b, size_t n) override {
    sim::serial_out.append((const char*)b, n);
    if (sim::verbose) fwrite(b, 1, n, stdout);
    return n;
  }
  using Print::write;
};
extern HardwareSerialMock Serial;

// FreeRTOS queue (single-threaded stand-in)
typedef void* QueueHandle_t;
#define pdTRUE 1
#define pdFALSE 0
QueueHandle_t xQueueCreate(int len, size_t item);
int xQueueSendFromISR(QueueHandle_t q, const void* item, void*);
int xQueueReceive(QueueHandle_t q, void* item, uint32_t);
