# CSI Fall Detection: Hardware Setup Manual

This guide will walk you through setting up the two ESP32-WROOM-32U boards to collect Channel State Information (CSI) for fall detection.

## 1. Hardware Assembly

**Transmitter (Tx) Node:**
1. Take one of the ESP32-WROOM-32U boards.
2. Carefully snap the IPEX end of the SMA-to-IPEX adapter cable onto the small gold IPEX connector on the ESP32 module. **Warning:** These connectors are fragile; press straight down until it clicks.
3. Screw the 2.4GHz external antenna onto the SMA connector.
4. (Optional) Secure the SMA pigtail to the board or a case so that pulling the antenna doesn't rip off the IPEX connector.

**Receiver (Rx) Node:**
1. Repeat the exact same process (steps 1-3) for the second ESP32-WROOM-32U board.

## 2. Environment Deployment

To maximize the line of sight for body-level detection and capture multi-path reflections accurately:

- **Positioning:** Place the Tx and Rx nodes at opposite corners of the room where you will be performing the data collection.
- **Height:** Mount both antennas vertically at a height of **0.8 to 1.0 meters** above the floor. This is roughly the height of a person's center of mass, making it ideal for detecting falls (which transition from 1m to 0m).
- **Clearance:** Ensure there are no large metal objects immediately blocking the antennas (e.g., metal cabinets within 1 foot).

## 3. Power and Connectivity

- **Tx Node:** Connect the Micro USB cable to the Tx board and plug it into a standard **5V USB Wall Adapter**. Using a wall adapter provides cleaner and more stable power than a battery bank, which is critical for maintaining a stable RF transmission signal.
- **Rx Node:** Connect the Micro USB cable to the Rx board and plug the other end directly into your **Host PC (Laptop/Desktop)**. This connection serves both as power and as the high-speed serial data link to capture the CSI data stream.

## 4. Next Steps
Once the hardware is positioned and powered:
1. Note the COM ports (on Windows) or `/dev/ttyUSBx` paths (on Linux/Mac) that appear when you plug the boards into your PC for flashing.
2. Proceed to compile and flash the `tx_node` firmware to the wall-powered ESP32, and the `rx_node` firmware to the PC-connected ESP32.
