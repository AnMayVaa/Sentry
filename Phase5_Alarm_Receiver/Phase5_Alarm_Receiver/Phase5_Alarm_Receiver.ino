// ============================================================
// Phase5_Alarm_Receiver.ino
// Sentry IoT - Physical Fall Alarm Node
// 
// Listens for UDP "FALL_ALERT" packets from the Raspberry Pi
// and triggers:
//   1. Red LED blink pattern (PIN 2)
//   2. Scary descending buzzer sound (PIN 4, passive buzzer)
//
// Graceful degradation: if LED/buzzer not wired, no crash.
// ============================================================

#include <WiFi.h>
#include <WiFiUDP.h>

// ---------- CONFIGURATION ----------
// Set your WiFi credentials here
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// UDP port to listen on (must match headless_brain.py ALARM_PORT)
const int ALARM_UDP_PORT = 5001;

// GPIO Pins
const int LED_PIN    = 2;   // Red LED (with resistor ~220Ω)
const int BUZZER_PIN = 4;   // Passive buzzer (with resistor ~100Ω)

// LEDC (PWM) channel for buzzer
const int BUZZER_CHANNEL  = 0;
const int BUZZER_FREQ     = 2000;  // Initial freq Hz
const int BUZZER_RES_BITS = 8;     // 8-bit resolution

// -----------------------------------

WiFiUDP udp;

// ---- Scary alarm pattern (descending freq sweep) ----
const int NOTE_COUNT = 8;
const int FREQS[NOTE_COUNT]      = {2000, 1700, 1400, 1100, 900, 700, 500, 300};
const int DURATIONS[NOTE_COUNT]  = {120,  120,  120,  120,  150, 150, 180, 300};
const int BLINK_TOTAL_CYCLES     = 10;   // LED blinks
const int ALARM_REPEAT           = 3;    // Repeat full pattern 3 times

void setup() {
  Serial.begin(115200);
  Serial.println("\n[ALARM] Sentry Phase 5 - Alarm Receiver Boot");

  // Set up pins safely
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // Set up LEDC for buzzer
  ledcSetup(BUZZER_CHANNEL, BUZZER_FREQ, BUZZER_RES_BITS);
  ledcAttachPin(BUZZER_PIN, BUZZER_CHANNEL);
  ledcWrite(BUZZER_CHANNEL, 0); // Silence on boot

  // Connect to WiFi
  Serial.print("[ALARM] Connecting to WiFi: ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 30) {
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[ALARM] WiFi connected!");
    Serial.print("[ALARM] IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[ALARM] WiFi failed. Will retry in loop.");
  }

  // Start UDP listener
  udp.begin(ALARM_UDP_PORT);
  Serial.print("[ALARM] Listening for fall alerts on UDP port ");
  Serial.println(ALARM_UDP_PORT);

  // Boot confirmation: 2 short beeps
  bootBeep();
}

void loop() {
  // Reconnect WiFi if dropped
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[ALARM] WiFi lost, reconnecting...");
    WiFi.reconnect();
    delay(3000);
    return;
  }

  // Check for incoming UDP packet
  int packetSize = udp.parsePacket();
  if (packetSize > 0) {
    char packetBuffer[64];
    int len = udp.read(packetBuffer, sizeof(packetBuffer) - 1);
    if (len > 0) {
      packetBuffer[len] = '\0';
      String msg = String(packetBuffer);
      msg.trim();

      Serial.print("[ALARM] Received UDP: ");
      Serial.println(msg);

      if (msg.startsWith("FALL_ALERT")) {
        Serial.println("[ALARM] 🚨 FALL DETECTED — Triggering alarm!");
        triggerAlarm();
      }
    }
  }

  delay(10); // Small yield to prevent watchdog reset
}

// ---- Trigger the full alarm sequence ----
void triggerAlarm() {
  for (int repeat = 0; repeat < ALARM_REPEAT; repeat++) {
    // --- Scary descending tone sweep ---
    for (int i = 0; i < NOTE_COUNT; i++) {
      // Buzzer note
      ledcSetup(BUZZER_CHANNEL, FREQS[i], BUZZER_RES_BITS);
      ledcWrite(BUZZER_CHANNEL, 128); // 50% duty cycle = loud

      // LED blink synced with buzzer
      digitalWrite(LED_PIN, (i % 2 == 0) ? HIGH : LOW);

      delay(DURATIONS[i]);
    }

    // Silence between repeats
    ledcWrite(BUZZER_CHANNEL, 0);
    digitalWrite(LED_PIN, LOW);
    delay(200);
  }

  // Final rapid LED flash
  for (int i = 0; i < BLINK_TOTAL_CYCLES; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(80);
    digitalWrite(LED_PIN, LOW);
    delay(80);
  }

  // All off
  ledcWrite(BUZZER_CHANNEL, 0);
  digitalWrite(LED_PIN, LOW);
  Serial.println("[ALARM] Alarm sequence complete.");
}

// ---- Boot confirmation 2 short beeps ----
void bootBeep() {
  for (int i = 0; i < 2; i++) {
    ledcSetup(BUZZER_CHANNEL, 1000, BUZZER_RES_BITS);
    ledcWrite(BUZZER_CHANNEL, 100);
    digitalWrite(LED_PIN, HIGH);
    delay(100);
    ledcWrite(BUZZER_CHANNEL, 0);
    digitalWrite(LED_PIN, LOW);
    delay(150);
  }
}
