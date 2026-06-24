#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/event_groups.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "esp_mac.h"
#include "driver/uart.h"
#include "driver/gpio.h"
#include "lwip/sockets.h"
#include "lwip/err.h"

static const char *TAG = "CSI_UDP_RX";

// --- CONFIGURATION ---
#define WIFI_SSID      "BUNDAOBUNTAI"
#define WIFI_PASS      "ohm12345"
#define DEST_IP_ADDR   "192.168.1.8"
#define DEST_PORT      5000

// Wi-Fi Event Group
static EventGroupHandle_t s_wifi_event_group;
#define WIFI_CONNECTED_BIT BIT0

// FreeRTOS Queue for thread-safe CSI transmission
static QueueHandle_t csi_queue;

typedef struct {
    uint8_t mac[6];
    int8_t rssi;
    uint16_t len;
    uint8_t buf[128]; // Max CSI length for 20MHz
    bool is_sos;
} csi_packet_t;

// Wi-Fi Event Handler
static void event_handler(void* arg, esp_event_base_t event_base,
                                int32_t event_id, void* event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        esp_wifi_connect();
        ESP_LOGI(TAG, "Retry to connect to the AP");
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
        ESP_LOGI(TAG, "Got IP:" IPSTR, IP2STR(&event->ip_info.ip));
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

// CSI Callback (Runs in High-Priority Wi-Fi Task)
static void wifi_csi_rx_cb(void *ctx, wifi_csi_info_t *info) {
    if (!info || !info->buf) {
        return;
    }
    
    // Check if it matches our specific TX Node MAC (d4:e9:f4:a4:40:ec)
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
        
        // Push to queue safely from ISR
        if (xQueueSendFromISR(csi_queue, &pkt, NULL) != pdTRUE) {
            // Queue full, drop packet to prevent crash
        }
    }
}

// UDP Sender Task
void udp_sender_task(void *pvParameters) {
    char payload_str[1024];
    
    while (1) {
        // Wait for Wi-Fi to connect
        xEventGroupWaitBits(s_wifi_event_group, WIFI_CONNECTED_BIT, pdFALSE, pdTRUE, portMAX_DELAY);
        
        int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
        if (sock < 0) {
            ESP_LOGE(TAG, "Unable to create socket: errno %d", errno);
            vTaskDelay(1000 / portTICK_PERIOD_MS);
            continue;
        }

        struct sockaddr_in dest_addr;
        dest_addr.sin_addr.s_addr = inet_addr(DEST_IP_ADDR);
        dest_addr.sin_family = AF_INET;
        dest_addr.sin_port = htons(DEST_PORT);

        ESP_LOGI(TAG, "Socket created, sending to %s:%d", DEST_IP_ADDR, DEST_PORT);

        csi_packet_t pkt;
        while (1) {
            if (xQueueReceive(csi_queue, &pkt, portMAX_DELAY)) {
                if (pkt.is_sos) {
                    strcpy(payload_str, "SOS_ALERT\n");
                } else {
                    int offset = sprintf(payload_str, "CSI_DATA,%d,%d,%d,", pkt.mac[0], pkt.rssi, pkt.len);
                    for (int i = 0; i < pkt.len; i++) {
                        offset += sprintf(payload_str + offset, "%d", pkt.buf[i]);
                        if (i < pkt.len - 1) {
                            offset += sprintf(payload_str + offset, ",");
                        }
                    }
                    sprintf(payload_str + offset, "\n");
                }
                
                int err = sendto(sock, payload_str, strlen(payload_str), 0, (struct sockaddr *)&dest_addr, sizeof(dest_addr));
                if (err < 0) {
                    ESP_LOGE(TAG, "Error occurred during sending: errno %d", errno);
                    break; // Break the inner loop to reconnect the socket
                }
            }
        }
        
        if (sock != -1) {
            ESP_LOGE(TAG, "Shutting down socket and restarting...");
            shutdown(sock, 0);
            close(sock);
        }
    }
}

void wifi_init_rx() {
    s_wifi_event_group = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    cfg.csi_enable = 1; // Enable CSI
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    esp_event_handler_instance_t instance_any_id;
    esp_event_handler_instance_t instance_got_ip;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
                                                        ESP_EVENT_ANY_ID,
                                                        &event_handler,
                                                        NULL,
                                                        &instance_any_id));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,
                                                        IP_EVENT_STA_GOT_IP,
                                                        &event_handler,
                                                        NULL,
                                                        &instance_got_ip));

    wifi_config_t wifi_config = {
        .sta = {
            .ssid = WIFI_SSID,
            .password = WIFI_PASS,
        },
    };
    
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));

    wifi_promiscuous_filter_t rx_filter = {
        .filter_mask = WIFI_PROMIS_FILTER_MASK_ALL
    };
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_filter(&rx_filter));
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
    ESP_ERROR_CHECK(nvs_flash_init());
    
    // We keep UART at 460800 just in case we want to view logs via USB debugging
    uart_set_baudrate(UART_NUM_0, 460800);
    
    gpio_set_direction(0, GPIO_MODE_INPUT);
    gpio_set_pull_mode(0, GPIO_PULLUP_ONLY);
    
    ESP_LOGI(TAG, "Initializing CSI UDP Rx Node");
    esp_log_level_set("wifi", ESP_LOG_WARN);
    
    // Create queue to hold 20 CSI packets
    csi_queue = xQueueCreate(20, sizeof(csi_packet_t));
    
    wifi_init_rx();
    
    // Start the UDP Sender Task
    xTaskCreate(udp_sender_task, "udp_sender_task", 4096, NULL, 5, NULL);
    
    while(1) {
        if (gpio_get_level(0) == 0) {
            // Local RX node button pressed! Send SOS via UDP
            csi_packet_t sos_pkt;
            memset(&sos_pkt, 0, sizeof(csi_packet_t));
            sos_pkt.is_sos = true;
            xQueueSend(csi_queue, &sos_pkt, portMAX_DELAY);
            
            vTaskDelay(1000 / portTICK_PERIOD_MS); 
        } else {
            vTaskDelay(100 / portTICK_PERIOD_MS);
        }
    }
}
