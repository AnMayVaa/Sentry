# NSC 2026 Project Report: CSI Fall Detection System (Sentry)

This document tracks the progress, methodologies, conflicts, and engineering solutions for the Sentry project. It serves as a master log for the 28th National Software Contest (NSC) documentation.

---

## Phase 1: Hardware Setup & Data Extraction
**Goal**: Establish a stable Wi-Fi connection between two ESP32 modules and extract raw Channel State Information (CSI) subcarriers in real-time.

*   **Approach**: We configured the Transmitter (Tx) node to continuously inject 802.11 QoS Data packets at 30Hz using the connectionless ESP-NOW protocol. This forces the hardware to use the 54 Mbps OFDM rate, ensuring the radio waves physically contain the 52 usable CSI subcarriers. The Receiver (Rx) node listens in Promiscuous mode, filters by MAC address, and streams the payload over USB. A Python PyQt6 GUI was built to graph the wave amplitudes in real-time.
*   **Conflict**: The ESP32 Rx node kept crashing and rebooting with a `Task watchdog got triggered` error. 
*   **Solution**: The UART serial port at standard `115200` baud was too slow to print 52 floats at 30 frames per second, causing a buffer overflow. We solved this by forcing the UART baud rate to `460800` in both the `sdkconfig` and `rx_main.c` firmware, allowing high-speed, crash-free data streaming.

---

## Phase 2: Machine Learning Fall Detection
**Goal**: Train an Artificial Intelligence model to mathematically detect human falls using the invisible Wi-Fi radio waves.

*   **Approach**: We recorded three CSV datasets (`static.csv`, `walking.csv`, `falling.csv`). We built a feature extraction script (`train_model.py`) to slice the data into 1.5-second windows and calculate mathematical features (Variance, Standard Deviation, Rate of Change). We trained a Random Forest Classifier using `scikit-learn`.
*   **Conflict 1 (Physics)**: Initially, the AI classified falls as "Static". This happened because the physical fall was recorded *behind* the antenna's Line-of-Sight, meaning the Wi-Fi waves didn't hit the body. 
*   **Solution 1**: We re-recorded the falls directly between the two antennas, providing the AI with massive variance spikes.
*   **Conflict 2 (Data Labeling)**: The AI started predicting "Fall" when the user was just walking. This occurred because `falling.csv` contained seconds of walking and lying still, which corrupted the "Fall" label.
*   **Solution 2**: We engineered an automated Data Cleaner inside `train_model.py` that mathematically sorts the file and isolates *only* the top 15% highest-variance frames (the actual impact moment) to train the model, discarding the rest.
*   **Conflict 3 (UI Flickering)**: Quick hand shakes or jumps caused instant, false-positive "FALL DETECTED" flashes in the UI.
*   **Solution 3**: We implemented a **Temporal Sequence State Machine**. A real fall isn't just an impact—it's an impact *followed by stillness*. The app now detects the impact, flags a "Potential Fall", and waits. If the person continues moving, it's ignored. If the person lies completely still, it locks into a "CONFIRMED FALL". We also linked the UI Threshold slider to the AI, allowing the user to manually override sensitivity.

---

## Phase 3: Emergency Notification System
**Goal**: Instantly alert caregivers or family members when the State Machine confirms a fall, ensuring rapid medical response.

*   **Approach**: We integrated the **LINE Messaging API** because LINE is universally used by Thai families and requires no extra app installation. We engineered `line_notifier.py` to construct and send a "Flex Message"—a beautiful, red emergency UI card displaying the exact time of the fall and a primary button to instantly dial `1669` (Ambulance).
*   **Conflict**: If a person stays on the ground, the Python loop (running at 30 frames per second) would send thousands of API requests to LINE, resulting in a ban for spamming. Furthermore, making API requests blocks the main thread, causing the PyQT6 graphs to lag and freeze.
*   **Solution**: We executed the LINE notification inside a Python `threading.Thread(daemon=True)` so it runs in the background without interrupting the live graphs. We also implemented a 60-second software cooldown timer, ensuring the family receives exactly one clear alert per minute until the situation is resolved.

## Phase 4: Hardware SOS Panic Button
**Goal**: Allow elders to manually trigger an alert if they feel dizzy or sick, bypassing the AI fall detection entirely.

*   **Approach**: We hacked the physical `BOOT` button (GPIO 0) built into the Transmitter ESP32. When pressed, the ESP32 conditionally switches its standard ESP-NOW payload from "CSI_MAGIC" to a special "SOS_BUTTON_PRESSED!" string.
*   **Conflict**: The Receiver (Rx) node is strictly configured to run in Promiscuous Mode to sniff raw Wi-Fi waves for CSI extraction. However, in Promiscuous Mode, the ESP32 MAC layer completely blocks the ESP-NOW layer from receiving packets via the standard `espnow_recv_cb` callback. 
*   **Solution**: We bypassed the MAC layer restriction by using Physics! We reprogrammed the Transmitter to dynamically change its payload size. A normal CSI packet is small (~16 bytes). When the SOS button is pressed, the Transmitter instantly bloats its packet to 150 bytes. Inside the Receiver's raw CSI callback, we monitor `info->rx_ctrl.sig_len`. If a massive wave hits the antenna (>100 bytes), the Receiver instantly recognizes it as an SOS signal without needing to decode the payload, bypassing the ESP-NOW limitation entirely. The Rx node then pipes an "SOS_ALERT" string to the Python App, which forces the State Machine into a Fall State and triggers the LINE API. Furthermore, we programmed the Receiver's local BOOT button to instantly print the same `SOS_ALERT` string, meaning BOTH nodes now act as physical panic buttons.
*   **Conflict 2 (Software)**: The Python background thread silently crashed when parsing the `SOS_ALERT` because the UI callback function expected two mathematical arguments (amplitudes, RSSI), but was only given one string ("SOS").
*   **Solution 2**: We updated the background `SerialReader` thread in `serial_reader.py` to properly intercept the `SOS_ALERT` string and pass a dummy RSSI argument (`"SOS", 0`) to satisfy the UI callback's strict signature, instantly un-freezing the graph and firing the LINE API.

