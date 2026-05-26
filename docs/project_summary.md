# Wi-Fi CSI Fall Detection System
**Project Summary & Innovation Roadmap**

## 1. Project Overview & Innovation
The goal of this project is to create a non-intrusive, privacy-preserving **Fall Detection System** without the need for cameras, microphones, or wearable devices. 

**The Innovation:** We are utilizing **Wi-Fi Channel State Information (CSI)**. When Wi-Fi signals travel between two antennas, they bounce off walls, furniture, and humans (multipath fading). By extracting the microscopic CSI data from off-the-shelf ESP32 microcontrollers, we can mathematically "see" the shape of the environment. When a human walks or falls through the invisible Wi-Fi waves, it creates a unique, measurable ripple in the subcarrier amplitudes.

---

## 2. What We Have Achieved So Far (Phase 1)
We have successfully built the hardware pipeline, established stable data extraction, and proved the physics of movement detection.

*   **Custom Transmitter (Tx) Node:** 
    *   Programmed an ESP32 to bypass standard Wi-Fi protocols and inject raw OFDM Data frames at a high-speed **30 Hz sampling rate**. This high frequency is critical to capturing the split-second dynamics of a human fall.
*   **Custom Receiver (Rx) Node:** 
    *   Programmed a second ESP32 in Promiscuous Mode to intercept the Tx packets and extract the 52 subcarrier amplitudes of the CSI matrix. 
    *   Optimized the hardware to stream data over UART at an ultra-fast **460800 baud rate** to prevent CPU watchdog crashes during high-speed data collection.
*   **Real-Time Visualization & Control App:** 
    *   Built a Python GUI (PyQt6 + PyQtGraph) that visualizes the invisible Wi-Fi waves in real-time.
    *   Implemented a mathematical **Heuristic Movement Detector** that calculates the standard deviation of subcarriers over a 1.5-second sliding window to successfully flag general human movement vs. an empty room.
    *   Built a CSV Data Logger to seamlessly record continuous CSI streams for Machine Learning.

---

## 3. Future Plan (Phase 2 & 3)
To evolve the system from general "Movement Detection" to accurate "Fall Detection", we will implement an AI pipeline.

*   **Step 1: Dataset Collection**
    *   Use the existing Control App to record structured CSV datasets of three specific scenarios: *Walking*, *Static (Empty Room)*, and *Falling*.
*   **Step 2: Feature Engineering**
    *   Process the CSV data in Python to extract mathematical features. A fall produces a very specific physical signature: a sudden, massive spike in variance followed by complete stillness (impact and lie still). Walking produces continuous, rhythmic variance. 
*   **Step 3: Machine Learning Model Training**
    *   Train a lightweight classifier (e.g., Random Forest or Support Vector Machine) using `scikit-learn` to recognize the unique signature of a fall based on the engineered features.
*   **Step 4: Real-Time AI Inference**
    *   Integrate the trained Machine Learning model (`.pkl` file) directly into the Python Control App. The app will feed the live 30Hz CSI data into the model and flash a dedicated **"FALL DETECTED!"** alert the moment a fall occurs.
