import socket
import threading
import time
import numpy as np

class UDPReader:
    def __init__(self, port=5000, data_callback=None):
        self.port = port
        self.sock = None
        self.running = False
        self.thread = None
        self.data_callback = data_callback

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind(('0.0.0.0', self.port))
            # Set a timeout so the read loop can exit cleanly if stopped
            self.sock.settimeout(1.0)
            self.running = True
            self.thread = threading.Thread(target=self._read_loop, daemon=True)
            self.thread.start()
            print(f"[UDPReader] Listening for ESP32 Wi-Fi packets on UDP port {self.port}...")
            return True
        except Exception as e:
            print(f"[UDPReader] Failed to bind to UDP port {self.port}: {e}")
            return False

    def disconnect(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.sock:
            self.sock.close()
            
    def _read_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                line = data.decode('utf-8', errors='ignore').strip()
                
                if line.startswith("SOS_ALERT"):
                    if self.data_callback:
                        self.data_callback("SOS", 0)
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
                                
                            # ESP32 802.11n HT20 subcarrier mapping
                            valid_amplitudes = amplitudes[1:28] + amplitudes[38:64]
                            
                            if self.data_callback:
                                self.data_callback(valid_amplitudes, rssi)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Read error: {e}")
                time.sleep(0.1)
