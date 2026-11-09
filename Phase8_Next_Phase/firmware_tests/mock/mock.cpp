#include "Arduino.h"
#include "WiFi.h"
#include "ESPmDNS.h"
#include "esp_wifi.h"
namespace sim {
uint32_t now_ms = 0;
std::map<int, int> pin_out, pin_in, pin_mode;
bool verbose = false;
std::vector<Packet> sent;
std::map<int, std::deque<std::string>> inbox;
bool wifi_connected = true;
bool mdns_resolves = true;
std::string serial_out;
wifi_csi_cb_t csi_cb = nullptr;
}
HardwareSerialMock Serial;
WiFiClass WiFi;
MDNSResponder MDNS;
struct Q { size_t item; size_t cap; std::deque<std::vector<uint8_t>> d; };
QueueHandle_t xQueueCreate(int len, size_t item) { return new Q{item, (size_t)len, {}}; }
int xQueueSendFromISR(QueueHandle_t h, const void* item, void*) {
  Q* q = (Q*)h;
  if (q->d.size() >= q->cap) return pdFALSE;
  const uint8_t* p = (const uint8_t*)item;
  q->d.emplace_back(p, p + q->item);
  return pdTRUE;
}
int xQueueReceive(QueueHandle_t h, void* item, uint32_t) {
  Q* q = (Q*)h;
  if (q->d.empty()) return pdFALSE;
  memcpy(item, q->d.front().data(), q->item);
  q->d.pop_front();
  return pdTRUE;
}
