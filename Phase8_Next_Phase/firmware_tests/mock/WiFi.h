#pragma once
#include "Arduino.h"
#define WL_CONNECTED 3
#define WL_DISCONNECTED 6
#define WIFI_STA 1
class WiFiClass {
 public:
  void mode(int) {}
  void begin(const char*, const char*) {}
  void setAutoReconnect(bool) {}
  void setSleep(bool) {}
  int status() { return sim::wifi_connected ? WL_CONNECTED : WL_DISCONNECTED; }
  IPAddress localIP() { return IPAddress(192, 168, 1, 50); }
  uint8_t* BSSID() { static uint8_t b[6] = {1, 2, 3, 4, 5, 6}; return b; }
};
extern WiFiClass WiFi;
