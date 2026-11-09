#pragma once
#include <stdint.h>
// Field order follows ESP-IDF 5.x (esp_wifi_types.h) for ESP32.
typedef struct { signed rssi : 8; } wifi_pkt_rx_ctrl_t;
typedef struct {
  wifi_pkt_rx_ctrl_t rx_ctrl;
  uint8_t mac[6];
  uint8_t dmac[6];
  bool first_word_invalid;
  int8_t* buf;
  uint16_t len;
} wifi_csi_info_t;
typedef struct { uint32_t filter_mask; } wifi_promiscuous_filter_t;
#define WIFI_PROMIS_FILTER_MASK_ALL 0xFFFFFFFF
typedef struct {
  bool lltf_en, htltf_en, stbc_htltf2_en, ltf_merge_en, channel_filter_en, manu_scale;
  uint8_t shift;
  bool dump_ack_en;
} wifi_csi_config_t;
typedef void (*wifi_csi_cb_t)(void* ctx, wifi_csi_info_t* data);
namespace sim { extern wifi_csi_cb_t csi_cb; }
inline int esp_wifi_set_promiscuous(bool) { return 0; }
inline int esp_wifi_set_promiscuous_filter(const wifi_promiscuous_filter_t*) { return 0; }
inline int esp_wifi_set_csi(bool) { return 0; }
inline int esp_wifi_set_csi_config(const wifi_csi_config_t*) { return 0; }
inline int esp_wifi_set_csi_rx_cb(wifi_csi_cb_t cb, void*) { sim::csi_cb = cb; return 0; }
