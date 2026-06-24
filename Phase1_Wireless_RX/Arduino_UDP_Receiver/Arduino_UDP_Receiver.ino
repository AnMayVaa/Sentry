#include <WiFi.h>
#include <WiFiUdp.h>
#include <esp_wifi.h>

#include <ESPmDNS.h>

// --- CONFIGURATION ---
const char* ssid = "BUNDAOBUNTAI";
const char* password = "ohm12345";
const char* dest_host = "OhmPatumwan"; // Hostname of the Raspberry Pi
const int dest_port = 5000;

WiFiUDP udp;
IPAddress target_ip;
bool target_resolved = false;

// We use FreeRTOS queues just like in ESP-IDF to prevent crashing!
QueueHandle_t csi_queue;

typedef struct {
    uint8_t mac[6];
    int8_t rssi;
    uint16_t len;
    int8_t buf[128]; // Use signed integers so UDP transmits negative numbers correctly
    bool is_sos;
} csi_packet_t;

// The CSI Callback (Runs in the background Wi-Fi thread)
void wifi_csi_rx_cb(void *ctx, wifi_csi_info_t *info) {
    if (!info || !info->buf) return;
    
    // Check if it matches our specific TX Node MAC
    bool is_our_tx = (info->mac[0] == 0xD4 && info->mac[1] == 0xE9 && info->mac[2] == 0xF4 &&
                      info->mac[3] == 0xA4 && info->mac[4] == 0x40 && info->mac[5] == 0xEC);

    if (is_our_tx) {
        csi_packet_t pkt;
        memset(&pkt, 0, sizeof(csi_packet_t));
        
        if (info->rx_ctrl.sig_len > 100) {
            pkt.is_sos = true;
        } else {
            pkt.is_sos = false;
            memcpy(pkt.mac, info->mac, 6);
            pkt.rssi = info->rx_ctrl.rssi;
            pkt.len = info->len > 128 ? 128 : info->len;
            memcpy(pkt.buf, info->buf, pkt.len);
        }
        
        // Push safely to queue
        xQueueSendFromISR(csi_queue, &pkt, NULL);
    }
}

void setup() {
    Serial.begin(460800);
    pinMode(0, INPUT_PULLUP); // BOOT button for SOS
    
    csi_queue = xQueueCreate(20, sizeof(csi_packet_t));
    
    Serial.println("Connecting to WiFi...");
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);
    
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi Connected! IP Address: ");
    Serial.println(WiFi.localIP());

    // Initialize mDNS
    if (!MDNS.begin("esp32-csi")) {
        Serial.println("Error setting up mDNS responder!");
    }
    
    Serial.printf("Resolving hostname %s.local...\n", dest_host);
    target_ip = MDNS.queryHost(dest_host);
    while (target_ip.toString() == "0.0.0.0") {
        Serial.print(".");
        delay(1000);
        target_ip = MDNS.queryHost(dest_host);
    }
    target_resolved = true;
    Serial.print("\nResolved IP: ");
    Serial.println(target_ip);

    // Enable Promiscuous mode and CSI sniffing
    esp_wifi_set_promiscuous(true);
    wifi_promiscuous_filter_t rx_filter = { .filter_mask = WIFI_PROMIS_FILTER_MASK_ALL };
    esp_wifi_set_promiscuous_filter(&rx_filter);
    esp_wifi_set_channel(6, WIFI_SECOND_CHAN_NONE);
    
    esp_wifi_set_csi(true);
    wifi_csi_config_t csi_config = {
        .lltf_en = true, .htltf_en = true, .stbc_htltf2_en = true,
        .ltf_merge_en = true, .channel_filter_en = true,
        .manu_scale = false, .shift = false,
    };
    esp_wifi_set_csi_config(&csi_config);
    esp_wifi_set_csi_rx_cb(wifi_csi_rx_cb, NULL);
    
    Serial.println("CSI Sniffing Started!");
}

void loop() {
    // 1. Check for SOS Button
    if (digitalRead(0) == LOW && target_resolved) {
        udp.beginPacket(target_ip, dest_port);
        udp.print("SOS_ALERT\n");
        udp.endPacket();
        Serial.println("SOS_ALERT");
        delay(1000); // Debounce
    }
    
    // 2. Process CSI Queue and send UDP packets in batches
    // The ESP32 single antenna drops incoming CSI packets while it is transmitting UDP.
    // By batching 5 frames into 1 UDP packet, we reduce the transmit overhead by 500%, 
    // restoring the full 30Hz frame rate so the Variance mathematical window works perfectly!
    int waiting = uxQueueMessagesWaiting(csi_queue);
    if (waiting >= 5 && target_resolved) {
        udp.beginPacket(target_ip, dest_port);
        
        for (int b = 0; b < waiting; b++) {
            csi_packet_t pkt;
            if (xQueueReceive(csi_queue, &pkt, 0) == pdTRUE) {
                if (pkt.is_sos) {
                    udp.print("SOS_ALERT\n");
                    Serial.println("SOS_ALERT");
                } else {
                    udp.printf("CSI_DATA,%d,%d,%d,", pkt.mac[0], pkt.rssi, pkt.len);
                    Serial.printf("CSI_DATA,%d,%d,%d,", pkt.mac[0], pkt.rssi, pkt.len);
                    for (int i = 0; i < pkt.len; i++) {
                        udp.print((int)pkt.buf[i]);
                        Serial.print((int)pkt.buf[i]);
                        if (i < pkt.len - 1) {
                            udp.print(",");
                            Serial.print(",");
                        }
                    }
                    udp.print("\n");
                    Serial.print("\n");
                }
            }
        }
        udp.endPacket();
    }
}
