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

## Project Structure
- `/control_app`: Contains the legacy Phase 1 Python GUI (`main.py`), ML pipeline (`train_model.py`), and LINE notifier.
- `/Phase2_Central_Brain`: Contains the modern headless Edge Compute backend (`headless_brain.py`) and the responsive Glassmorphism Universal Web UI (`dashboard/index.html`).
- `/tx_node`: ESP32 Transmitter firmware (injects high-speed OFDM packets and acts as the SOS button).
- `/rx_node`: ESP32 Receiver firmware (Promiscuous mode Wi-Fi sniffer).
- `/docs/scripts`: Python scripts for generating academic poster graphs and running the Mycelium Simulator.
- `/docs/images`: Exported data visualization graphs (e.g., CSI Signal Signatures).

## Setup Instructions
1. Flash `tx_node` and `rx_node` onto two separate ESP32 microcontrollers.
2. Install Python requirements in `control_app`: `pip install -r requirements.txt`.
3. Run the backend GUI: `python main.py`.

## Future Work (NSC 2026)
- **TinyML:** Port the Python Random Forest model directly into C++ to run natively on the ESP32 receiver.
- **Mycelium Expansion:** Deploy the biological routing mesh across multi-room environments for whole-house coverage.
