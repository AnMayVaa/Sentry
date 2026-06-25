#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "esp_mac.h"
#include "esp_now.h"
#include "driver/gpio.h"

#define BOOT_BUTTON_GPIO 0

static const char *TAG = "CSI_TX";

// Configured MAC address of the receiver
static const uint8_t rx_mac[6] = {0xD4, 0xE9, 0xF4, 0xE2, 0x5F, 0x7C};

void wifi_init_tx() {
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    cfg.ampdu_tx_enable = 0; // Disable AMPDU to allow fixed rates
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());

    // Reduce WiFi transmit power to 10 dBm (40 * 0.25) to prevent Brownout Detector
    ESP_ERROR_CHECK(esp_wifi_set_max_tx_power(40));

    // Set a fixed channel (e.g., 6)
    ESP_ERROR_CHECK(esp_wifi_set_channel(6, WIFI_SECOND_CHAN_NONE));

    // Initialize ESP-NOW
    ESP_ERROR_CHECK(esp_now_init());

    // Force ESP-NOW to use an OFDM rate (54Mbps) because CSI requires OFDM subcarriers!
    ESP_ERROR_CHECK(esp_wifi_config_espnow_rate(WIFI_IF_STA, WIFI_PHY_RATE_54M));

    // Register the Receiver as an ESP-NOW peer
    esp_now_peer_info_t peerInfo = {};
    memcpy(peerInfo.peer_addr, rx_mac, 6);
    peerInfo.channel = 6;
    peerInfo.ifidx = WIFI_IF_STA;
    peerInfo.encrypt = false;
    ESP_ERROR_CHECK(esp_now_add_peer(&peerInfo));

    ESP_LOGI(TAG, "ESP-NOW Initialized and running on Channel 6");
}

void tx_task(void *pvParameter) {
    ESP_LOGI(TAG, "Starting ESP-NOW transmission loop...");
    
    // Normal packet payload (16 bytes)
    uint8_t normal_payload[] = "CSI_MAGIC_12345!";
    
    // Massive packet payload for SOS (150 bytes)
    uint8_t sos_payload[150];
    memset(sos_payload, 0x55, sizeof(sos_payload));
    
    while(1) {
        if (gpio_get_level(BOOT_BUTTON_GPIO) == 0) {
            // Button is pressed! Send MASSIVE packet.
            esp_now_send(rx_mac, sos_payload, sizeof(sos_payload));
            vTaskDelay(100 / portTICK_PERIOD_MS); // Don't spam SOS too fast
        } else {
            // Normal operation. Send standard CSI packets.
            esp_now_send(rx_mac, normal_payload, sizeof(normal_payload));
            vTaskDelay(33 / portTICK_PERIOD_MS); // 30 Hz transmission
        }
    }
}

void app_main(void) {
    ESP_LOGI(TAG, "Initializing CSI Tx Node (ESP-NOW)");
    
    // Configure BOOT Button (GPIO 0) as input with internal pull-up
    gpio_set_direction(BOOT_BUTTON_GPIO, GPIO_MODE_INPUT);
    gpio_set_pull_mode(BOOT_BUTTON_GPIO, GPIO_PULLUP_ONLY);

    wifi_init_tx();
    
    // Start transmission task
    xTaskCreate(&tx_task, "tx_task", 4096, NULL, 5, NULL);
}
