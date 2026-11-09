#include <WiFi.h>
#include <WiFiUdp.h>
#include <esp_wifi.h>
#include <ESPmDNS.h>
#include "sentry_common.h"

// ============================================================
// Sentry Phase 8: RX Node (CSI sensor + local siren + SOS button)
//
// Builds on Phase 7. What is new:
//  1. SOS: in idle, HOLD the button 2 s -> SOS goes out
//       - to the Pi (UDP 5000, "SOS_ALERT,<location>")  -> LINE SOS message
//       - straight to every Alert Station (UDP 5005 broadcast,
//         "SOS_ALERT:<location>") so the stations ring even if the Pi,
//         the internet or LINE is down
//     Sent 3 times, 250 ms apart, because UDP can drop a packet.
//  2. Button while the siren rings: any press silences THIS node (as before).
//  3. Short press in idle: status chirp (1 blink = Wi-Fi OK, 3 = no Wi-Fi).
//  4. ACTIVE buzzer support (on/off rhythms instead of PWM tones).
//  5. No more getting stuck at boot: if the Pi's name cannot be resolved,
//     the node keeps retrying in the background and the SOS button still
//     works (SOS falls back to a broadcast that the Pi also hears).
//
// Wiring (ESP32 DevKit, 30/32-pin):
//   GPIO 2  -> 220 ohm -> LED (+, long leg)   LED (-) -> GND
//   GPIO 4  -> active buzzer (+) (or the base resistor of an NPN driver)
//   GPIO 17 -> button -> GND        (internal pull-up, pressed = LOW)
// See docs/Phase8_Alert_Station_SOS_Enclosures.md for full wiring.
// ============================================================

// --- CONFIGURATION ---
// Wi-Fi credentials live in secrets.h (git-ignored). Copy secrets.example.h
// to secrets.h in this folder and fill in your network before uploading.
#if __has_include("secrets.h")
#include "secrets.h"
#else
#warning "secrets.h not found: copy secrets.example.h to secrets.h and set your Wi-Fi"
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#endif
const char* ssid = WIFI_SSID;
const char* password = WIFI_PASSWORD;
const char* dest_host = "OhmPatumwan";   // Hostname of the Raspberry Pi (without .local)
const int dest_port = 5000;              // Pi: CSI data, heartbeats, SOS
String node_location = "Bath Room";      // Change this before uploading to each node!

// --- PINS ---
const int LED_PIN = 2;      // Red 5 mm LED via 220 ohm (GPIO 2 is also the on-board blue LED)
const int BUZZER_PIN = 4;   // ACTIVE buzzer (has its own oscillator: just on/off)
const int BUTTON_PIN = 17;  // Push button between GPIO 17 and GND (Active LOW)

// Most kit active buzzers (and an NPN driver) turn ON with HIGH.
// If yours is a "low level trigger" module that beeps when the pin is LOW, set this to 0.
#define BUZZER_ACTIVE_HIGH 1

// --- TIMING ---
const uint32_t SOS_HOLD_MS = 2000;       // hold this long in idle to send SOS
const uint8_t SOS_SEND_COPIES = 3;
const uint16_t SOS_SEND_GAP_MS = 250;
const uint32_t HEARTBEAT_MS = 5000;
const uint32_t MDNS_RETRY_MS = 10000;
const uint32_t WIFI_BOOT_WAIT_MS = 20000; // then carry on; Wi-Fi keeps reconnecting by itself

const int ALARM_UDP_PORT = 5005;          // fall alerts / silence in, SOS broadcast out
const int ALARM_HEARTBEAT_PORT = 5002;

WiFiUDP udp;         // CSI + SOS out, mode commands in (port 5000)
WiFiUDP alarm_udp;   // fall alerts + remote silence in (port 5005)

IPAddress target_ip;
bool target_resolved = false;

QueueHandle_t csi_queue;

typedef struct {
    uint8_t mac[6];
    int8_t rssi;
    uint16_t len;
    int8_t buf[128]; // signed so UDP carries negative numbers correctly
} csi_packet_t;