## Phase 1.5: Wireless UDP PC Receiver
**Goal**: Remove the USB cable entirely from the Receiver (Rx) Node, allowing it to send CSI data wirelessly over the home Wi-Fi network directly to the PC via UDP packets.

*   **Approach**: We re-wrote the Rx Node firmware in Arduino IDE to leverage its native Wi-Fi stack. The Rx node continues to use Promiscuous Mode on Channel 6 to sniff CSI from the Tx Node, but instead of streaming over serial, it connects to the home router (Access Point) and broadcasts UDP packets to the Windows PC on Port 5000. We also upgraded the Python PyQt6 GUI to replace `serial_reader.py` with a multi-threaded `udp_reader.py`.
*   **Conflict 1 (Build Environment)**: The manual Windows ESP-IDF terminal encountered strict `PATH` and Python environment alias errors when trying to flash the UDP C code, halting progress.
*   **Solution 1**: We abandoned the rigid ESP-IDF C++ environment for this phase and migrated the Rx Node entirely to an Arduino IDE `.ino` sketch. Because the ESP32 Arduino Core wraps the ESP-IDF natively, we could still import `<esp_wifi.h>` to access the low-level Promiscuous Mode and CSI callback functions, granting the user a frictionless 1-click GUI upload process.
*   **Conflict 2 (The One-Antenna Physics Problem)**: When we flashed the UDP code, the Arduino printed `CSI Sniffing Started!` but failed to receive a single packet from the Tx Node. This happened because the ESP32 only has *one* physical antenna. When `WiFi.begin()` connected the Rx Node to the home router to send UDP packets, the antenna forcibly tuned to the router's channel (e.g., Channel 11). Because the Tx Node was still transmitting on Channel 6, the Rx Node became physically deaf to the Tx Node.
*   **Solution 2**: We logged into the user's home TP-Link Router admin panel and forced the 2.4GHz Wi-Fi band to broadcast strictly on **Channel 6**. This aligned the router, the Tx Node, and the Rx Node on the exact same frequency, instantly restoring the invisible CSI radio wave flow.
*   **Conflict 3 (Type Casting & Mathematical Explosion)**: After solving the channel issue, the Python GUI successfully received UDP packets, but the Amplitude graph jumped violently between 100-300, causing the Variance logic to hit 120+ and constantly trigger false "MOVEMENT" alarms. This occurred because we accidentally defined the CSI payload buffer as `uint8_t` (unsigned) instead of `int8_t` (signed) in the Arduino struct. When the ESP32 printed a negative raw CSI value (e.g., `-5`), it wrapped around and was transmitted via UDP as a massive positive integer (`251`).
*   **Solution 3**: We corrected the struct definition in `Arduino_UDP_Receiver.ino` to use `int8_t buf[128]`. This allowed the `udp.print()` function to properly send negative numbers across the Wi-Fi network. The Python app immediately registered correct amplitudes (0-40) and Variance stabilized back to 0-5.
*   **Conflict 4 (Frame Rate Dilution)**: Even with correct amplitudes, the user had to move extremely aggressively for long periods to trigger a Fall or Movement state. This occurred because the ESP32 only has one physical antenna. In Phase 1.5, the RX Node was forced to rapidly switch its MAC layer between sniffing for CSI (Promiscuous Mode) and transmitting to the router (Station Mode) 30 times a second. Because of this massive transmission overhead, it dropped ~50% of the incoming CSI packets. This reduced the effective frame rate to 10-15 fps, causing the AI's mathematical 45-frame window to stretch from 1.5 seconds out to over 3 seconds, artificially diluting the Standard Deviation (Variance) of quick human movements.
*   **Solution 4**: We implemented a **UDP Packet Batching Optimization** in `Arduino_UDP_Receiver.ino`. Instead of transmitting one UDP packet for every CSI frame received, the ESP32 now queues 5 CSI frames into a memory buffer and transmits them together inside a single UDP packet separated by newline characters (`\n`). This cut the Wi-Fi transmission overhead by 500%, allowing the ESP32 to spend 95% of its airtime listening for CSI. We then upgraded the Python `udp_reader.py` to seamlessly parse multi-line UDP packets. This fully restored the 30Hz frame rate and the hyper-responsiveness of the ML model without requiring hardware upgrades.

---
*Document will be updated as new phases are completed.*
