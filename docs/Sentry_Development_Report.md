# Sentry Project — Full Development Report
**Project:** CSI-Based Smart Fall Detection System for Elderly in Residential Areas
**Contest:** NSC 2026 (28th National Software Contest)
**Prepared for:** Co-Worker Handoff
**Date:** June 2026

---

## Project Summary

**Sentry** is a non-invasive fall detection system that uses invisible Wi-Fi radio waves — specifically **Wi-Fi Channel State Information (CSI)** — to detect human movement and falls in real time, without any wearable devices or cameras.

The system captures how a person's body distorts the invisible 2.4GHz Wi-Fi waves passing through a room. A Machine Learning model then analyzes these wave distortions to distinguish between Static, Movement, and Fall states, and automatically notifies caregivers via LINE when a fall is confirmed.

### Tech Stack Overview

| Layer | Technology |
|---|---|
| Hardware Sensors | ESP32 microcontrollers (Tx + Rx nodes) |
| Firmware | Arduino IDE (ESP-IDF native wrappers) |
| Edge Compute | Raspberry Pi 5 (headless server) |
| Backend | Python — `asyncio`, `websockets`, `scikit-learn`, `numpy` |
| Frontend | Vanilla HTML/CSS/JS — `Chart.js` |
| Networking | Cloudflare Tunnel → `csi.ohmpatumwan.com` |
| Notifications | LINE Messaging API (Flex Messages) |

---

## Phase 1 — Hardware Setup & Raw CSI Extraction

### Goal
Establish a stable wireless link between two ESP32 modules and extract raw Channel State Information (CSI) subcarrier amplitudes at 30 frames per second.

### How It Works
Wi-Fi signals are made up of **52 OFDM subcarriers** — essentially 52 parallel data lanes. When a human body moves through a room, it bends and scatters these radio waves in a mathematically unique way. By reading the **amplitude** of all 52 subcarriers 30 times per second, we can detect this distortion as a "motion signature."

### Approach
- **Transmitter (Tx) ESP32:** Configured to continuously inject raw **802.11 QoS Data** packets at 30Hz using **ESP-NOW** protocol (connectionless). This forces the radio to operate at the 54 Mbps OFDM rate, guaranteeing all 52 subcarriers are active in every packet.
- **Receiver (Rx) ESP32:** Placed in **Promiscuous Mode** to sniff all nearby Wi-Fi traffic and filter specifically for packets from the Tx node's MAC address. The CSI payload (52 signed integers) is then streamed over USB to a Windows PC.
- **Python GUI (PyQt6):** Real-time graphing application that reads the serial stream and plots all 52 subcarrier amplitudes live.

### Conflict & Solution

**Problem:** The Rx ESP32 kept crashing and rebooting with:
```
E (xxxx) task_wdt: Task watchdog got triggered.
```

**Root Cause:** The UART serial port was configured at the standard `115200` baud rate. At 30 frames per second with 52 floats per frame, this baud rate was too slow to flush the hardware transmit buffer — it overflowed and the CPU watchdog timer killed the task.

**Fix:** We forced the UART baud rate to `460800` baud in both the ESP-IDF `sdkconfig` file and the `rx_main.c` source code. This is 4× faster, providing enough bandwidth for crash-free, real-time 30Hz CSI streaming.

---

## Phase 2 — Machine Learning Fall Detection

### Goal
Train an AI model to mathematically classify the CSI data stream into three categories: Static (0), Movement (1), and Fall (2).

### Approach
1. **Data Collection:** Recorded three separate 5-minute CSV datasets: `static.csv` (sitting still), `walking.csv` (walking back and forth), `falling.csv` (intentional falls between antennas).
2. **Feature Engineering (`train_model.py`):** A sliding window of 45 frames (~1.5 seconds) is used. For each window, we extract: Variance, Standard Deviation, Mean, Rate of Change, and Peak-to-Peak amplitude.
3. **Model:** Trained a **Random Forest Classifier** (`scikit-learn`) — chosen for its speed (sub-millisecond inference), robustness to noise, and resistance to overfitting on a small dataset.

### Conflicts & Solutions

**Problem 1 — Physics Blind Spot:**
The AI classified every fall as "Static." Root cause: we recorded the falls standing *behind* the line-of-sight between the two antennas. The body never intersected the Wi-Fi wave path, so the subcarrier amplitudes didn't change.

