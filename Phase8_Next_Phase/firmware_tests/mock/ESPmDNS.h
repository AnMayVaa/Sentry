#pragma once
#include "Arduino.h"
class MDNSResponder {
 public:
  bool begin(const char*) { return true; }
  IPAddress queryHost(const char*, uint32_t timeout = 2000) {
    sim::now_ms += sim::mdns_resolves ? 5 : timeout;  // a failed lookup blocks for the timeout
    return sim::mdns_resolves ? IPAddress(192, 168, 1, 10) : IPAddress();
  }
};
extern MDNSResponder MDNS;