enum TxMode { MODE_TX_NODE, MODE_ROUTER };
volatile TxMode currentTxMode = MODE_TX_NODE;

// The Dedicated TX Node MAC address
uint8_t dedicated_tx_mac[6] = {0xD4, 0xE9, 0xF4, 0xA4, 0x40, 0xEC};
// The Router's MAC address (filled in once Wi-Fi connects)
uint8_t router_mac[6];
bool router_mac_known = false;

// --- Alarm / button state ---
enum NodeState { STATE_IDLE, STATE_FALL_ALARM, STATE_SOS_ACTIVE };
NodeState node_state = STATE_IDLE;

sentry::Button button(30, SOS_HOLD_MS);
sentry::PatternPlayer siren;      // drives buzzer AND LED while an alarm/feedback plays
sentry::Retry sos_retry;
bool siren_silent = false;        // true = pattern drives the LED only (no sound)
bool mdns_started = false;
bool swallow_press = false;       // the press that silenced an alarm must not also become an SOS

// (No default arguments: the Arduino IDE's auto-prototypes can choke on them.)
void play_pattern(const sentry::Pattern* p, bool sound) {
    siren.start(p, millis());
    siren_silent = !sound;
}
void play(const sentry::Pattern* p) { play_pattern(p, true); }        // buzzer + LED
void flash(const sentry::Pattern* p) { play_pattern(p, false); }      // LED only

static inline void buzzer(bool on) {
    digitalWrite(BUZZER_PIN, (on == (bool)BUZZER_ACTIVE_HIGH) ? HIGH : LOW);
}
static inline void led(bool on) { digitalWrite(LED_PIN, on ? HIGH : LOW); }

void outputs_off() {
    siren.stop();
    buzzer(false);
    led(false);
}

void start_fall_alarm() {
    node_state = STATE_FALL_ALARM;
    play(&sentry::PATTERN_FALL);
}

void silence_local(const char* why) {
    node_state = STATE_IDLE;
    outputs_off();
    Serial.printf("\n[ALARM] Siren silenced (%s).\n", why);
}

void send_sos_copy() {
    // 1) To the Pi. If its address is unknown, broadcast: the Pi listens on 0.0.0.0:5000.
    IPAddress pi = target_resolved ? target_ip : IPAddress(255, 255, 255, 255);
    udp.beginPacket(pi, dest_port);
    udp.print("SOS_ALERT," + node_location + "\n");
    udp.endPacket();
    // 2) Straight to every Alert Station, so they ring even without the Pi.
    alarm_udp.beginPacket(IPAddress(255, 255, 255, 255), ALARM_UDP_PORT);
    alarm_udp.print("SOS_ALERT:" + node_location);
    alarm_udp.endPacket();
    // 3) USB mode: the Pi's serial reader understands the same line.
    Serial.print("SOS_ALERT," + node_location + "\n");
}

void trigger_sos() {
    Serial.println("\n[SOS] Button held 2 s -> sending SOS!");
    node_state = STATE_SOS_ACTIVE;
    sos_retry.start(SOS_SEND_COPIES, SOS_SEND_GAP_MS, millis());
    play(&sentry::PATTERN_CONFIRM); // 3 chirps, then the SOS rhythm (see loop)
}

void handle_button(uint32_t now) {
    sentry::ButtonEvent ev = button.update(digitalRead(BUTTON_PIN) == LOW, now);
    if (swallow_press) {
        if (!button.isHeld()) swallow_press = false;
        return;
    }
    if (ev == sentry::BTN_NONE) return;

    if (node_state != STATE_IDLE) {
        // A press while ringing = "I'm OK / I heard it": silence this node at once.
        // The rest of that press is ignored, so holding it does not send an SOS.
        if (ev == sentry::BTN_DOWN) {
            silence_local("button");
            swallow_press = true;
        }
        return;
    }
    if (ev == sentry::BTN_LONG_PRESS) {
        trigger_sos();
    } else if (ev == sentry::BTN_SHORT_PRESS) {
        // Status: 1 chirp = Wi-Fi OK. No Wi-Fi = LED flashes 3x (no sound).
        if (WiFi.status() == WL_CONNECTED) play(&sentry::PATTERN_CHIRP);
        else flash(&sentry::PATTERN_CONFIRM);
    }
}

