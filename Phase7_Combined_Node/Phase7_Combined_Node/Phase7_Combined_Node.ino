#include <WiFi.h>
#include <WiFiUdp.h>
#include <esp_wifi.h>
#include <ESPmDNS.h>

// ============================================================
// Sentry Phase 7: Combined Node with Remote & Local Silence
//
// Features:
// 1. Full Wi-Fi CSI Sniffing & 30Hz Real-Time Transmission
// 2. Non-Blocking Alarm Siren (Buzzer GPIO 4, Red LED GPIO 2)
// 3. Physical Silence Button on GPIO 17 (Push to GND)
// 4. Remote Silence Command from LINE / Web Dashboard (UDP 5005)
// ============================================================

// --- CONFIGURATION ---
const char* ssid = "BUNDAOBUNTAI";
const char* password = "ohm12345";
const char* dest_host = "OhmPatumwan"; // Hostname of the Raspberry Pi
const int dest_port = 5000;
String node_location = "Bath Room"; // Change this before uploading to each node!

// --- ALARM CONFIGURATION ---
const int LED_PIN = 2;
const int BUZZER_PIN = 4;
const int BUTTON_PIN = 17; // Push button between GPIO 17 and GND (Active LOW)
const int BUZZER_FREQ = 2000;
const int BUZZER_RES_BITS = 8;
const int FREQS[] = { 1000, 1500, 2000, 2500 }; // 4 tones for the siren

const int ALARM_UDP_PORT = 5005;

WiFiUDP udp;         // For sending CSI and receiving commands on port 5000
WiFiUDP alarm_udp;   // For receiving fall alerts and remote silence commands on port 5005

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

// Alarm State Variables (Non-blocking)
bool alarm_active = false;
unsigned long last_tone_change = 0;
int current_tone_index = 0;

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
    
    // Setup Alarm Pins (ESP32 Arduino Core 3.x API)
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);
    pinMode(BUTTON_PIN, INPUT_PULLUP); // Local hardware button to stop alarm
    ledcAttach(BUZZER_PIN, BUZZER_FREQ, BUZZER_RES_BITS);
    ledcWriteTone(BUZZER_PIN, 0); // Ensure buzzer is off
    
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

    // Start UDP Listeners
    udp.begin(5000);
    alarm_udp.begin(ALARM_UDP_PORT);
    Serial.println("UDP CSI Command Listener started on port 5000.");
    Serial.println("UDP Alarm Trigger & Remote Silence Listener started on port 5005.");
    Serial.println("Alarm Reset Button active on Pin 17.");

    // Enable Promiscuous mode and CSI sniffing (Works alongside STA mode!)
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
    
    Serial.println("Phase 7 Combined Node Started! CSI Sniffing & Remote Silence Active.");
}

void loop() {
    // 1. Process Incoming Commands from Pi (UDP 5000)
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

    // 2. Process Incoming Alarm Triggers & Remote Silence (UDP 5005)
    int alarmPacketSize = alarm_udp.parsePacket();
    if (alarmPacketSize) {
        char incomingAlarm[255];
        int len = alarm_udp.read(incomingAlarm, 255);
        if (len > 0) {
            incomingAlarm[len] = 0;
            String msg = String(incomingAlarm);
            msg.trim();
            if (msg.startsWith("FALL_ALERT") || msg.startsWith("ALARM_TRIGGER")) {
                Serial.println("\n[ALARM] Fall Alert Received! Triggering Continuous Siren!");
                alarm_active = true;
                last_tone_change = millis();
                current_tone_index = 0;
                ledcWriteTone(BUZZER_PIN, FREQS[0]);
                digitalWrite(LED_PIN, HIGH);
            } else if (msg.startsWith("FALL_SILENCE") || msg.startsWith("ALARM_STOP") || msg.startsWith("SILENCE")) {
                Serial.println("\n[ALARM] Remote Silence Command Received (via LINE / Dashboard)! Siren silenced.");
                alarm_active = false;
                ledcWriteTone(BUZZER_PIN, 0); // Stop buzzer
                digitalWrite(LED_PIN, LOW);   // Turn off LED
            }
        }
    }

    // 3. Process Non-Blocking Alarm Siren (Runs continuously until Button Pin 17 pressed or Remote Silence received)
    if (alarm_active) {
        // Check if physical button on GPIO 17 is pressed (Active LOW)
        if (digitalRead(BUTTON_PIN) == LOW) {
            alarm_active = false;
            ledcWriteTone(BUZZER_PIN, 0); // Stop buzzer
            digitalWrite(LED_PIN, LOW);   // Turn off LED
            Serial.println("\n[ALARM] Physical button (Pin 17) pressed! Siren silenced.");
            delay(250); // Simple debounce
        } else {
            unsigned long now = millis();
            if (now - last_tone_change > 100) {
                last_tone_change = now;
                current_tone_index = (current_tone_index + 1) % 4;
                
                // Continuous siren tone + alternating blink
                ledcWriteTone(BUZZER_PIN, FREQS[current_tone_index]);
                digitalWrite(LED_PIN, (current_tone_index % 2 == 0) ? HIGH : LOW);
            }
        }
    }

    // 4. Send Heartbeats to Pi
    static unsigned long last_heartbeat = 0;
    if (millis() - last_heartbeat > 5000 && target_resolved) {
        // Heartbeat for CSI Dashboard
        udp.beginPacket(target_ip, dest_port);
        udp.print("HEARTBEAT\n");
        udp.endPacket();
        
        // Heartbeat for Alarm System (Port 5002)
        udp.beginPacket(target_ip, 5002);
        udp.print("ALARM_READY:" + WiFi.localIP().toString() + "\n");
        udp.endPacket();
        
        last_heartbeat = millis();
    }

    // 5. Process CSI Queue - send each packet IMMEDIATELY (no batching!)
    csi_packet_t pkt;
    while (xQueueReceive(csi_queue, &pkt, 0) == pdTRUE && target_resolved) {
        // Build the string into a buffer first, then send in one shot
        char txBuf[512];
        int pos = snprintf(txBuf, sizeof(txBuf), "CSI_DATA,%s,%d,%d,%d", node_location.c_str(), pkt.mac[0], pkt.rssi, pkt.len);
        for (int i = 0; i < pkt.len && pos < (int)sizeof(txBuf) - 5; i++) {
            pos += snprintf(txBuf + pos, sizeof(txBuf) - pos, ",%d", pkt.buf[i]);
        }
        txBuf[pos++] = '\n';
        txBuf[pos] = '\0';

        udp.beginPacket(target_ip, dest_port);
        udp.write((const uint8_t*)txBuf, pos);
        udp.endPacket();

        // Also mirror to Serial for USB mode (single write, non-blocking)
        // Only print CSI if alarm isn't actively going off, to avoid serial flood during alarm prints
        if (!alarm_active) {
            Serial.write(txBuf, pos);
        }
    }
}