*Fix:* Re-recorded falls standing **directly between** the two antennas. Variance spikes during impact jumped to 40–80, giving the model a clear training signal.

---

**Problem 2 — Label Contamination:**
The AI started classifying normal walking as "Fall." Root cause: `falling.csv` was recorded as one long session — it contained several seconds of walking *to* the falling zone, the fall itself, and then several seconds of lying still. All of this was labeled "Fall," which corrupted the model.

*Fix:* Engineered an automated **Data Cleaner** inside `train_model.py`. It mathematically sorts every 45-frame window by Variance and retains only the **top 15%** highest-variance windows — the actual impact moment. All low-activity windows labeled as "Fall" are discarded before training.

---

**Problem 3 — UI Flickering / False Positives:**
Quick hand shakes or someone sitting down abruptly caused the UI to instantly flash "FALL DETECTED" for 1-2 frames.

*Fix:* Implemented a **Temporal State Machine**. A real fall is physically defined as:
1. A sudden variance spike (IMPACT state)
2. Followed immediately by near-zero variance (body lying still)

The system now requires **both** conditions to be satisfied in sequence. If the person continues moving after a spike, it's classified as "MOVEMENT." Only 3 consecutive seconds of stillness after an impact locks in a "CONFIRMED FALL." This reduced false positives to near-zero.

---

## Phase 3 — Emergency Notification System (LINE API)

### Goal
Instantly and reliably send an emergency alert to family members / caregivers when a fall is confirmed.

### Approach
We integrated the **LINE Messaging API** (chosen because LINE is universally used in Thai households — no extra apps required). The script `line_notifier.py` constructs a **Flex Message** — a custom-designed rich interactive card — showing:
- The exact timestamp of the fall
- The location name
- A large button that dials `1669` (Thai ambulance) when tapped

### Conflicts & Solutions

**Problem — API Rate Limit Spam + UI Freeze:**
Two bugs emerged simultaneously. If a person remained on the ground, the Python loop (running at 30Hz) would call the LINE API thousands of times per minute, resulting in an API ban. Additionally, the HTTPS request was blocking the main thread, causing the real-time graphs to freeze for 2-3 seconds.

*Fix 1 (Non-blocking):* Executed the LINE API call inside a `threading.Thread(daemon=True)`. The background thread sends the alert completely independently, and the main CSI processing loop never stalls.

*Fix 2 (Rate Limiting):* Implemented a **60-second cooldown timer** (`last_line_alert_time`). If the state is still "Fall" after 60 seconds, a new alert fires. This ensures caregivers get regular updates while preventing API abuse.

---

## Phase 4 (Early) — Hardware SOS Panic Button

### Goal
Allow the elderly user to manually trigger an emergency alert at any time (e.g., they feel dizzy, chest pain, or are about to fall) without waiting for the AI to confirm anything.

### Approach
We "hacked" the physical **BOOT button** (GPIO 0) built directly onto the ESP32 board — no extra components needed. When pressed, the Tx ESP32 changes what it broadcasts.

### Conflicts & Solutions

**Problem — MAC Layer Blocks ESP-NOW in Promiscuous Mode:**
The intended approach was for the Tx node to send an ESP-NOW message with an "SOS" payload. However, the Rx node runs in Promiscuous Mode for CSI sniffing. This mode forces the MAC layer to process every packet at the lowest level, completely bypassing the normal `espnow_recv_cb` callback. The SOS message was received but silently dropped.

*Fix — Physics-Based Detection:*
We bypassed the software entirely using a **physical packet size trick**. A normal CSI frame is ~16 bytes. When the SOS button is pressed, the Tx node instantly bloats its next packet to **150 bytes**. On the Rx side, we monitor `info->rx_ctrl.sig_len` inside the Promiscuous Mode callback. If a packet larger than 100 bytes is detected, it's recognized as an SOS signal *without decoding the payload at all* — bypassing every software restriction. Both nodes' physical BOOT buttons now act as panic buttons.

---

**Problem 2 — Python Crash on Unexpected SOS String:**
After the hardware fix, the Python app silently crashed. The `data_received()` callback strictly expected `(amplitudes: list, rssi: int)` but received only the string `"SOS"`.

