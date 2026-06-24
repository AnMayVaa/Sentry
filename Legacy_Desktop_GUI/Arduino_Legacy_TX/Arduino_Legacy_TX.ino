#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

// Configured MAC address of the receiver
uint8_t rx_mac[] = {0xD4, 0xE9, 0xF4, 0xE2, 0x5F, 0x7C};

// Payloads
uint8_t normal_payload[] = "CSI_MAGIC_12345!";
uint8_t sos_payload[150];

#define BOOT_BUTTON_GPIO 0

void setup() {
    Serial.begin(115200);
    pinMode(BOOT_BUTTON_GPIO, INPUT_PULLUP);
    
    // Fill SOS payload with dummy bytes
    memset(sos_payload, 0x55, sizeof(sos_payload));

    // Initialize WiFi in Station mode
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    
    // Reduce WiFi transmit power to prevent Brownout Detector
    esp_wifi_set_max_tx_power(40); // 10 dBm
    
    // Set fixed channel to match RX
    esp_wifi_set_channel(6, WIFI_SECOND_CHAN_NONE);

    // Initialize ESP-NOW
    if (esp_now_init() != ESP_OK) {
        Serial.println("Error initializing ESP-NOW");
        return;
    }

    // Force ESP-NOW to use an OFDM rate (54Mbps) because CSI requires OFDM subcarriers!
    esp_wifi_config_espnow_rate(WIFI_IF_STA, WIFI_PHY_RATE_54M);

    // Register peer
    esp_now_peer_info_t peerInfo = {};
    memcpy(peerInfo.peer_addr, rx_mac, 6);
    peerInfo.channel = 6;  
    peerInfo.encrypt = false;
    
    if (esp_now_add_peer(&peerInfo) != ESP_OK){
        Serial.println("Failed to add peer");
        return;
    }
    
    Serial.println("ESP-NOW Initialized and running on Channel 6");
}

void loop() {
    if (digitalRead(BOOT_BUTTON_GPIO) == LOW) {
        // Button is pressed! Send MASSIVE packet.
        esp_now_send(rx_mac, sos_payload, sizeof(sos_payload));
        delay(100); // Don't spam SOS too fast
    } else {
        // Normal operation. Send standard CSI packets.
        esp_now_send(rx_mac, normal_payload, sizeof(normal_payload));
        delay(33); // ~30 Hz transmission
    }
}
