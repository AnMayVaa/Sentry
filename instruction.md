# Sentry AI Project Instructions

This file serves to teach future AI agents about the Sentry CSI Fall Detection project architecture and critical rules.

## Project Architecture

1. **Legacy Setup (`Legacy_Desktop_GUI/`)**: 
   - Uses ESP-IDF (or Arduino IDE wrappers of ESP-IDF) to stream CSI over a physical USB serial connection.
   - Extremely stable frame rate (30fps) because the ESP32 only listens over Wi-Fi and uses USB for data transfer.
2. **Phase 1 Wireless Setup (`Phase1_Wireless_RX/`)**:
   - Upgrades the RX node to transmit data to the PC wirelessly via UDP packets instead of USB.
   - The RX Node is forced to share its single antenna for sniffing (Promiscuous) and transmitting (Station).
   
3. **Phase 1.75 USB Central Brain (`Phase1.75_USB_Central_Brain/`)**:
   - Drops the unreliable wireless UDP transmission from Phase 1.
   - Connects the RX ESP32 directly to a Raspberry Pi 5 via USB for a perfectly stable 30fps stream.
   - Replaces the standalone Python PyQt5 desktop app with a headless Python server (`headless_brain.py`) running as a `systemd` service (`sentry.service`).
   - Merges ML Inference, a File Server for the Dashboard UI, and a WebSocket Server onto a single unified port (8000) for easy Cloudflare proxying.
   - Uses an entirely web-based Glassmorphism dashboard (`dashboard/index.html`) accessible via `https://csi.ohmpatumwan.com/`.

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
4. **The Strict Gatekeeper Logic**:
   - In Phase 1, the gatekeeper was disabled due to the `uint8_t` bug causing fake variance spikes.
   - In Phase 1.75, because the variance math is accurate again, the **Strict Gatekeeper is mandatory**. `if variance < threshold: force STATIC`. This ignores micro-movements and false-positives predicted by the ML model.
5. **Cloudflare Tunnel Containerization**:
   - Tunnels run directly in terminal die when SSH closes. They MUST be run inside Docker with `--restart unless-stopped`.
   - When bridging a Cloudflare Docker container to a localhost service on a Raspberry Pi, you MUST use `--network host`. Otherwise, the tunnel attempts to connect to `localhost:8000` *inside* its own isolated container, causing a 502 Bad Gateway.
6. **UI Throttling & Animation Lag**:
   - Blasting raw 30 FPS JSON payloads over WebSocket over a Cloudflare Tunnel into a browser will overload the PC graphics card and lock up the browser's main thread. You MUST throttle the UI broadcast from the backend (e.g., to 15 FPS) while keeping the ML engine running internally at 30 FPS.
   - `Chart.js` animation calculations are too heavy for real-time streams. Use `chart.update('none')` to bypass the animation loop and draw instantly, eliminating micro-pausing.
7. **Mobile Responsiveness & CSS Clipping**:
   - Do NOT use `height: 100vh` combined with `overflow: hidden` on a main dashboard body. When users zoom in, the browser bounds shrink, causing elements at the bottom to be forcefully clipped and unreachable. Use `min-height: 100vh` and allow scrolling.
8. **WebSocket Multi-Client Sync (Optimistic UI)**:
   - Since multiple devices (Phone, iPad, PC) can connect to the Edge Brain simultaneously, state commands (like Connect/Disconnect or Threshold adjustments) MUST broadcast their resulting `config` state to ALL connected websocket clients (not just the sender), ensuring all dashboards stay in perfect sync.
   - Hardware initialization (like `serial.Serial`) blocks the Python process. The frontend must implement "Optimistic UI" (e.g. immediately changing button text to "Connecting...") to prevent the user from perceiving lag while the backend negotiates the COM port.