*Fix:* Updated `serial_reader.py` to intercept the `SOS_ALERT` string before the callback, and pass a synthetic tuple `("SOS", 0)` instead, satisfying the callback signature and triggering the LINE API correctly.

---

## Phase 1.5 — Wireless UDP Receiver (Cable-Free)

### Goal
Eliminate the physical USB cable between the ESP32 Rx node and the PC, allowing the receiver to be placed anywhere in the house wirelessly.

### Approach
Rewrote the Rx firmware in **Arduino IDE** (`.ino`). The node continues to sniff CSI in Promiscuous Mode, but instead of printing over Serial, it connects to the home Wi-Fi router and sends **batched UDP packets** to the Windows PC on Port 5000.

### Conflicts & Solutions

**Problem 1 — ESP-IDF Build Toolchain Failures:**
The Windows ESP-IDF C build environment had broken `PATH` variables and Python alias conflicts that prevented flashing.

*Fix:* Abandoned ESP-IDF for this phase, migrating entirely to **Arduino IDE**. The ESP32 Arduino Core wraps ESP-IDF natively, so we could still call `<esp_wifi.h>` Promiscuous Mode APIs with a simple 1-click GUI upload.

---

**Problem 2 — One Antenna, Two Jobs (The Frequency Blindness Problem):**
After flashing, the Arduino printed `CSI Sniffing Started!` — but received zero packets. The ESP32 has only **one physical antenna**. When `WiFi.begin()` joined the home router (which was on Channel 11), the antenna physically retuned to Channel 11. The Tx node was still transmitting on Channel 6. The receiver became completely deaf.

*Fix:* Logged into the TP-Link router admin panel and **forced the 2.4GHz Wi-Fi band to Channel 6**. This aligned all three devices on the same frequency.

---

**Problem 3 — Unsigned Integer Overflow (Amplitude Explosion):**
UDP packets arrived, but amplitude values were 100–300 instead of the expected 0–40, causing Variance to constantly exceed 120 and fire continuous false alarms.

*Root Cause:* The CSI buffer was declared as `uint8_t buf[128]` (unsigned). When the ESP32 measured a physically negative CSI value (e.g., `-5`), the `uint8_t` type wrapped it to `251`. This was transmitted to Python as-is.

*Fix:* Changed the struct definition to `int8_t buf[128]`. Negative values now transmit correctly, stabilizing amplitudes to the expected 0–40 range.

---

**Problem 4 — Frame Rate Dilution (50% Packet Drop):**
Even with correct amplitudes, the system needed extremely aggressive, prolonged movement to trigger detection. Root cause: the ESP32's single antenna was constantly switching between "listen for CSI" (Promiscuous Mode) and "transmit UDP to router" (Station Mode) 30 times per second. This switching overhead dropped ~50% of incoming CSI packets, stretching the 45-frame ML window from 1.5 seconds to over 3 seconds — artificially diluting variance.

*Fix:* Implemented **UDP Packet Batching**. Instead of one UDP packet per CSI frame, the ESP32 now queues 5 CSI frames into a memory buffer and sends them in one UDP packet separated by `\n`. This reduced Wi-Fi transmissions by 500%, giving the antenna 95% of its time for listening. Python's `udp_reader.py` was upgraded to split and process multi-line packets. Full 30Hz frame rate was restored.

---

## Phase 1.75 — Edge Compute Server & Cloudflare Global Deployment

### Goal
Move the ML inference off the local PC and onto a Raspberry Pi 5 edge server, making the dashboard accessible globally through the internet without opening router ports.

### Architecture
```
Internet → cloudflare.com → Cloudflare Tunnel → Raspberry Pi 5:8000
                                                     ↕ WebSocket
                                              headless_brain.py
                                                     ↕ USB/UDP
                                              ESP32 Rx Nodes
```

### Approach
- Wrote `headless_brain.py` — a single unified Python server that binds `http.server` and `websockets` on port `8000`.
- Built `dashboard/index.html` — a Glassmorphism dark-mode dashboard with real-time `Chart.js` graphs.
- Deployed `cloudflare/cloudflared` in a persistent Docker container as a secure reverse proxy, exposing port `8000` globally.

### Conflicts & Solutions

