// ============================================================
// Phase5_Alarm_Receiver.ino
// Sentry IoT - Physical Fall Alarm Node
//
// Compatible with ESP32 Arduino Core v3.x (new LEDC API)
//
// Listens for UDP "FALL_ALERT" packets from the Raspberry Pi
// and triggers:
//   1. Red LED blink pattern  (GPIO 2)
//   2. Scary descending buzzer (GPIO 4, passive buzzer)
//
// Graceful: if LED/buzzer not wired, no crash.
// ============================================================

#include <WiFi.h>
#include <WiFiUDP.h>

// ---------- CONFIGURATION ----------
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

const int ALARM_UDP_PORT = 5001;

const int LED_PIN    = 2;   // Red LED (220Ω resistor in series)
const int BUZZER_PIN = 4;   // Passive buzzer (100Ω resistor in series)
// -----------------------------------

WiFiUDP udp;

// Scary descending frequency sweep
const int NOTE_COUNT = 8;
const int FREQS[NOTE_COUNT]     = {2000, 1700, 1400, 1100, 900, 700, 500, 300};
const int DURATIONS[NOTE_COUNT] = { 120,  120,  120,  120, 150, 150, 180, 300};
const int ALARM_REPEAT          = 3;
const int FINAL_BLINKS          = 10;

// ---- helpers ----
void buzzerTone(int freq) {
  // New ESP32 Core v3 API: ledcWriteTone(pin, freq)
  ledcWriteTone(BUZZER_PIN, freq);
}

void buzzerOff() {
  ledcWriteTone(BUZZER_PIN, 0);
}

// ---- Boot setup ----
void setup() {
  Serial.begin(115200);
  Serial.println("\n[ALARM] Sentry Phase 5 - Alarm Receiver Boot");

  // LED
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // Buzzer: attach with new API (no channel needed)
  ledcAttach(BUZZER_PIN, 2000, 8);  // pin, initial freq, 8-bit resolution
  buzzerOff();

  // WiFi
  Serial.printf("[ALARM] Connecting to WiFi: %s\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 30) {
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[ALARM] WiFi OK! IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[ALARM] WiFi failed — will retry in loop");
  }

  udp.begin(ALARM_UDP_PORT);
  Serial.printf("[ALARM] Listening on UDP port %d\n", ALARM_UDP_PORT);

  bootBeep();
}

// ---- Main loop ----
void loop() {
  // Reconnect if WiFi dropped
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[ALARM] WiFi lost, reconnecting...");
    WiFi.reconnect();
    delay(3000);
    return;
  }

  // Check UDP
  int packetSize = udp.parsePacket();
  if (packetSize > 0) {
    char buf[64];
    int len = udp.read(buf, sizeof(buf) - 1);
    if (len > 0) {
      buf[len] = '\0';
      String msg = String(buf);
      msg.trim();
      Serial.printf("[ALARM] UDP received: %s\n", msg.c_str());

      if (msg.startsWith("FALL_ALERT")) {
        Serial.println("[ALARM] FALL DETECTED — triggering alarm!");
        triggerAlarm();
      }
    }
  }

  delay(10);
}

// ---- Full alarm sequence ----
void triggerAlarm() {
  for (int repeat = 0; repeat < ALARM_REPEAT; repeat++) {
    for (int i = 0; i < NOTE_COUNT; i++) {
      buzzerTone(FREQS[i]);
      digitalWrite(LED_PIN, (i % 2 == 0) ? HIGH : LOW);
      delay(DURATIONS[i]);
    }
    buzzerOff();
    digitalWrite(LED_PIN, LOW);
    delay(200);
  }

  // Final rapid LED flash
  for (int i = 0; i < FINAL_BLINKS; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(80);
    digitalWrite(LED_PIN, LOW);
    delay(80);
  }

  buzzerOff();
  digitalWrite(LED_PIN, LOW);
  Serial.println("[ALARM] Alarm sequence complete.");
}

// ---- 2 short boot beeps ----
void bootBeep() {
  for (int i = 0; i < 2; i++) {
    buzzerTone(1000);
    digitalWrite(LED_PIN, HIGH);
    delay(100);
    buzzerOff();
    digitalWrite(LED_PIN, LOW);
    delay(150);
  }
}
