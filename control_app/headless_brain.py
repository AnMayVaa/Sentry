import sys
import time
import numpy as np
import pandas as pd
import joblib
from collections import Counter
import threading
import serial.tools.list_ports
from serial_reader import SerialReader
from train_model import extract_features
from line_notifier import send_fall_alert

class HeadlessBrain:
    def __init__(self, port, threshold=2.0):
        self.port = port
        self.threshold = threshold
        
        self.history = []
        self.prediction_history = []
        
        self.ml_model = None
        try:
            self.ml_model = joblib.load("fall_detection_model.pkl")
            print("[INFO] Loaded Fall Detection ML model successfully!")
        except Exception as e:
            print(f"[WARNING] Could not load ML model: {e}")
            sys.exit(1)
            
        self.potential_fall_time = 0
        self.last_line_alert_time = 0
        self.current_state = 0 # 0=STATIC, 1=MOVEMENT, 2=FALL
        
        self.reader = SerialReader(self.port, 460800, self.data_received)

    def start(self):
        print(f"[INFO] Connecting to {self.port}...")
        if self.reader.connect():
            print(f"[SUCCESS] Connected to {self.port}! Listening for CSI data...")
            print(f"[INFO] Variance Threshold set to {self.threshold}")
            try:
                while True:
                    time.sleep(1) # Keep main thread alive
            except KeyboardInterrupt:
                print("\n[INFO] Shutting down...")
                self.reader.disconnect()
        else:
            print("[ERROR] Connection failed. Check USB connection and permissions.")

    def data_received(self, amplitudes, rssi):
        current_time = time.time()
        
        # --- PHASE 4: SOS BUTTON INTERRUPT ---
        if isinstance(amplitudes, str) and amplitudes == "SOS":
            print(f"[{time.strftime('%H:%M:%S')}] 🚨 SOS BUTTON PRESSED! 🚨")
            if current_time - self.last_line_alert_time > 60.0:
                print("[ACTION] Sending Emergency LINE Alert...")
                threading.Thread(target=send_fall_alert, daemon=True).start()
                self.last_line_alert_time = current_time
            return

        # Movement Detection Logic
        self.history.append(amplitudes)
        if len(self.history) > 45: # 1.5 seconds at 30Hz
            self.history.pop(0)
            
            # Extract features
            hist_arr = np.array(self.history)
            df_window = pd.DataFrame(hist_arr)
            features = extract_features(df_window)
            
            # Predict
            raw_pred = self.ml_model.predict([features])[0]
            current_variance = features[0]
            
            # --- SENSITIVITY OVERRIDE (NOISE GATE) ---
            if current_variance < self.threshold:
                raw_pred = 0 # Force STATIC
            elif current_variance >= self.threshold and raw_pred == 0:
                raw_pred = 1 # Force MOVEMENT
                
            # Debounce Logic
            self.prediction_history.append(raw_pred)
            if len(self.prediction_history) > 15: # 0.5 seconds buffer
                self.prediction_history.pop(0)
                
            mode_pred = Counter(self.prediction_history).most_common(1)[0][0]
            
            # Sequence State Machine
            if mode_pred == 2:
                self.potential_fall_time = current_time
                
            # Check for confirmed fall (Impact followed by Static)
            if (current_time - self.potential_fall_time < 3.0) and mode_pred == 0:
                if current_time - self.last_line_alert_time > 60.0:
                    print(f"\n[{time.strftime('%H:%M:%S')}] 🚨 FALL DETECTED! CONFIRMED STATIC POSTURE! 🚨")
                    print("[ACTION] Sending Emergency LINE Alert...")
                    threading.Thread(target=send_fall_alert, daemon=True).start()
                    self.last_line_alert_time = current_time
            
            # State Logging (Only print when state changes to avoid spam)
            new_state = 1 if mode_pred == 2 else mode_pred # Don't log momentary 2 as 'fall' unless confirmed
            if current_time - self.last_line_alert_time < 3.0:
                new_state = 2 # Latch fall state for logging
                
            if new_state != self.current_state:
                state_names = {0: "🟢 STATIC", 1: "🟠 MOVEMENT", 2: "🔴 FALL DETECTED"}
                print(f"[{time.strftime('%H:%M:%S')}] STATE CHANGE: {state_names[new_state]} (Var: {current_variance:.2f})")
                self.current_state = new_state

if __name__ == "__main__":
    print("=======================================")
    print(" SENTRY: Edge Computing CSI Processor  ")
    print("=======================================")
    
    # Auto-detect ports if none specified
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("[ERROR] No serial ports found. Is the ESP32 plugged in?")
        sys.exit(1)
        
    # Prefer /dev/ttyUSB0 (Linux) or COM (Windows)
    target_port = ports[0].device
    for p in ports:
        if "USB" in p.device:
            target_port = p.device
            break
            
    brain = HeadlessBrain(port=target_port, threshold=2.0)
    brain.start()