**Problem 1 — 502 Bad Gateway on Cloudflare Tunnel:**
The tunnel said "Healthy" but the browser returned `502 Bad Gateway`. The Docker container's `localhost` pointed to the container's isolated network namespace, not the Pi's host network.

*Fix:* Redeployed the container with `--network host`, binding it directly to the Pi's physical network stack.

---

**Problem 2 — Browser Graphics Lag:**
The dashboard stuttered and froze on all devices. Root cause: Python was blasting 30 JSON payloads per second and `Chart.js` tried to interpolate smooth animation curves between every single data point, completely overloading the browser renderer.

*Fix (Two-Layer Optimization):*
- **Backend:** Throttled WebSocket broadcasts to **15 FPS** (ML model still runs at 30Hz internally).
- **Frontend:** Disabled Chart.js animations with `chart.update('none')`, forcing raw immediate pixel rendering.

---

**Problem 3 — Responsive Layout Destruction on Mobile:**
The dashboard broke on iPhones and iPads — charts clipped, text overflowed, panels stacked vertically into useless thin strips.

*Fix:* Changed the main container CSS from `height: 100vh; overflow: hidden` to `min-height: 100vh`. Added `overflow-x: auto` to chart wrappers for horizontal scrolling. Added `@media` breakpoints to reflow the control panel on small screens.

---

**Problem 4 — Multi-Device State Desync:**
When one user (e.g., on a phone) changed a setting, other users (e.g., on a PC) saw a stale UI. Also, pressing "Connect" gave no feedback for 1-2 seconds while Python initialized the serial port.

*Fix 1 (State Sync):* Built `broadcast_config()` — an asyncio coroutine that pushes the full system state to every connected WebSocket client immediately on any change.

*Fix 2 (Optimistic UI):* The Connect button now *immediately* shows "Connecting..." upon click, before Python responds. The UI updates feel instant to the user.

---

## Phase 2 — Universal Brain (USB + UDP + mDNS)

### Goal
Allow the Raspberry Pi backend to simultaneously support both USB Serial ESP32s and Wi-Fi UDP ESP32s — selectable from the dashboard UI.

### Approach
Engineered a **Universal Firmware** (`Arduino_UDP_Receiver.ino`) that simultaneously:
- Prints CSI data to USB Serial (for wired mode)
- Blasts CSI data over UDP Wi-Fi (for wireless mode)

The backend was upgraded to dynamically spawn either a `SerialReader` or `UDPReader` based on the user's selection in the dashboard.

### Conflicts & Solutions

**Problem 1 — Hardcoded IP Address Fragility:**
The firmware had the Raspberry Pi's IP hardcoded. When the router rebooted and DHCP reassigned a new IP, all UDP packets went into the void.

*Fix:* Implemented **mDNS Auto-Discovery** using `<ESPmDNS.h>`. Upon boot, the ESP32 broadcasts a query for `OhmPatumwan.local`. The Pi responds with its current IP. The ESP32 locks onto it dynamically — permanently immune to DHCP changes.

---

**Problem 2 — Firmware Fragmentation:**
Switching between USB and UDP modes required re-flashing the ESP32 every time.

*Fix:* The Universal Firmware streams data *simultaneously* over both interfaces. Flash it once, use it forever. The user simply selects the desired input mode from the web dashboard.

---

## Phase 3 — "God Firmware", Router-as-TX & Zero-Lag Pipeline

### Goal
Eliminate the dedicated Tx ESP32 entirely. Instead, repurpose the existing home Wi-Fi router as the ambient Wi-Fi transmitter. Optimize the full pipeline for zero-lag, real-time inference.

### Approach
The **Phase3_God_Firmware** turns the ESP32 into a pure passive receiver. It sniffs CSI from the home router's normal Wi-Fi broadcasts, which already blanket the room with OFDM waves. The Python backend stimulates the router by sending empty UDP packets over Wi-Fi, keeping the router actively transmitting.

### Conflicts & Solutions

**Problem 1 — ESP32 Serial Output Bottleneck (167ms Lag):**
The system accumulated a growing backlog of frames, causing decisions to lag 167ms or more behind real-time. Root cause: `Serial.print()` outputs strings character-by-character in a blocking loop, stalling the ESP32 CPU between every CSI frame.

