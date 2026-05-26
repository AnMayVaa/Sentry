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

---
*Document will be updated as new phases are completed.*
