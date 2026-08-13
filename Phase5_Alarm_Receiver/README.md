# Phase 5 — Physical Alarm Receiver

## Overview
A standalone ESP32 node that physically alerts when a fall is detected by the Sentry system.

When the Raspberry Pi detects a fall, it sends a tiny UDP broadcast packet (`FALL_ALERT:<location>`) to the whole LAN.  
This ESP32 receives that packet and immediately triggers:
1. 🔴 **Red LED blink pattern** — rapid alternating flashes
2. 🔊 **Scary descending buzzer sweep** — 8-step frequency drop from 2000 Hz → 300 Hz, repeated 3 times

## Hardware
| Component | GPIO Pin | Notes |
|---|---|---|
| Red LED | GPIO **2** | Add 220Ω resistor in series |
| Passive Buzzer | GPIO **4** | Add 100Ω resistor in series |

**Wiring diagram:**
```
3.3V ──[220Ω]──[LED+]──[LED-]── GND
GPIO2 ──────────────────────────┘  (short leg of LED to GND)

GPIO4 ──[100Ω]──[BUZZER+]──[BUZZER-]── GND
```

## Graceful Degradation
If the LED or buzzer is **not connected**, the firmware will not crash.  
The ESP32 simply won't have anything to drive. No errors are sent to the dashboard.

## Setup
1. Open `Phase5_Alarm_Receiver.ino` in Arduino IDE
2. Edit `WIFI_SSID` and `WIFI_PASSWORD` to match your network
3. Upload to any spare ESP32
4. On boot you will hear 2 short beeps (confirmation)
5. Serial Monitor (115200 baud) shows IP address and incoming packets

## How It Works
```
Raspberry Pi (headless_brain.py)
    │
    │  UDP Broadcast (255.255.255.255:5001)
    │  Packet: "FALL_ALERT:Living Room"
    ▼
ESP32 Alarm Receiver
    │
    ├── Descending tone sweep × 3 (GPIO4, LEDC PWM)
    └── LED blink pattern (GPIO2)
```

## Config (config.json)
```json
"alarm": {
    "enabled": true,
    "udp_port": 5001
}
```
Set `"enabled": false` to disable all physical alarms without modifying code.