// The CSI Callback (runs in the Wi-Fi task on core 0)
void wifi_csi_rx_cb(void *ctx, wifi_csi_info_t *info) {
    if (!info || !info->buf) return;
    const uint8_t* want = (currentTxMode == MODE_TX_NODE) ? dedicated_tx_mac : router_mac;
    if (currentTxMode == MODE_ROUTER && !router_mac_known) return;
    if (memcmp(info->mac, want, 6) != 0) return;

    csi_packet_t pkt;
    memset(&pkt, 0, sizeof(csi_packet_t));
    memcpy(pkt.mac, info->mac, 6);
    pkt.rssi = info->rx_ctrl.rssi;
    pkt.len = info->len > 128 ? 128 : info->len;
    memcpy(pkt.buf, info->buf, pkt.len);
    xQueueSendFromISR(csi_queue, &pkt, NULL);
}

void try_resolve_pi() {
    IPAddress ip = MDNS.queryHost(dest_host, 500);
    if (!(ip == IPAddress(0, 0, 0, 0))) {
        target_ip = ip;
        target_resolved = true;
        Serial.print("\nResolved Pi IP: ");
        Serial.println(target_ip);
    }
}

void setup() {
    Serial.begin(460800);

    pinMode(LED_PIN, OUTPUT);
    pinMode(BUZZER_PIN, OUTPUT);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    outputs_off();

    csi_queue = xQueueCreate(30, sizeof(csi_packet_t));

    Serial.println("Connecting to WiFi...");
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(ssid, password);
    uint32_t t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < WIFI_BOOT_WAIT_MS) {
        led(((millis() / 250) % 2) == 0); // fast blink = connecting
        delay(50);
    }
    led(false);
    if (WiFi.status() == WL_CONNECTED) {
        Serial.print("\nWiFi Connected! IP Address: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("\nWiFi not connected yet - will keep trying in the background.");
    }

    udp.begin(dest_port);
    alarm_udp.begin(ALARM_UDP_PORT);
    Serial.println("UDP 5000: CSI out / commands in.  UDP 5005: alarms in.");
    Serial.println("Button GPIO 17: hold 2 s = SOS, press while ringing = silence.");

    // Promiscuous mode + CSI (works alongside STA mode)
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

    if (WiFi.status() == WL_CONNECTED) play(&sentry::PATTERN_BOOT);
    Serial.println("Phase 8 RX Node started.");
}

