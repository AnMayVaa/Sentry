# Sentry AI Project Instructions

This file serves to teach future AI agents about the Sentry CSI Fall Detection project architecture and critical rules.

## Project Architecture

1. **Legacy Setup (`Legacy_Desktop_GUI/`)**: 
   - Uses ESP-IDF (or Arduino IDE wrappers of ESP-IDF) to stream CSI over a physical USB serial connection.
   - Extremely stable frame rate (30fps) because the ESP32 only listens over Wi-Fi and uses USB for data transfer.
2. **Phase 1 Wireless Setup (`Phase1_Wireless_RX/`)**:
   - Upgrades the RX node to transmit data to the PC wirelessly via UDP packets instead of USB.
   - The RX Node is forced to share its single antenna for sniffing (Promiscuous) and transmitting (Station).
   
## Critical Engineering Physics & Rules

1. **The ESP32 Wi-Fi Channel Lock**:
   - The TX Node, RX Node, and the Home Wi-Fi Router MUST be on the exact same channel (e.g., Channel 6). If the router shifts to Channel 11, the RX Node will switch to Channel 11 when it connects, becoming deaf to the TX Node on Channel 6.
2. **The Int8 vs Uint8 Math Bug**:
   - Raw CSI subcarriers contain BOTH positive and negative numbers.
   - The ML Model was trained on SIGNED data (`int8_t`). If you mistakenly define the CSI buffer as `uint8_t`, the negative numbers will mathematically wrap around to massive integers (e.g. `251`), completely breaking the AI Variance calculations and locking the app in a false "MOVEMENT" state.
   - Arduino `udp.print(int8_t)` prints invisible ASCII characters instead of negative numbers. ALWAYS cast to `(int)` before printing over UDP/Serial.
3. **The UDP Frame Rate Dilution Problem (Batching)**:
   - If the RX Node sends a UDP packet for every single CSI frame it receives (30Hz), the massive TX overhead will cause it to drop incoming sniffing packets, plummeting the frame rate to 10-15fps.
   - Because the AI calculates Variance over a 45-frame window, 10-15fps stretches the window to 3 seconds, heavily diluting the standard deviation of short movements and causing false negatives.
   - You MUST batch CSI packets (e.g., 5 frames per 1 UDP packet separated by `\n`) to free up airtime for the sniffer antenna.
4. **The UI Strict Gatekeeper**:
   - Do NOT use a strict gatekeeper logic (e.g. `if variance < threshold: force STATIC`).
   - The Sequence State Machine relies on `MOVEMENT (1/2)` transitioning to `STATIC (0)` to detect a fall. If you artificially force `STATIC` when the variance drops, a noisy movement spike will instantly trigger a false-positive FALL. Let the ML model dictate `STATIC` naturally.