*Fix:* Replaced `Serial.print()` with `Serial.write()` of a pre-formatted binary memory buffer. This flushes all 52 values in a single syscall, reducing ESP32 transmission latency to near-zero.

---

**Problem 2 — Python Pandas Hot-Path Overhead:**
The Raspberry Pi's ML backlog grew infinitely. Root cause: `headless_brain.py` constructed and destroyed a Pandas `DataFrame` object on every single incoming frame (30Hz), which allocates and deallocates memory constantly on the Pi's limited RAM.

*Fix:* Eliminated Pandas from the real-time loop entirely. Rewrote feature extraction as `extract_features_np()` — operating directly on raw NumPy arrays. Added a `self._processing` threading lock: if the previous frame's ML inference is still running when the next frame arrives, the new frame is silently dropped rather than queued, preventing any backlog from forming.

---

**Problem 3 — Browser Render Jank at 30Hz:**
Chart.js attempted to repaint every frame at 30Hz, causing visible stuttering.

*Fix:* Implemented a JavaScript **frame-buffer decoupler**. WebSocket messages write to a `pendingData` variable. The browser's native `requestAnimationFrame` API reads from this buffer and triggers repaints only when the hardware display vsync is ready (up to 60fps). This completely eliminates forced layout thrashing.

---

**Problem 4 — JSON Serialization Crash:**
The backend sporadically crashed with `TypeError: Object of type int32 is not JSON serializable`. The `scikit-learn` Random Forest returns NumPy `int32`, which Python's `json.dumps()` cannot handle.

*Fix:* Wrapped the model output with an explicit `int()` cast: `int(model.predict([features])[0])`.

---

**Problem 5 — Long-Session Chart.js Memory Leak:**
After hours, the browser became sluggish with increasing RAM usage. Root cause: the JavaScript was assigning a brand new array object to `rawChart.data.datasets[0].data` on every update. Chart.js internally creates and destroys 52 objects per update cycle, causing the browser's Garbage Collector to run constantly.

*Fix:* Changed from array reassignment to **in-place mutation**: `rawData[i] = newValue` for each of the 52 subcarriers. Chart.js now recycles the same 52 objects infinitely, achieving zero memory growth over unlimited runtime.

---

## Phase 4 — Multi-Node Architecture & Stability Overhaul

### Goal
Scale the system from one room to an entire house. Support an unlimited number of ESP32 Rx nodes deployed in different rooms (e.g., Living Room, Bathroom), each appearing as an independent monitoring block on the dashboard.

### Architecture Change
The single-instance `NodeState` was replaced with a `dict` of `NodeState` objects keyed by a unique location ID. The dashboard dynamically spawns and destroys `NodeCard` UI components based on which nodes are actively streaming.

### Conflicts & Solutions

**Problem 1 — Data Merging (Both Rooms Show Same Block):**
Connecting two ESP32s resulted in their data colliding into a single dashboard block. Root cause: both Arduino sketches had the same hardcoded `location_name = "Bath Room"` string, so Python used the same dictionary key for both — overwriting data.

*Fix:* The `data_received()` callback now prepends the physical connection interface ID to the location name: `[/dev/ttyUSB0] Bath Room` vs `[UDP_5000] Bath Room`. No firmware re-flash required. Each physical port automatically creates a unique key.

---

**Problem 2 — Zombie Charts on Reconnection:**
When an ESP32 disconnected, its UI block was removed. Upon reconnection, the new graph rendered corrupt — drawing lines backward across old ghost data. Root cause: the `<canvas>` HTML element was removed from the DOM, but the `Chart.js` context object remained allocated in the browser's JavaScript heap, corrupting the new instance.

*Fix:* Refactored the UI into a proper `NodeCard` JavaScript class. The `destroy()` method explicitly calls `chart.destroy()` on both graphs before removing the DOM node. This purges the Chart.js GPU context completely.

---

**Problem 3 — ESP32 Lag & Disappearing Nodes (Over Long Sessions):**
After 30–60 minutes, nodes began to show lag (Temporal Variance number stuttering) and eventually disappeared from the dashboard entirely. Root cause: the Python backend was sending a "PING" UDP string directly to each ESP32's IP at 10Hz (to stimulate router traffic). The ESP32 was receiving and trying to parse 10 UDP string commands per second on its tiny heap, causing memory fragmentation, lag, and eventual crashes/reboots.

