import sys
print("Starting main.py")
try:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QComboBox, QLabel
    from PyQt6.QtCore import QTimer
    import pyqtgraph as pg
    import numpy as np
    import serial.tools.list_ports
    from serial_reader import SerialReader
    print("Imported everything")
except Exception as e:
    print(f"Import error: {e}")
    sys.exit(1)

class CSIVisualizerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CSI Fall Detection Control App")
        self.resize(1000, 600)
        
        self.reader = None
        self.latest_data = None
        self.ml_model = None
        try:
            import joblib
            self.ml_model = joblib.load("fall_detection_model.pkl")
            print("Loaded Fall Detection ML model!")
        except Exception as e:
            print(f"Could not load ML model (fallback to heuristic): {e}")
            
        self.prediction_history = []
        self.fall_latch_time = 0
        
        self.init_ui()
        
        # Timer for UI updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(30) # ~33fps refresh rate
        
    def init_ui(self):
        from PyQt6.QtWidgets import QDoubleSpinBox
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Control Panel
        control_layout = QHBoxLayout()
        
        self.port_combo = QComboBox()
        self.refresh_ports()
        
        self.btn_refresh = QPushButton("Refresh Ports")
        self.btn_refresh.clicked.connect(self.refresh_ports)
        
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self.toggle_connection)
        
        self.lbl_status = QLabel("Disconnected")
        
        # Data recording controls
        self.btn_record = QPushButton("Start Recording")
        self.btn_record.clicked.connect(self.toggle_recording)
        self.btn_record.setEnabled(False)
        self.is_recording = False
        
        # Movement Detection Controls
        self.history = []
        self.is_moving = False
        self.current_threshold = 1.5
        
        self.spin_threshold = QDoubleSpinBox()
        self.spin_threshold.setRange(0.1, 20.0)
        self.spin_threshold.setSingleStep(0.1)
        self.spin_threshold.setValue(1.5)
        self.spin_threshold.valueChanged.connect(self.update_threshold)
        
        self.lbl_movement = QLabel("STATIC")
        self.lbl_movement.setStyleSheet("background-color: green; color: white; font-size: 20px; font-weight: bold; padding: 5px;")
        
        control_layout.addWidget(QLabel("COM Port:"))
        control_layout.addWidget(self.port_combo)
        control_layout.addWidget(self.btn_refresh)
        control_layout.addWidget(self.btn_connect)
        control_layout.addWidget(self.btn_record)
        control_layout.addWidget(QLabel("Threshold:"))
        control_layout.addWidget(self.spin_threshold)
        control_layout.addWidget(self.lbl_movement)
        control_layout.addWidget(self.lbl_status)
        control_layout.addStretch()
        
        main_layout.addLayout(control_layout)
        
        # Plot
        self.plot_widget = pg.PlotWidget(title="CSI Subcarrier Amplitude")
        self.plot_widget.setYRange(0, 50) # Rough amplitude range, adjust as needed
        self.plot_widget.setLabel('left', 'Amplitude')
        self.plot_widget.setLabel('bottom', 'Subcarrier Index')
        self.curve = self.plot_widget.plot(pen='y')
        
        main_layout.addWidget(self.plot_widget)

    def update_threshold(self, value):
        self.current_threshold = value

    def refresh_ports(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.port_combo.addItem(p.device)
            
    def data_received(self, amplitudes, rssi):
        # --- PHASE 4: SOS BUTTON INTERRUPT ---
        import time
        if isinstance(amplitudes, str) and amplitudes == "SOS":
            self.current_prediction = 2 # Force Fall State
            self.fall_latch_time = time.time()
            self.lbl_movement.setText("STATUS: 🚨 SOS BUTTON PRESSED! 🚨")
            self.lbl_movement.setStyleSheet("color: red; font-size: 32px; font-weight: bold;")
            
            # Trigger LINE Alert for SOS
            current_time = time.time()
            if not hasattr(self, 'last_line_alert_time'):
                self.last_line_alert_time = 0
            if current_time - self.last_line_alert_time > 60.0:
                import threading
                from line_notifier import send_fall_alert
                threading.Thread(target=send_fall_alert, daemon=True).start()
                self.last_line_alert_time = current_time
            return

        # Callback from SerialReader thread
        self.latest_data = amplitudes
        
        # Movement Detection Logic
        self.history.append(amplitudes)
        if len(self.history) > 45: # 45 frames = 1.5 seconds at 30Hz
            self.history.pop(0)
            
            if hasattr(self, 'ml_model') and self.ml_model is not None:
                import pandas as pd
                from train_model import extract_features
                
                # ML Inference
                hist_arr = np.array(self.history)
                df_window = pd.DataFrame(hist_arr)
                features = extract_features(df_window)
                raw_pred = self.ml_model.predict([features])[0]
                
                # --- SENSITIVITY OVERRIDE ---
                # features[0] is the mean standard deviation (variance).
                # If the physical variance exceeds the UI Threshold slider, force the app out of STATIC!
                if features[0] > self.current_threshold and raw_pred == 0:
                    raw_pred = 1 # Force MOVEMENT
                
                # Debounce Logic
                self.prediction_history.append(raw_pred)
                if len(self.prediction_history) > 15: # 0.5 seconds buffer
                    self.prediction_history.pop(0)
                    
                from collections import Counter
                import time
                mode_pred = Counter(self.prediction_history).most_common(1)[0][0]
                
                current_time = time.time()
                
                # Sequence State Machine: A real fall is IMPACT (2) followed by STATIC (0)
                if mode_pred == 2:
                    # Record the time of the high-impact event (but don't alert yet!)
                    if not hasattr(self, 'potential_fall_time'):
                        self.potential_fall_time = current_time
                    self.potential_fall_time = current_time
                    
                # Check if we had an impact in the last 3 seconds, AND the user is now completely STILL (0)
                if hasattr(self, 'potential_fall_time'):
                    if (current_time - self.potential_fall_time < 3.0) and mode_pred == 0:
                        self.fall_latch_time = current_time # CONFIRMED FALL!
                        
                        # --- PHASE 3: LINE NOTIFICATION ---
                        if not hasattr(self, 'last_line_alert_time'):
                            self.last_line_alert_time = 0
                            
                        # 60 second cooldown to prevent API spam
                        if current_time - self.last_line_alert_time > 60.0:
                            import threading
                            from line_notifier import send_fall_alert
                            # Run in a background thread so it doesn't freeze the UI!
                            threading.Thread(target=send_fall_alert, daemon=True).start()
                            self.last_line_alert_time = current_time
                        
                # UI Latching: Keep the FALL alert on screen for 3 seconds
                if time.time() - self.fall_latch_time < 3.0:
                    self.current_prediction = 2
                else:
                    # If they are currently impacting/shaking (2) but haven't gone static yet, 
                    # just show MOVEMENT (1) to prevent flickering false alarms.
                    self.current_prediction = 1 if mode_pred == 2 else mode_pred
            else:
                # Fallback heuristic
                hist_arr = np.array(self.history)
                std_devs = np.std(hist_arr, axis=0)
                mean_std = np.mean(std_devs)
                
                if mean_std > self.current_threshold:
                    self.current_prediction = 1 # Movement
                else:
                    self.current_prediction = 0 # Static
                
        # If recording, save to file
        if self.is_recording and hasattr(self, 'csv_file') and not self.csv_file.closed:
            try:
                # Convert the amplitudes array to a comma-separated string
                line = ",".join(f"{amp:.2f}" for amp in amplitudes)
                import time
                self.csv_file.write(f"{time.time()},{rssi},{line}\n")
            except Exception as e:
                print(f"Error writing to CSV: {e}")

    def update_plot(self):
        if self.latest_data is not None:
            self.curve.setData(self.latest_data)
            
        if hasattr(self, 'current_prediction'):
            if self.current_prediction == 2:
                self.lbl_movement.setText("FALL DETECTED!")
                self.lbl_movement.setStyleSheet("background-color: red; color: white; font-size: 24px; font-weight: bold; padding: 10px;")
            elif self.current_prediction == 1:
                self.lbl_movement.setText("MOVEMENT")
                self.lbl_movement.setStyleSheet("background-color: orange; color: black; font-size: 20px; font-weight: bold; padding: 5px;")
            else:
                self.lbl_movement.setText("STATIC")
                self.lbl_movement.setStyleSheet("background-color: green; color: white; font-size: 20px; font-weight: bold; padding: 5px;")

    def toggle_connection(self):
        if self.reader and self.reader.running:
            if self.is_recording:
                self.toggle_recording() # Ensure recording stops if we disconnect
            self.reader.disconnect()
            self.btn_connect.setText("Connect")
            self.lbl_status.setText("Disconnected")
            self.btn_record.setEnabled(False)
        else:
            port = self.port_combo.currentText()
            if not port:
                return
            
            self.reader = SerialReader(port, 460800, self.data_received)
            if self.reader.connect():
                self.btn_connect.setText("Disconnect")
                self.lbl_status.setText(f"Connected to {port}")
                self.btn_record.setEnabled(True)
            else:
                self.lbl_status.setText("Connection Failed")

    def toggle_recording(self):
        import time
        import os
        self.is_recording = not self.is_recording
        if self.is_recording:
            # Create data directory if it doesn't exist
            os.makedirs("data", exist_ok=True)
            filename = f"data/csi_record_{int(time.time())}.csv"
            try:
                self.csv_file = open(filename, "w")
                # Write header: timestamp, rssi, subcarrier_1...subcarrier_52
                headers = ["timestamp", "rssi"] + [f"sub_{i}" for i in range(1, 53)]
                self.csv_file.write(",".join(headers) + "\n")
                
                self.btn_record.setText("Stop Recording")
                self.btn_record.setStyleSheet("background-color: red; color: white;")
                self.lbl_status.setText(f"Recording to {filename}")
            except Exception as e:
                print(f"Failed to open file: {e}")
                self.is_recording = False
        else:
            self.btn_record.setText("Start Recording")
            self.btn_record.setStyleSheet("")
            self.lbl_status.setText(f"Connected to {self.port_combo.currentText()}")
            if hasattr(self, 'csv_file') and not self.csv_file.closed:
                self.csv_file.close()

if __name__ == "__main__":
    import time
    app = QApplication(sys.argv)
    window = CSIVisualizerApp()
    window.show()
    sys.exit(app.exec())
