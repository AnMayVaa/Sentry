#include <WiFi.h>
#include <WiFiUdp.h>
#include "sentry_common.h"

// ============================================================
// Sentry Phase 8: Alert Station (caregiver's receiver)
//
// ESP32 + active buzzer + red LED (under a light dome) + button.
// Put it where the caregiver is: kitchen, bedroom, nurse desk.
//
// It listens on UDP 5005 (broadcast, no pairing, no IP to type in):
//   FALL_ALERT:<room>  (from the Pi)            -> fast beeping + fast blink
//   SOS_ALERT:<room>   (from an RX node or Pi)  -> Morse "SOS" rhythm
//   FALL_SILENCE       (LINE button / dashboard) -> stop
// Every station on the Wi-Fi rings at once. Add as many as you like.
//
// Button:
//   press while ringing   -> silence THIS station
//   hold 2 s while idle   -> self-test (long beep) - good for demo day
//   short press while idle-> status chirp (1 blink = Wi-Fi OK, 3 = no Wi-Fi)
// Idle LED: tiny blink every 3 s = connected; double blink every 1 s = no Wi-Fi.
//
// It also sends "ALARM_READY:<ip>" to UDP 5002 every 5 s so the Pi knows it is alive.
//
// Wiring (ESP32 DevKit, 30/32-pin) - same pins as the RX node:
//   GPIO 2  -> 220 ohm -> LED (+, long leg)   LED (-) -> GND
//   GPIO 4  -> active buzzer (+) (or the base resistor of an NPN driver)
//   GPIO 17 -> button -> GND        (internal pull-up, pressed = LOW)
// ============================================================

#if __has_include("secrets.h")
#include "secrets.h"
#else
#warning "secrets.h not found: copy secrets.example.h to secrets.h and set your Wi-Fi"
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#endif

const char* station_name = "Caregiver Station";  // shows in Serial logs only

// --- PINS ---
const int LED_PIN = 2;
const int BUZZER_PIN = 4;
const int BUTTON_PIN = 17;
// 1 = buzzer ON when the pin is HIGH (bare active buzzer / NPN driver / most modules).
// 0 = "low level trigger" module.
#define BUZZER_ACTIVE_HIGH 1

const int ALARM_UDP_PORT = 5005;
const int HEARTBEAT_UDP_PORT = 5002;
const uint32_t HEARTBEAT_MS = 5000;
const uint32_t REPEAT_HOLDOFF_MS = 8000;  // ignore copies of an alert you just silenced

WiFiUDP udpRx;
WiFiUDP udpTx;

enum StationState { ST_IDLE, ST_RINGING };
StationState state = ST_IDLE;
sentry::AlarmKind ringing_kind = sentry::MSG_NONE;
char ringing_loc[64] = "";

sentry::Button button(30, 2000);
sentry::PatternPlayer siren;
sentry::RepeatFilter repeats(REPEAT_HOLDOFF_MS);
bool siren_silent = false;
bool swallow_press = false;   // the press that silenced an alarm must not also start a self-test

static inline void buzzer(bool on) {
    digitalWrite(BUZZER_PIN, (on == (bool)BUZZER_ACTIVE_HIGH) ? HIGH : LOW);
}
static inline void led(bool on) { digitalWrite(LED_PIN, on ? HIGH : LOW); }

// (No default arguments: the Arduino IDE's auto-prototypes can choke on them.)
void play_pattern(const sentry::Pattern* p, bool sound) {
    siren.start(p, millis());
    siren_silent = !sound;
}
void play(const sentry::Pattern* p) { play_pattern(p, true); }        // buzzer + LED
void flash(const sentry::Pattern* p) { play_pattern(p, false); }      // LED only

void ring(sentry::AlarmKind kind, const char* loc) {
    // An SOS outranks a fall: if a fall is ringing and an SOS arrives, switch rhythm.
    if (state == ST_RINGING && ringing_kind == sentry::MSG_SOS && kind == sentry::MSG_FALL) return;
    if (state == ST_RINGING && ringing_kind == kind && strcmp(ringing_loc, loc) == 0) return; // already ringing
    state = ST_RINGING;
    ringing_kind = kind;
    strncpy(ringing_loc, loc, sizeof(ringing_loc) - 1);
    ringing_loc[sizeof(ringing_loc) - 1] = 0;
    play(kind == sentry::MSG_SOS ? &sentry::PATTERN_SOS : &sentry::PATTERN_FALL);
    Serial.printf("[ALERT] %s in '%s' - ringing until silenced\n",
                  kind == sentry::MSG_SOS ? "SOS" : "FALL", loc[0] ? loc : "?");
}

