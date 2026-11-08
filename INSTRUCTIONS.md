# Sentry: Smart Fall Detection System (AI Knowledge Base)

This document serves as the master knowledge base for any AI assisting with this project. Read this carefully to understand the architecture, hardware, software stack, and deployment environment.

## 1. Project Overview
"Sentry" is an Edge-Compute Smart Fall Detection System designed for elderly care in residential areas. It uses Wi-Fi Channel State Information (CSI) to detect physical movement and falls without requiring the user to wear any devices or cameras, ensuring privacy. 

## 2. Hardware Architecture
- **Transmitter (TX):** 5G AX1800 Wireless Dual-Band Gigabit Router (or an ESP32 acting as an AP).
- **Receiver (RX):** ESP32 microcontroller with a 2.5GHz antenna. It captures the CSI data (subcarrier amplitudes) from the Wi-Fi signals.
- **Edge Compute Server:** Raspberry Pi 5 (8GB RAM, 64GB SD).
  - The ESP32 is physically plugged into the Raspberry Pi 5 via USB (`/dev/ttyUSB0` or `/dev/ttyUSB1`).
  - The Pi runs the heavy Machine Learning inference, Web Server, and WebSocket Server.

## 3. Software Stack & Codebase
The core logic resides in the `Phase4_Multi_Node` directory:
- **`headless_brain.py`**: The main backend script. It extracts features (variance), runs them through a pre-trained `scikit-learn` Random Forest model, and broadcasts the state and live data via WebSockets. It acts as a **Multi-Node Universal Brain**, dynamically supporting infinite concurrent ESP32s over USB PySerial and Wireless UDP Wi-Fi, assigning unique ID prefixes to prevent data collisions.
- **`serial_reader.py`**: Parses raw CSI integers from the ESP32 via physical USB cable.
- **`udp_reader.py`**: Parses raw CSI integers wirelessly over the local Wi-Fi network (Port 5000), broadcasting to `255.255.255.255` for instant auto-discovery of nodes.
- **`dashboard/index.html`**: The frontend UI. It features a modern Glassmorphism Dark Mode dashboard using `Chart.js`. It dynamically spawns `NodeCard` UI components based on active hardware, scaling infinitely. Includes per-room Sensitivity Threshold sliders and auto-polling Hardware Connection lists.
- **`line_notifier.py`**: Sends an emergency alert message to a LINE Group via the LINE Notify API when a Fall is confirmed.

## 4. Edge Server Deployment (Raspberry Pi 5)
- **Path:** `/home/ohmpatumwan/Sentry/Phase3_Router_as_TX`
- **Python Environment:** Runs natively or via `venv` on the Pi (`pandas`, `scikit-learn`, `websockets`, `pyserial`).
- **Systemd Service:** `sentry.service`
  - The backend runs automatically on boot as a Linux background service.
  - Commands to manage: 
    - `sudo systemctl status sentry.service`
    - `sudo systemctl restart sentry.service`
    - `journalctl -u sentry.service -f` (to view live logs)

## 5. Cloudflare & Networking (Reverse Proxy)
The system is accessible globally via the user's domain: `ohmpatumwan.com`.
Traffic is routed through a Cloudflare Tunnel named `raspi5` (running on the Pi).
- **Dashboard (HTTP):** Cloudflare routes `https://csi.ohmpatumwan.com` to `http://127.0.0.1:8000` on the Pi.
- **WebSocket (Data Stream):** `wss://csi.ohmpatumwan.com/ws` is served by the same unified server on port 8000 (`networking.http_port`). Port 8765 is no longer used by Phase 4.
*Note: The frontend `index.html` uses dynamic path-based routing (`/ws`) to ensure the WebSocket connection passes through the Cloudflare Proxy correctly without port blocking.*

## 5.1 Secrets & Access Control
- `config.json` is tracked in a **public** repo, so it must never hold secrets. Put real values in `config.local.json` next to it (git-ignored; copy `config.local.example.json`). Environment variables `SENTRY_LINE_TOKEN`, `SENTRY_LINE_USER_ID`, `SENTRY_CONTROL_TOKEN` and `SENTRY_PUBLIC_URL` override both files.
- `security.control_token`: when set, every dashboard command that changes the system (threshold, connect/disconnect, TX mode, simulation, test alerts) and the `/silence` link require it. Open the dashboard once as `https://csi.ohmpatumwan.com/?token=YOUR_TOKEN` and the browser remembers it. The LINE "Silence Alarm" button includes the token automatically. Without a token anyone who finds the URL can disable detection.
- Firmware Wi-Fi credentials go in `Phase7_Combined_Node/Phase7_Combined_Node/secrets.h` (git-ignored; copy `secrets.example.h`).
- `deploy.py` uses your SSH key, never a stored password. Override host/user/path with `SENTRY_PI_HOST`, `SENTRY_PI_USER`, `SENTRY_PI_PATH`.

## 5.2 Subcarrier Alignment (do not change without retraining)
The model was trained on `amplitudes[2:28] + amplitudes[38:64]` (52 values) because the training CSVs have one more value per row than header columns and pandas shifts them. `ml_engine.select_subcarriers()` is the single place that picks these; both readers use it. If you retrain with a fixed CSV header, change `select_subcarriers()` at the same time.

## 5.3 Tests
`python -m pytest Phase4_Multi_Node/tests -q` (from the repo root) checks config loading, the fall state machine, the control token, UDP parsing, and that the shipped model does not report falls on the static/walking recordings.

## 6. Logic & State Machine
The system tracks three states: `0=STATIC`, `1=MOVEMENT`, `2=FALL`.
- **Noise Gate / Threshold:** If the rolling variance is below the adjustable Threshold, the system forces a `STATIC` state.
- **Fall Confirmation:** A fall is only confirmed if the ML model detects an `IMPACT (2)` immediately followed by `STATIC (0)` for 3 seconds. This prevents false positives (e.g., sitting down quickly).
- **Debounce:** LINE notifications have a 60-second cooldown so they don't spam the user.
- **SOS Button:** Sending the string `"SOS"` over the serial port triggers an immediate emergency override.

## 7. Interactive GUI Features
The HTML Dashboard is not just read-only; it features a Two-Way WebSocket Control Panel:
- **COM Port Selector:** Queries the Pi for active USB devices and allows the user to reconnect the ESP32 on the fly if it unplugs/changes ports.
- **Sensitivity Threshold:** A slider to dynamically adjust the Noise Gate threshold in `headless_brain.py` without restarting the server.

## 8. AI Developer Guidelines
When making changes:
1. Always edit the local codebase first (`C:\Antigravity\CSI`).
2. Commit and push changes to GitHub (`master` branch).
3. SSH into the Pi (`ssh ohmpatumwan@ohmpatumwan`), run `git pull`, and restart `sentry.service`.
4. Keep the UI elegant, modern, and dark-mode focused. Ensure JavaScript charting runs smoothly at 30fps.
5. Do not break the `asyncio` WebSocket loop in `headless_brain.py` (we use `websockets.serve` inside an `async def`).
