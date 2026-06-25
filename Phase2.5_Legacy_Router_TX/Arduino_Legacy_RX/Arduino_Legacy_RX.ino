#include <WiFi.h>
#include <WiFiUdp.h>
#include <esp_wifi.h>

const char* ssid = "BUNDAOBUNTAI";
const char* password = "ohm12345";
WiFiUDP udp;

QueueHandle_t csi_queue;

typedef struct {
    uint8_t mac[6];
    int8_t rssi;
    uint16_t len;
    int8_t buf[128]; 
    bool is_sos;
} csi_packet_t;

uint8_t router_mac[6];

// The CSI Callback
void wifi_csi_rx_cb(void *ctx, wifi_csi_info_t *info) {
    if (!info || !info->buf) return;
    
    // Filter for Router MAC
    bool is_router = (info->mac[0] == router_mac[0] && info->mac[1] == router_mac[1] && 
                      info->mac[2] == router_mac[2] && info->mac[3] == router_mac[3] && 
                      info->mac[4] == router_mac[4] && info->mac[5] == router_mac[5]);

    if (is_router) {
        csi_packet_t pkt;
        memset(&pkt, 0, sizeof(csi_packet_t));
        
        pkt.is_sos = false;
        memcpy(pkt.mac, info->mac, 6);
        pkt.rssi = info->rx_ctrl.rssi;
        pkt.len = info->len > 128 ? 128 : info->len;
        memcpy(pkt.buf, info->buf, pkt.len);
        xQueueSendFromISR(csi_queue, &pkt, NULL);
    }
}

void setup() {
    Serial.begin(460800);
    pinMode(0, INPUT_PULLUP);
    
    csi_queue = xQueueCreate(30, sizeof(csi_packet_t));
    
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);
    
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
    }
    Serial.println();
    Serial.printf("ESP32_IP,%s\n", WiFi.localIP().toString().c_str());

    uint8_t* bssid = WiFi.BSSID();
    memcpy(router_mac, bssid, 6);

    udp.begin(5000);

    esp_wifi_set_promiscuous(true);
    wifi_promiscuous_filter_t rx_filter = { .filter_mask = WIFI_PROMIS_FILTER_MASK_ALL };
    esp_wifi_set_promiscuous_filter(&rx_filter);
    
    esp_wifi_set_csi(true);
    wifi_csi_config_t csi_config = {
        .lltf_en = true, .htltf_en = true, .stbc_htltf2_en = true,
        .ltf_merge_en = true, .channel_filter_en = true,
        .manu_scale = false, .shift = false,
    };
    esp_wifi_set_csi_config(&csi_config);
    esp_wifi_set_csi_rx_cb(wifi_csi_rx_cb, NULL);
}

void loop() {
    // Read and discard UDP pings to keep the buffer clean
    int packetSize = udp.parsePacket();
    if (packetSize) {
        char incomingPacket[255];
        udp.read(incomingPacket, 255);
    }

    // if (digitalRead(0) == LOW) {
    //     Serial.printf("SOS_ALERT\n");
    //     delay(1000); 
    // }
    
    csi_packet_t pkt;
    if (xQueueReceive(csi_queue, &pkt, 0) == pdTRUE) {
        if (pkt.is_sos) {
            Serial.printf("SOS_ALERT\n");
        } else {
            Serial.printf("CSI_DATA,%d,%d,%d,", pkt.mac[0], pkt.rssi, pkt.len);
            for (int i = 0; i < pkt.len; i++) {
                Serial.printf("%d", pkt.buf[i]);
                if (i < pkt.len - 1) {
                    Serial.printf(",");
                }
            }
            Serial.printf("\n");
        }
    }
}
