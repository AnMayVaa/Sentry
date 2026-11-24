# Sentry: Smart Fall Detection System for Elderly in Residential Area Using Intelligent Wi-Fi State Classification

## Overview
Sentry is an intelligent, non-invasive fall detection system designed to monitor elderly individuals in residential areas. Instead of relying on wearable devices or privacy-invasive cameras, Sentry utilizes invisible Wi-Fi Channel State Information (CSI) radio waves to detect human falls with high accuracy. 

The system leverages a Custom Hardware Pipeline (ESP32), a Hybrid Sequence State Machine, and a Random Forest Machine Learning classifier to analyze real-time physics and trigger emergency alerts.

## Key Features
- **Invisible Sensing:** Uses 52 OFDM subcarriers from Wi-Fi CSI to detect movement and falls without cameras.
- **Hardware-Level SOS Panic Button:** Bypasses software MAC layer limitations to instantly trigger SOS alerts by dynamically manipulating physical packet sizes.
- **Machine Learning Integration:** Uses `scikit-learn`'s Random Forest Classifier for ultra-fast, sub-millisecond inference to distinguish between static, walking, and falling states.
- **Mycelium Mesh Routing:** Biologically-inspired intelligent routing protocols to ensure energy-efficient data transmission across a multi-node residential network.
- **LINE Messaging API:** Automatically pushes beautiful, interactive Emergency Cards to caregivers via LINE when a fall is confirmed, complete with a button to dial emergency services (1669).
- **Edge Compute Central Brain:** Deploys a Raspberry Pi 5 acting as a headless ML processor. It hosts a Unified HTTP/WebSocket Server and leverages a persistent Dockerized Cloudflare Tunnel to expose the system globally without opening router ports.
- **Universal Edge Dashboard:** A stunning, dark-mode, responsive web application that renders 15 FPS hardware-accelerated graphs of the mathematical Variance and the raw 52-subcarrier OFDM snapshot. Features a Two-Way syncing control panel to remotely toggle hardware connections ([USB Mode] vs [Wireless UDP Mode]) and adjust AI sensitivity thresholds on the fly from any device.
- **mDNS Auto-Discovery:** The ESP32 receiver dynamically resolves the Raspberry Pi's hostname on the local network, making the wireless UDP system completely immune to DHCP IP address changes.
- **Zero-Lag Architecture:** Pandas overhead was stripped in favor of raw NumPy arrays, and ESP32 UART bottlenecks were removed using single-call buffer writes, allowing 30fps real-time inference without frame backlog.
- **Home Router TX Mode:** Repurposes the existing home Wi-Fi router as the CSI transmitter via persistent UDP stimulation, eliminating the need for a dedicated TX ESP32 node.
- **Alert Station + SOS Button (Phase 8):** Caregiver Alert Stations (ESP32 + buzzer + LED + button) ring together on any fall or SOS, with different rhythms for each. Holding the RX node's button for 2 seconds sends an SOS that reaches the stations directly, even if the Pi or internet is down. 3D-printable enclosures and a desk stand are included.
- **Multi-Node Architecture:** Scales infinitely to support multiple ESP32 receivers across an entire house (e.g., Living Room, Bath Room). Each node features isolated, per-room sensitivity tuning and auto-discovers via UDP subnet broadcasting (`255.255.255.255`) and asynchronous USB polling.

## Project Structure
The current system is **`Phase4_Multi_Node/`** (Pi backend) plus **`Phase8_Next_Phase/`** (ESP32 firmware and enclosures). The other phase folders are earlier versions kept for reference.

- `/Phase4_Multi_Node`: the headless Edge Compute backend that runs on the Pi as `sentry.service`.
  - `headless_brain.py`: CSI processing, ML inference, fall state machine, unified HTTP + WebSocket server (port 8000).
  - `ml_engine.py`: feature extraction and `select_subcarriers()` (the 52 subcarriers the model expects).
  - `udp_reader.py` / `serial_reader.py`: Wi-Fi (UDP 5000) and USB inputs.
  - `line_notifier.py`: LINE Messaging API alerts. `alarm_broadcaster.py`: UDP 5005 broadcasts to the Alert Stations.
  - `dashboard/`: the web dashboard. `tests/`: pytest suite.
- `/Phase8_Next_Phase`: Phase 8 firmware and hardware. Guide: [`docs/Phase8_Alert_Station_SOS_Enclosures.md`](docs/Phase8_Alert_Station_SOS_Enclosures.md).
  - `Phase8_RX_Node/`: RX sensor firmware (CSI + local siren + hold-2s SOS button).
  - `Phase8_Alert_Station/`: caregiver Alert Station firmware (buzzer + LED + button).
  - `firmware_tests/`: runs both sketches on a PC with simulated pins/UDP/time.
  - `enclosures/`: OpenSCAD sources, STL, PNG previews. `previews/`: browser 3D viewer and overview page.
- `/ML_Training_Tools`: training data (`livingroom_data/`), training and analysis scripts.
- `/docs`: reports, setup guides, `scripts/` (poster graphs, Mycelium simulator) and `images/`.
- `config.json` (public settings), `config.local.example.json` (template for secrets), `deploy.py` (pull + restart on the Pi).
- Older versions: `Legacy_Desktop_GUI/`, `Phase1_Wireless_RX/` to `Phase7_Combined_Node/`, `Sentry_NSC_sourcecode/`.

## Setup Instructions
1. **Pi backend:** on the Raspberry Pi, `pip install -r Phase4_Multi_Node/requirements_headless.txt`. Keep the pinned versions: `headless_brain.py` needs `websockets==12.0` (newer versions break the dashboard with HTTP 500), and the model needs `scikit-learn==1.8.0`.
2. **Secrets:** copy `config.local.example.json` to `config.local.json` (git-ignored) and fill in the LINE token, LINE user ID and a `control_token`. See [`docs/LINE_Setup_Guide.md`](docs/LINE_Setup_Guide.md).
3. **Run:** `python Phase4_Multi_Node/headless_brain.py`, or as the `sentry` systemd service. The dashboard is on port 8000 (`/`, WebSocket `/ws`).
4. **Firmware:** in `Phase8_Next_Phase/Phase8_RX_Node/` and `Phase8_Next_Phase/Phase8_Alert_Station/`, copy `secrets.example.h` to `secrets.h`, set your Wi-Fi, set `node_location` per RX node, and upload. The home router is the transmitter; no TX ESP32 is needed.
5. **Tests:** `python -m pytest Phase4_Multi_Node/tests -q` and `bash Phase8_Next_Phase/firmware_tests/run_tests.sh`.
6. **Deploy updates:** `python deploy.py` (SSH key; pulls on the Pi and restarts `sentry`).

## Future Work (NSC 2026)
- **TinyML:** Port the Python Random Forest model directly into C++ to run natively on the ESP32 receiver.
- **Mycelium Expansion:** Deploy the biological routing mesh across multi-room environments for whole-house coverage.