*Fix:* Removed all direct PING packets to the ESP32. Instead, broadcast an empty binary pulse to `255.255.255.255` (the entire subnet) on a **dummy port 5001** that nothing listens to. The home router still re-broadcasts this traffic (stimulating the Wi-Fi waves), but the ESP32 microcontrollers are never targeted and remain perfectly stable.

---

**Problem 4 — UDP Mode Blindness (Must Toggle UI to Refresh):**
After connecting multiple ESP32s over UDP, users had to manually toggle the "Transmitter Target" button back and forth before the ESP32s would start streaming in the correct mode. Root cause: Python didn't know any ESP32's IP address until *after* it received the first packet. It couldn't send the initial `MODE_ROUTER` command because there was no destination to send it to.

*Fix:* Upgraded `send_command()` in `udp_reader.py` to use **subnet broadcasting**. It now sends commands to `255.255.255.255:5000` in addition to any known IPs. Every ESP32 on the local network receives and applies the command instantly on first connection, no toggling needed.

---

**Problem 5 — Variance Graph Invisible After Large Movement:**
The Variance graph appeared to stop updating after energetic movement. Root cause: the Chart.js Y-axis was hardcoded to `max: 20`. If the physics variance spiked to 50, 80, or 120, the line was rendered completely off-screen above the chart boundary, appearing blank.

*Fix:* Changed `max: 20` to `suggestedMax: 20`. The chart now displays normally during calm periods, and automatically scales up its Y-axis when high variance values occur.

---

**Problem 6 — Single Global Sensitivity Threshold:**
One global Threshold slider controlled all rooms equally. A bathroom (small, high wall reflections) needs a completely different sensitivity than a living room (large, open space).

*Fix:* Moved `threshold` from a class-level variable in `HeadlessBrain` into each `NodeState` object. Added a per-node `Sensitivity Threshold` slider embedded directly inside each room's dashboard card. The WebSocket `set_threshold` command now accepts an optional `node_id` field — if provided, only that room's threshold is updated.

---

**Problem 7 — USB Ports Don't Auto-Appear:**
Plugging in a new ESP32 via USB required the user to manually click through a dummy port first to "trigger" the dashboard to refresh and show the new device.

*Fix:* Added a `_poll_com_ports()` background thread to `headless_brain.py`. It queries `serial.tools.list_ports.comports()` every 2 seconds. If the list of available ports changes, it immediately calls `broadcast_config()` over WebSocket, pushing the updated hardware list to every connected dashboard automatically.

---

## Key Learnings Summary

| # | Lesson |
|---|---|
| 1 | Physics constraints (antenna frequency, line-of-sight) are the most common hardware failure mode |
| 2 | Always declare C buffers as `int8_t`, not `uint8_t`, for signed sensor data |
| 3 | Never block the main Python asyncio loop — use `threading.Thread(daemon=True)` for I/O |
| 4 | Chart.js requires explicit `destroy()` calls before DOM node removal to prevent memory corruption |
| 5 | Microcontrollers (ESP32) should **never** be the target of continuous background UDP traffic from a server |
| 6 | Subnet broadcast (`255.255.255.255`) is more reliable than direct-IP for initial device configuration |
| 7 | `suggestedMax` instead of `max` in Chart.js allows dynamic Y-axis scaling without sacrificing default behavior |
| 8 | Docker containers require `--network host` to access the host machine's localhost services |
| 9 | Eliminate Pandas from any real-time ML hot-path; use raw NumPy arrays instead |
| 10 | Transmitter Target mode must be **Home Router** when using ambient Wi-Fi CSI sniffing — Dedicated Node mode requires a separate TX ESP32 to be powered on |

---

## Current System Status (Phase 4)
- Multi-room monitoring: **Live** (Living Room + Bathroom tested)
- Wireless UDP mode: **Live** with subnet broadcast auto-discovery
- USB Serial mode: **Live** with auto hot-plug detection every 2 seconds
- Per-room AI Threshold: **Live**
- LINE Emergency Notification: **Live** (60s cooldown)
- Global Dashboard: **Live** at `https://csi.ohmpatumwan.com`
- Backend Service: Running as `sentry.service` on the Raspberry Pi 5 (auto-starts on boot)

---

*Report compiled from engineering logs — June 26, 2026*
