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
4. **The Sensitivity Gatekeeper (trade-off)**:
   - `headless_brain.py` (Phase 4) DOES use a per-room gatekeeper: if the window variance is below the room's threshold the prediction is forced to `STATIC (0)`, and above it a `STATIC` prediction is bumped to `MOVEMENT (1)`.
   - The risk: the fall state machine fires when an `IMPACT (2)` is followed by `STATIC (0)` within 3 s. If the threshold is set too high, a noisy movement spike followed by a forced `STATIC` can look like a fall. Keep the threshold close to the room's real static variance and tune it per room from the dashboard.
   - The 15-prediction majority vote and the median filter reduce this, and `Phase4_Multi_Node/tests` checks that the shipped model reports no falls on the static and walking recordings. Re-run those tests after changing the gatekeeper or the threshold default.
