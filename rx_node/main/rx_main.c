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
#include "driver/uart.h"
#include "driver/gpio.h"
#include "esp_now.h"

static const char *TAG = "CSI_RX";

// The Magic Bytes we look for in the payload to ensure it's our Tx

static void wifi_csi_rx_cb(void *ctx, wifi_csi_info_t *info) {
    if (!info || !info->buf) {
        return;
    }
    
    // Check if it matches our specific TX Node MAC (d4:e9:f4:a4:40:ec)
    bool is_our_tx = (info->mac[0] == 0xD4 && info->mac[1] == 0xE9 && info->mac[2] == 0xF4 &&
                      info->mac[3] == 0xA4 && info->mac[4] == 0x40 && info->mac[5] == 0xEC);

    if (is_our_tx) {
        // --- PHASE 4: SOS DETECTION ---
        // The normal ESP-NOW packet length is around 50-60 bytes (header + 16 byte payload).
        // The SOS packet payload is 150 bytes, so sig_len will be > 100.
        if (info->rx_ctrl.sig_len > 100) {
            printf("SOS_ALERT\n");
            return; // Don't print CSI for SOS packets to keep graphs clean
        }

        // A standard 20MHz CSI buffer has 128 bytes
        printf("CSI_DATA,%d,%d,%d,", info->mac[0], info->rx_ctrl.rssi, info->len);
        for (int i = 0; i < info->len; i++) {
            printf("%d", info->buf[i]);
            if (i < info->len - 1) {
                printf(",");
            }
        }
        printf("\n");
    } else {
        // It's not our packet. Let's print the MAC occasionally to see what's actually arriving!
        static int count = 0;
        if (count++ % 20 == 0) {
            printf("DEBUG_MAC: %02X:%02X:%02X:%02X:%02X:%02X (rssi: %d, len: %d)\n", 
                   info->mac[0], info->mac[1], info->mac[2], 
                   info->mac[3], info->mac[4], info->mac[5], 
                   info->rx_ctrl.rssi, info->len);
        }
    }
}

void wifi_init_rx() {
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    cfg.csi_enable = 1; // Enable CSI
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));

    // By default, Promiscuous mode often ignores Management frames!
    // We MUST tell it to listen to everything (WIFI_PROMIS_FILTER_MASK_ALL) 
    // so it doesn't throw away our custom Action Frames.
    wifi_promiscuous_filter_t rx_filter = {
        .filter_mask = WIFI_PROMIS_FILTER_MASK_ALL
    };
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_filter(&rx_filter));

    // Must be on the exact same channel as Tx
    ESP_ERROR_CHECK(esp_wifi_set_channel(6, WIFI_SECOND_CHAN_NONE));

    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
    
    wifi_csi_config_t csi_config = {
        .lltf_en           = true,
        .htltf_en          = true,
        .stbc_htltf2_en    = true,
        .ltf_merge_en      = true,
        .channel_filter_en = true,
        .manu_scale        = false,
        .shift             = false,
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_config));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(wifi_csi_rx_cb, NULL));

    ESP_LOGI(TAG, "WiFi Initialized, CSI enabled, Promiscuous mode on Channel 6");
}

void app_main(void) {
    // Force baud rate to 460800 so the Python app can keep up and to prevent watchdog timeouts
    uart_set_baudrate(UART_NUM_0, 460800);
    
    // Configure local BOOT Button (GPIO 0) as input with internal pull-up
    gpio_set_direction(0, GPIO_MODE_INPUT);
    gpio_set_pull_mode(0, GPIO_PULLUP_ONLY);
    
    ESP_LOGI(TAG, "Initializing CSI Rx Node");
    // Disable logging from WiFi stack to not pollute CSV output over serial
    esp_log_level_set("wifi", ESP_LOG_WARN);
    wifi_init_rx();
    
    while(1) {
        if (gpio_get_level(0) == 0) {
            // Local RX node button pressed!
            printf("SOS_ALERT\n");
            vTaskDelay(1000 / portTICK_PERIOD_MS); // Prevent spam
        } else {
            vTaskDelay(100 / portTICK_PERIOD_MS);
        }
    }
}
