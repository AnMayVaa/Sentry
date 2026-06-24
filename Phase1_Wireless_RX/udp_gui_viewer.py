import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel
from PyQt6.QtCore import QTimer
import pyqtgraph as pg
import numpy as np

# We import the new UDPReader from Phase2!
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Phase2_Central_Brain')))
from udp_reader import UDPReader

class UDPVisualizerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Phase 1: Wireless UDP CSI Viewer")
        self.resize(800, 600)
        
        self.latest_data = None
        
        self.init_ui()
        
        # Start the UDP Reader on Port 5000
        self.reader = UDPReader(port=5000, data_callback=self.data_received)
        self.reader.connect()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(30)
        
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        self.lbl_status = QLabel("Listening for UDP packets on Port 5000...")
        self.lbl_status.setStyleSheet("font-size: 18px; font-weight: bold; color: #2980b9;")
        layout.addWidget(self.lbl_status)
        
        self.plot_widget = pg.PlotWidget(title="Live Wireless CSI Subcarriers (52 Ch Snapshot)")
        self.plot_widget.setYRange(0, 60) 
        self.plot_widget.setLabel('left', 'Amplitude')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.curve = self.plot_widget.plot(pen=pg.mkPen(color='c', width=2))
        
        layout.addWidget(self.plot_widget)
        
    def data_received(self, amplitudes, rssi):
        if isinstance(amplitudes, str) and amplitudes == "SOS":
            self.lbl_status.setText("🚨 SOS BUTTON PRESSED! 🚨")
            self.lbl_status.setStyleSheet("color: red; font-weight: bold; font-size: 24px;")
            return
            
        self.latest_data = amplitudes
        self.lbl_status.setText(f"Receiving Wireless CSI Data... RSSI: {rssi}")
        self.lbl_status.setStyleSheet("color: green; font-weight: bold; font-size: 18px;")

    def update_plot(self):
        if self.latest_data is not None:
            self.curve.setData(self.latest_data)

    def closeEvent(self, event):
        if self.reader:
            self.reader.disconnect()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = UDPVisualizerApp()
    window.show()
    sys.exit(app.exec())