void loop() {
    const uint32_t now = millis();
    const bool wifi_ok = (WiFi.status() == WL_CONNECTED);

    // 0. Learn the router MAC once connected (needed for Router TX mode)
    if (wifi_ok && !router_mac_known) {
        uint8_t* bssid = WiFi.BSSID();
        if (bssid) {
            memcpy(router_mac, bssid, 6);
            router_mac_known = true;
            Serial.printf("Detected Router MAC: %02X:%02X:%02X:%02X:%02X:%02X\n",
                          router_mac[0], router_mac[1], router_mac[2],
                          router_mac[3], router_mac[4], router_mac[5]);
        }
    }

    // 1. Find the Pi in the background (never blocks the button for long)
    if (wifi_ok && !mdns_started) {
        mdns_started = MDNS.begin("esp32-csi");  // lets the Pi find us as esp32-csi.local
        if (!mdns_started) Serial.println("Error setting up mDNS responder!");
    }
    static uint32_t last_mdns_try = 0;
    if (wifi_ok && mdns_started && !target_resolved && (last_mdns_try == 0 || now - last_mdns_try > MDNS_RETRY_MS)) {
        last_mdns_try = now;
        try_resolve_pi();
    }

    // 2. Button first: SOS and silence must always respond
    handle_button(now);

    // 3. SOS copies (non-blocking)
    if (sos_retry.due(now)) send_sos_copy();

    // 4. Commands from the Pi (UDP 5000)
    int packetSize = udp.parsePacket();
    if (packetSize) {
        char incomingPacket[256];
        int len = udp.read(incomingPacket, sizeof(incomingPacket) - 1);
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

    // 5. Fall alerts & remote silence (UDP 5005)
    int alarmPacketSize = alarm_udp.parsePacket();
    if (alarmPacketSize) {
        char incomingAlarm[256];
        char loc[64];
        int len = alarm_udp.read(incomingAlarm, sizeof(incomingAlarm) - 1);
        if (len > 0) {
            incomingAlarm[len] = 0;
            sentry::AlarmKind kind = sentry::parseAlarm(incomingAlarm, loc, sizeof(loc));
            if (kind == sentry::MSG_FALL && node_state == STATE_IDLE) {
                Serial.println("\n[ALARM] Fall Alert Received! Siren on until silenced.");
                start_fall_alarm();
            } else if (kind == sentry::MSG_SILENCE && node_state != STATE_IDLE) {
                silence_local("remote: LINE / dashboard");
            }
            // SOS_ALERT is for the Alert Stations; RX nodes ignore it.
        }
    }

    // 6. Drive buzzer + LED
    if (node_state == STATE_SOS_ACTIVE && !siren.active()) {
        play(&sentry::PATTERN_SOS); // after the confirm chirps
    }
    if (siren.active()) {
        bool on = siren.output(now);
        led(on);
        buzzer(on && !siren_silent);
    } else if (button.isCharging() && !swallow_press) {
        led(true);  // holding: LED on solid -> "keep holding for SOS"
        buzzer(false);
    } else {
        led(false);
        buzzer(false);
    }

    // 7. Heartbeats to the Pi
    static uint32_t last_heartbeat = 0;
    if (target_resolved && wifi_ok && now - last_heartbeat > HEARTBEAT_MS) {
        udp.beginPacket(target_ip, dest_port);
        udp.print("HEARTBEAT\n");
        udp.endPacket();

        udp.beginPacket(target_ip, ALARM_HEARTBEAT_PORT);
        udp.print("ALARM_READY:" + WiFi.localIP().toString() + "\n");
        udp.endPacket();
        last_heartbeat = now;
    }

    // 8. CSI queue -> Pi, one frame per packet
    csi_packet_t pkt;
    while (target_resolved && xQueueReceive(csi_queue, &pkt, 0) == pdTRUE) {
        // ~80 byte header + 128 values x 5 chars = ~720 bytes, so 1024 always fits.
        char txBuf[1024];
        int pos = snprintf(txBuf, sizeof(txBuf), "CSI_DATA,%s,%d,%d,%d", node_location.c_str(), pkt.mac[0], pkt.rssi, pkt.len);
        bool overflow = (pos < 0 || pos >= (int)sizeof(txBuf) - 2);
        for (int i = 0; i < pkt.len && !overflow; i++) {
            int n = snprintf(txBuf + pos, sizeof(txBuf) - pos, ",%d", (int)pkt.buf[i]);
            if (n < 0 || pos + n >= (int)sizeof(txBuf) - 2) { overflow = true; break; }
            pos += n;
        }
        if (overflow) continue; // never send a truncated frame
        txBuf[pos++] = '\n';
        txBuf[pos] = '\0';

        udp.beginPacket(target_ip, dest_port);
        udp.write((const uint8_t*)txBuf, pos);
        udp.endPacket();

        // Mirror to Serial for USB mode (quiet while an alarm is on)
        if (node_state == STATE_IDLE) Serial.write(txBuf, pos);

        handle_button(millis()); // stay responsive during CSI bursts
    }
}