void silence(const char* why) {
    if (state == ST_RINGING) repeats.silenced(ringing_kind, ringing_loc, millis());
    state = ST_IDLE;
    ringing_kind = sentry::MSG_NONE;
    ringing_loc[0] = 0;
    siren.stop();
    buzzer(false);
    led(false);
    Serial.printf("[ALERT] Silenced (%s)\n", why);
}

void send_heartbeat() {
    udpTx.beginPacket(IPAddress(255, 255, 255, 255), HEARTBEAT_UDP_PORT);
    udpTx.print("ALARM_READY:" + WiFi.localIP().toString());
    udpTx.endPacket();
}

void setup() {
    Serial.begin(115200);
    pinMode(LED_PIN, OUTPUT);
    pinMode(BUZZER_PIN, OUTPUT);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    buzzer(false);
    led(false);

    Serial.printf("\n[ALERT] Sentry Phase 8 Alert Station '%s'\n", station_name);
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.setSleep(false);   // modem sleep can delay/miss broadcast packets
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    udpRx.begin(ALARM_UDP_PORT);
    Serial.printf("[ALERT] Listening on UDP %d, heartbeats to UDP %d\n", ALARM_UDP_PORT, HEARTBEAT_UDP_PORT);
}

void loop() {
    const uint32_t now = millis();
    const bool wifi_ok = (WiFi.status() == WL_CONNECTED);

    // 1. Wi-Fi (re)connect: re-open the UDP socket and beep twice when we come online
    static bool was_online = false;
    if (wifi_ok && !was_online) {
        Serial.print("[ALERT] Wi-Fi connected, IP ");
        Serial.println(WiFi.localIP());
        udpRx.stop();
        udpRx.begin(ALARM_UDP_PORT);
        if (state == ST_IDLE) play(&sentry::PATTERN_BOOT);
        send_heartbeat();
    } else if (!wifi_ok && was_online) {
        Serial.println("[ALERT] Wi-Fi lost - reconnecting...");
    }
    was_online = wifi_ok;

    // 2. Button
    sentry::ButtonEvent ev = button.update(digitalRead(BUTTON_PIN) == LOW, now);
    if (swallow_press) {
        if (!button.isHeld()) swallow_press = false;
        ev = sentry::BTN_NONE;
    }
    if (ev != sentry::BTN_NONE) {
        if (state == ST_RINGING) {
            if (ev == sentry::BTN_DOWN) {   // silence at once, on press
                silence("button");
                swallow_press = true;
            }
        } else if (ev == sentry::BTN_LONG_PRESS) {
            Serial.println("[ALERT] Self-test");
            play(&sentry::PATTERN_TEST);
            if (wifi_ok) send_heartbeat();
        } else if (ev == sentry::BTN_SHORT_PRESS) {
            if (wifi_ok) play(&sentry::PATTERN_CHIRP);
            else flash(&sentry::PATTERN_CONFIRM);
        }
    }

    // 3. Alerts
    int packetSize = udpRx.parsePacket();
    if (packetSize) {
        char buf[256];
        char loc[64];
        int len = udpRx.read(buf, sizeof(buf) - 1);
        if (len > 0) {
            buf[len] = 0;
            sentry::AlarmKind kind = sentry::parseAlarm(buf, loc, sizeof(loc));
            if (kind == sentry::MSG_FALL || kind == sentry::MSG_SOS) {
                if (repeats.allow(kind, loc, now)) ring(kind, loc);
            } else if (kind == sentry::MSG_SILENCE) {
                if (state == ST_RINGING) silence("remote: LINE / dashboard");
            }
        }
    }

    // 4. Outputs
    if (siren.active()) {
        bool on = siren.output(now);
        led(on);
        buzzer(on && !siren_silent);
    } else if (button.isCharging() && !swallow_press) {
        led(true);   // feedback while holding for self-test
        buzzer(false);
    } else {
        buzzer(false);
        // Idle status light
        uint32_t ph = wifi_ok ? (now % 3000) : (now % 1000);
        bool on = wifi_ok ? (ph < 40) : (ph < 60 || (ph >= 160 && ph < 220));
        led(on);
    }

    // 5. Heartbeat
    static uint32_t last_hb = 0;
    if (wifi_ok && now - last_hb > HEARTBEAT_MS) {
        send_heartbeat();
        last_hb = now;
    }
}
