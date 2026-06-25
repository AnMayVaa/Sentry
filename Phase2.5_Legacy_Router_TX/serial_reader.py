import serial
import threading
import time
import numpy as np

class SerialReader:
    def __init__(self, port, baudrate=115200, data_callback=None):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False
        self.thread = None
        self.data_callback = data_callback

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            self.running = True
            self.thread = threading.Thread(target=self._read_loop, daemon=True)
            self.thread.start()
            return True
        except Exception as e:
            print(f"Failed to connect to {self.port}: {e}")
            return False

    def disconnect(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.ser and self.ser.is_open:
            self.ser.close()
            
    def _read_loop(self):
        while self.running and self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                
                if line.startswith("SOS_ALERT"):
                    if self.data_callback:
                        self.data_callback("SOS", 0)
                    continue
                
                if line.startswith("ESP32_IP,"):
                    parts = line.split(",")
                    if len(parts) >= 2:
                        ip_str = parts[1].strip()
                        if self.data_callback:
                            self.data_callback("IP", ip_str)
                    continue
                    
                if line.startswith("CSI_DATA"):
                    parts = line.split(',')
                    if len(parts) > 4:
                        # Format: CSI_DATA, mac, rssi, len, buf0, buf1...
                        rssi = int(parts[2])
                        csi_len = int(parts[3])
                        csi_raw = [int(x) for x in parts[4:] if x]
                        
                        # Calculate amplitude for the 64 subcarriers
                        if len(csi_raw) >= 128:
                            amplitudes = []
                            for i in range(0, 128, 2):
                                imag = csi_raw[i]
                                real = csi_raw[i+1]
                                amp = np.sqrt(imag**2 + real**2)
                                amplitudes.append(amp)
                                
                            # ESP32 802.11n HT20 subcarrier mapping:
                            # Index 0: DC subcarrier (massive spike/noise)
                            # Index 1-27: Positive subcarriers
                            # Index 28-37: Null/Guard subcarriers (zero dip)
                            # Index 38-63: Negative subcarriers
                            # We filter out the bad ones to keep the 52 usable data subcarriers!
                            valid_amplitudes = amplitudes[1:28] + amplitudes[38:64]
                            
                            if self.data_callback:
                                self.data_callback(valid_amplitudes, rssi)
                        else:
                            print(f"Skipping packet, CSI length too short: {len(csi_raw)}")
            except Exception as e:
                print(f"Read error: {e}")
                time.sleep(0.1)
