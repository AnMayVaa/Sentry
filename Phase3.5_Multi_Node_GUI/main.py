import sys
import locale
import time
from collections import deque, Counter
import threading

locale.setlocale(locale.LC_ALL, 'C') # Force English numerals

try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                                 QWidget, QPushButton, QComboBox, QLabel, QGroupBox, 
                                 QScrollArea, QDoubleSpinBox, QRadioButton, QButtonGroup, QFrame)
    from PyQt6.QtCore import QTimer, Qt
    import pyqtgraph as pg
    import numpy as np
    import pandas as pd
    import serial.tools.list_ports
    import joblib
    
    from serial_reader import SerialReader
    from udp_reader import UDPReader
    from ml_engine import extract_features_np
    from line_notifier import send_fall_alert
except Exception as e:
    print(f"Import error: {e}")
    sys.exit(1)

class NodeState:
    def __init__(self, location_name):
        self.location_name = location_name
        self.history = deque(maxlen=45)
        self.prediction_history = deque(maxlen=15)
        self.frame_count = 0
        self._processing = False
        
        self.potential_fall_time = 0
        self.last_line_alert_time = 0
        self.current_state = 0 # 0=STATIC, 1=MOVEMENT, 2=FALL
        self.last_variance = 0.0
        self.latest_amplitudes = np.zeros(52)
        
        self.variance_buffer_size = 150
        self.variance_history = np.zeros(self.variance_buffer_size)

class NodeCardUI(QGroupBox):
    def __init__(self, location_name):
        super().__init__(f"📍 LOCATION: {location_name.upper()}")
        self.setStyleSheet("QGroupBox { font-weight: bold; font-size: 16px; border: 2px solid #ccc; border-radius: 8px; margin-top: 15px; } QGroupBox::title { subcontrol-origin: margin; left: 15px; padding: 0 5px; color: #2980b9; }")
        
        layout = QVBoxLayout()
        
        # --- Top Row: Status and Metric ---
        top_row = QHBoxLayout()
        
        self.lbl_status = QLabel("STATIC")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("background-color: #27ae60; color: white; font-size: 24px; font-weight: bold; padding: 15px; border-radius: 5px;")
        top_row.addWidget(self.lbl_status, stretch=2)
        
        metric_box = QVBoxLayout()
        self.lbl_var_val = QLabel("0.00")
        self.lbl_var_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_var_val.setStyleSheet("font-size: 32px; font-weight: bold; color: #e67e22;")
        lbl_var_title = QLabel("Temporal Variance")
        lbl_var_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_var_title.setStyleSheet("font-size: 12px; color: #7f8c8d; font-weight: bold;")
        metric_box.addWidget(lbl_var_title)
        metric_box.addWidget(self.lbl_var_val)
        
        top_row.addLayout(metric_box, stretch=1)
        layout.addLayout(top_row)
        
        # --- Bottom Row: Charts ---
        charts_row = QHBoxLayout()
        
        self.variance_plot = pg.PlotWidget(title="Live Motion Index (Temporal Variance)")
        self.variance_plot.setYRange(0, 20)
        self.variance_plot.setMinimumHeight(200)
        self.variance_plot.showGrid(x=True, y=True, alpha=0.3)
        self.variance_curve = self.variance_plot.plot(pen=pg.mkPen(color='r', width=2))
        self.thresh_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('y', width=2, style=Qt.PenStyle.DashLine))
        self.thresh_line.setValue(2.0)
        self.variance_plot.addItem(self.thresh_line)
        charts_row.addWidget(self.variance_plot)
        
        self.raw_plot = pg.PlotWidget(title="Raw CSI Subcarriers (52 Ch)")
        self.raw_plot.setYRange(0, 50)
        self.raw_plot.setMinimumHeight(200)
        self.raw_plot.showGrid(x=True, y=True, alpha=0.3)
        self.raw_curve = self.raw_plot.plot(pen=pg.mkPen(color='c', width=2))
        charts_row.addWidget(self.raw_plot)
        
        layout.addLayout(charts_row)
        self.setLayout(layout)
        
    def update_ui(self, state, variance, thresh, var_hist, raw_amps):
        # Update labels
        if state == 2:
            self.lbl_status.setText("FALL DETECTED!")
            self.lbl_status.setStyleSheet("background-color: #c0392b; color: white; font-size: 24px; font-weight: bold; padding: 15px; border-radius: 5px;")
        elif state == 1:
            self.lbl_status.setText("MOVEMENT")
            self.lbl_status.setStyleSheet("background-color: #f39c12; color: white; font-size: 24px; font-weight: bold; padding: 15px; border-radius: 5px;")
        else:
            self.lbl_status.setText("STATIC")
            self.lbl_status.setStyleSheet("background-color: #27ae60; color: white; font-size: 24px; font-weight: bold; padding: 15px; border-radius: 5px;")
            
        self.lbl_var_val.setText(f"{variance:.2f}")
        
        # Update Threshold Line
        self.thresh_line.setValue(thresh)
        
        # Update Plots
        self.variance_curve.setData(var_hist)
        self.raw_curve.setData(raw_amps)

class MultiNodeCSIVisualizerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sentry Multi-Node Edge Control")
        self.resize(1200, 800)
        
        self.reader = None
        self.nodes = {} # location_name -> NodeState
        self.node_uis = {} # location_name -> NodeCardUI
        
        self.ml_model = None
        try:
            self.ml_model = joblib.load("fall_detection_model.pkl")
            print("Loaded Fall Detection ML model!")
        except Exception as e:
            print(f"Could not load ML model: {e}")
            
        self.current_threshold = 2.0
        
        self.init_ui()
        
        # Timer for UI updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plots)
        self.timer.start(33) # ~30fps refresh rate
        
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # --- LEFT PANEL: CONTROLS ---
        left_panel = QVBoxLayout()
        left_panel.setContentsMargins(10, 10, 10, 10)
        left_panel.setSpacing(15)
        
        # 1. Connection Group
        conn_group = QGroupBox("1. Hardware Connection")
        conn_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        conn_layout = QVBoxLayout()
        
        self.mode_group = QButtonGroup()
        self.radio_usb = QRadioButton("USB Serial")
        self.radio_udp = QRadioButton("Wireless UDP (Router)")
        self.radio_usb.setChecked(True)
        self.mode_group.addButton(self.radio_usb)
        self.mode_group.addButton(self.radio_udp)
        
        self.radio_usb.toggled.connect(self.on_mode_changed)
        
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.radio_usb)
        mode_row.addWidget(self.radio_udp)
        conn_layout.addLayout(mode_row)
        
        # Port Selection
        self.port_row = QWidget()
        port_layout = QHBoxLayout(self.port_row)
        port_layout.setContentsMargins(0,0,0,0)
        port_layout.addWidget(QLabel("COM Port:"))
        self.port_combo = QComboBox()
        self.refresh_ports()
        port_layout.addWidget(self.port_combo)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh_ports)
        port_layout.addWidget(self.btn_refresh)
        conn_layout.addWidget(self.port_row)
        
        self.btn_connect = QPushButton("Connect Receiver")
        self.btn_connect.setMinimumHeight(40)
        self.btn_connect.setStyleSheet("background-color: #2980b9; color: white; font-weight: bold; font-size: 14px; border-radius: 4px;")
        self.btn_connect.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.btn_connect)
        
        self.lbl_status = QLabel("Status: Disconnected")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        conn_layout.addWidget(self.lbl_status)
        conn_group.setLayout(conn_layout)
        left_panel.addWidget(conn_group)
        
        # 2. Sensitivity Settings
        ai_group = QGroupBox("2. Gatekeeper Threshold")
        ai_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        ai_layout = QVBoxLayout()
        
        thresh_row = QHBoxLayout()
        thresh_row.addWidget(QLabel("Variance Threshold:"))
        self.spin_threshold = QDoubleSpinBox()
        self.spin_threshold.setRange(0.1, 20.0)
        self.spin_threshold.setSingleStep(0.1)
        self.spin_threshold.setValue(2.0)
        self.spin_threshold.valueChanged.connect(self.update_threshold)
        thresh_row.addWidget(self.spin_threshold)
        ai_layout.addLayout(thresh_row)
        ai_group.setLayout(ai_layout)
        left_panel.addWidget(ai_group)
        
        # Quick Guide
        guide_label = QLabel(
            "<h3>Quick Guide (Multi-Node)</h3>"
            "<ul>"
            "<li><b>ESP32s:</b> Flash God Firmware with unique <code>node_location</code> strings.</li>"
            "<li><b>Connect:</b> Choose USB (Dedicated Node) or UDP (Router) mode.</li>"
            "<li><b>Nodes:</b> New locations will spawn graph cards automatically.</li>"
            "<li><b>Test Fall:</b> Impact followed by 3s static triggers LINE Alert!</li>"
            "</ul>"
        )
        guide_label.setWordWrap(True)
        guide_label.setStyleSheet("background-color: #ecf0f1; padding: 15px; border-radius: 5px;")
        left_panel.addWidget(guide_label)
        
        left_panel.addStretch()
        
        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        left_widget.setFixedWidth(350)
        main_layout.addWidget(left_widget)
        
        # --- RIGHT PANEL: SCROLLABLE NODE CARDS ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; }")
        
        self.nodes_container = QWidget()
        self.nodes_layout = QVBoxLayout(self.nodes_container)
        self.nodes_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Add a placeholder
        self.placeholder = QLabel("Waiting for ESP32 Nodes to connect and transmit data...")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet("color: #7f8c8d; font-size: 18px; font-weight: bold; margin-top: 50px;")
        self.nodes_layout.addWidget(self.placeholder)
        
        self.scroll_area.setWidget(self.nodes_container)
        main_layout.addWidget(self.scroll_area, 1)

    def on_mode_changed(self):
        if self.radio_usb.isChecked():
            self.port_row.setVisible(True)
        else:
            self.port_row.setVisible(False)

    def update_threshold(self, value):
        self.current_threshold = value

    def refresh_ports(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.port_combo.addItem(p.device)
            
    def data_received(self, amplitudes, rssi, location_name="Unknown"):
        current_time = time.time()
        
        # Initialize Node if it doesn't exist
        if location_name not in self.nodes:
            self.nodes[location_name] = NodeState(location_name)
            # Create UI in the main thread (thread-safe using QTimer, but doing it directly here might be risky. 
            # We'll just set a flag and let update_plots build the UI)
            
        node = self.nodes[location_name]
        
        # --- PHASE 4: SOS BUTTON INTERRUPT ---
        if isinstance(amplitudes, str) and amplitudes == "SOS":
            print(f"[{time.strftime('%H:%M:%S')}] 🚨 SOS BUTTON PRESSED IN {location_name}! 🚨")
            node.current_state = 2 # Force fall
            node.potential_fall_time = current_time # Latch it
            if current_time - node.last_line_alert_time > 60.0:
                threading.Thread(target=send_fall_alert, args=(location_name,), daemon=True).start()
                node.last_line_alert_time = current_time
            return

        if node._processing:
            return
        node._processing = True
        
        try:
            node.history.append(amplitudes)
            node.frame_count += 1
            node.latest_amplitudes = amplitudes
            
            current_variance = node.last_variance
            
            if len(node.history) >= 45:
                # Run ML inference every 2nd frame (15Hz)
                if node.frame_count % 2 == 0:
                    hist_arr = np.array(node.history)
                    features = extract_features_np(hist_arr)
                    
                    if self.ml_model is not None:
                        raw_pred = int(self.ml_model.predict([features])[0])
                        current_variance = float(features[0])
                        node.last_variance = current_variance
                        
                        # --- SENSITIVITY OVERRIDE (GATEKEEPER) ---
                        if current_variance < self.current_threshold:
                            raw_pred = 0
                        elif current_variance >= self.current_threshold and raw_pred == 0:
                            raw_pred = 1
                            
                        node.prediction_history.append(raw_pred)
                        mode_pred = Counter(node.prediction_history).most_common(1)[0][0]
                        
                        # Sequence State Machine
                        if mode_pred == 2:
                            node.potential_fall_time = current_time
                            
                        if (current_time - node.potential_fall_time < 3.0) and mode_pred == 0:
                            if current_time - node.last_line_alert_time > 60.0:
                                print(f"\n[{time.strftime('%H:%M:%S')}] 🚨 FALL DETECTED IN {location_name}! 🚨")
                                threading.Thread(target=send_fall_alert, args=(location_name,), daemon=True).start()
                                node.last_line_alert_time = current_time
                        
                        new_state = 1 if mode_pred == 2 else mode_pred 
                        if current_time - node.last_line_alert_time < 3.0:
                            new_state = 2 
                            
                        node.current_state = new_state
            
            # Update visual variance buffer
            node.variance_history[:-1] = node.variance_history[1:]
            node.variance_history[-1] = current_variance
                
        finally:
            node._processing = False

    def update_plots(self):
        # 1. Spawn new UI cards if necessary (doing this in main thread is safe)
        for loc, node in self.nodes.items():
            if loc not in self.node_uis:
                # Remove placeholder if it exists
                if self.placeholder:
                    self.placeholder.setParent(None)
                    self.placeholder = None
                    
                ui_card = NodeCardUI(loc)
                self.node_uis[loc] = ui_card
                self.nodes_layout.addWidget(ui_card)
        
        # 2. Update existing UI cards
        for loc, node in self.nodes.items():
            if loc in self.node_uis:
                self.node_uis[loc].update_ui(
                    node.current_state,
                    node.last_variance,
                    self.current_threshold,
                    node.variance_history,
                    node.latest_amplitudes
                )

    def toggle_connection(self):
        if self.reader and getattr(self.reader, 'running', False):
            self.reader.disconnect()
            self.btn_connect.setText("Connect Receiver")
            self.btn_connect.setStyleSheet("background-color: #2980b9; color: white; font-weight: bold; font-size: 14px; border-radius: 4px;")
            self.lbl_status.setText("Disconnected")
            self.radio_usb.setEnabled(True)
            self.radio_udp.setEnabled(True)
        else:
            if self.radio_usb.isChecked():
                port = self.port_combo.currentText()
                if not port:
                    return
                self.reader = SerialReader(port, 460800, self.data_received)
                if self.reader.connect():
                    self.btn_connect.setText("Disconnect")
                    self.btn_connect.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; font-size: 14px; border-radius: 4px;")
                    self.lbl_status.setText(f"Connected to {port}")
                    self.radio_usb.setEnabled(False)
                    self.radio_udp.setEnabled(False)
                else:
                    self.lbl_status.setText("Connection Failed")
            else:
                self.reader = UDPReader(5000, self.data_received)
                if self.reader.connect():
                    self.btn_connect.setText("Disconnect")
                    self.btn_connect.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; font-size: 14px; border-radius: 4px;")
                    self.lbl_status.setText(f"Listening on UDP 5000")
                    self.radio_usb.setEnabled(False)
                    self.radio_udp.setEnabled(False)
                else:
                    self.lbl_status.setText("UDP Bind Failed")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MultiNodeCSIVisualizerApp()
    window.show()
    sys.exit(app.exec())
