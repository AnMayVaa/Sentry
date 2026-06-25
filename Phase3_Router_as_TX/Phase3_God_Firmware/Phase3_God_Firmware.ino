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

// Mode Variables
enum TxMode {
    MODE_TX_NODE,
    MODE_ROUTER
};
TxMode currentTxMode = MODE_TX_NODE;

// The Dedicated TX Node MAC address (used in Phase 2)
uint8_t dedicated_tx_mac[6] = {0xD4, 0xE9, 0xF4, 0xA4, 0x40, 0xEC};

// The Router's MAC address will be populated automatically when connected
uint8_t router_mac[6];

// The CSI Callback (Runs in the background Wi-Fi thread on Core 0)
void wifi_csi_rx_cb(void *ctx, wifi_csi_info_t *info) {
    if (!info || !info->buf) return;
    
    bool is_our_tx = false;
    
    if (currentTxMode == MODE_TX_NODE) {
        // Filter for Dedicated TX Node
        is_our_tx = (info->mac[0] == dedicated_tx_mac[0] && info->mac[1] == dedicated_tx_mac[1] && 
                     info->mac[2] == dedicated_tx_mac[2] && info->mac[3] == dedicated_tx_mac[3] && 
                     info->mac[4] == dedicated_tx_mac[4] && info->mac[5] == dedicated_tx_mac[5]);
    } else if (currentTxMode == MODE_ROUTER) {
        // Filter for Router (Gateway) MAC
        is_our_tx = (info->mac[0] == router_mac[0] && info->mac[1] == router_mac[1] && 
                     info->mac[2] == router_mac[2] && info->mac[3] == router_mac[3] && 
                     info->mac[4] == router_mac[4] && info->mac[5] == router_mac[5]);
    }

    if (is_our_tx) {
        csi_packet_t pkt;
        memset(&pkt, 0, sizeof(csi_packet_t));
        
        pkt.is_sos = false;
        memcpy(pkt.mac, info->mac, 6);
        pkt.rssi = info->rx_ctrl.rssi;
        pkt.len = info->len > 128 ? 128 : info->len;
        memcpy(pkt.buf, info->buf, pkt.len);
        
        // Push safely to queue
        xQueueSendFromISR(csi_queue, &pkt, NULL);
    }
}

void setup() {
    Serial.begin(460800);
    pinMode(0, INPUT_PULLUP); // BOOT button for SOS
    
    csi_queue = xQueueCreate(30, sizeof(csi_packet_t));
    
    Serial.println("Connecting to WiFi...");
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);
    
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi Connected! IP Address: ");
    Serial.println(WiFi.localIP());

    // Automatically detect and store the Router's MAC Address!
    uint8_t* bssid = WiFi.BSSID();
    memcpy(router_mac, bssid, 6);
    Serial.printf("Detected Router MAC: %02X:%02X:%02X:%02X:%02X:%02X\n",
                  router_mac[0], router_mac[1], router_mac[2],
                  router_mac[3], router_mac[4], router_mac[5]);

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

    // Start UDP Server to listen for commands from Pi
    udp.begin(5000);
    Serial.println("UDP Listener started on port 5000.");

    // Enable Promiscuous mode and CSI sniffing (Works alongside STA mode!)
    esp_wifi_set_promiscuous(true);
    wifi_promiscuous_filter_t rx_filter = { .filter_mask = WIFI_PROMIS_FILTER_MASK_ALL };
    esp_wifi_set_promiscuous_filter(&rx_filter);
    // Note: We don't force channel here. It stays on the Router's channel.
    
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
    // 1. Process Incoming Commands from Pi (UDP)
    int packetSize = udp.parsePacket();
    if (packetSize) {
        char incomingPacket[255];
        int len = udp.read(incomingPacket, 255);
        if (len > 0) {
            incomingPacket[len] = 0;
            String cmd = String(incomingPacket);
            cmd.trim();
            if (cmd == "MODE_ROUTER") {
                currentTxMode = MODE_ROUTER;
                Serial.println("Switched to Router TX Mode.");
            } else if (cmd == "MODE_TX_NODE") {
                currentTxMode = MODE_TX_NODE;
                Serial.println("Switched to Dedicated TX Mode.");
            }
        }
    }

    // 2. Process Incoming Commands from Pi (Serial USB)
    if (Serial.available()) {
        String cmd = Serial.readStringUntil('\n');
        cmd.trim();
        if (cmd == "MODE_ROUTER") {
            currentTxMode = MODE_ROUTER;
            Serial.println("Switched to Router TX Mode.");
        } else if (cmd == "MODE_TX_NODE") {
            currentTxMode = MODE_TX_NODE;
            Serial.println("Switched to Dedicated TX Mode.");
        }
    }
    
    // 2.5 Send Heartbeat to Pi so it learns our IP address!
    static unsigned long last_heartbeat = 0;
    if (millis() - last_heartbeat > 1000 && target_resolved) {
        udp.beginPacket(target_ip, dest_port);
        udp.print("HEARTBEAT\n");
        udp.endPacket();
        last_heartbeat = millis();
    }

    // 3. Check for SOS Button
    // if (digitalRead(0) == LOW && target_resolved) {
    //     udp.beginPacket(target_ip, dest_port);
    //     udp.print("SOS_ALERT\n");
    //     udp.endPacket();
    //     Serial.println("SOS_ALERT");
    //     delay(1000); // Debounce
    // }
    
    // 4. Process CSI Queue - send each packet IMMEDIATELY (no batching!)
    csi_packet_t pkt;
    while (xQueueReceive(csi_queue, &pkt, 0) == pdTRUE && target_resolved) {
        // Build the string into a buffer first, then send in one shot
        char txBuf[512];
        int pos = snprintf(txBuf, sizeof(txBuf), "CSI_DATA,%d,%d,%d", pkt.mac[0], pkt.rssi, pkt.len);
        for (int i = 0; i < pkt.len && pos < (int)sizeof(txBuf) - 5; i++) {
            pos += snprintf(txBuf + pos, sizeof(txBuf) - pos, ",%d", pkt.buf[i]);
        }
        txBuf[pos++] = '\n';
        txBuf[pos] = '\0';

        udp.beginPacket(target_ip, dest_port);
        udp.write((const uint8_t*)txBuf, pos);
        udp.endPacket();
    }
}
