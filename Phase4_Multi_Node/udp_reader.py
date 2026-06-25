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
        self.last_client_addr = None

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind(("0.0.0.0", self.port))
            self.sock.settimeout(1.0)
            self.running = True
            self.thread = threading.Thread(target=self._read_loop, daemon=True)
            self.thread.start()
            print(f"[UDPReader] Listening for CSI packets on 0.0.0.0:{self.port}...")
            return True
        except Exception as e:
            print(f"Failed to bind UDP socket to port {self.port}: {e}")
            return False

    def disconnect(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.sock:
            self.sock.close()
            
    def send_command(self, cmd_string):
        if self.sock and self.last_client_addr:
            try:
                self.sock.sendto((cmd_string + '\n').encode('utf-8'), self.last_client_addr)
                return True
            except Exception as e:
                print(f"Failed to send UDP command: {e}")
        return False
            
    def _read_loop(self):
        while self.running and self.sock:
            try:
                data, addr = self.sock.recvfrom(4096)
                self.last_client_addr = addr
                decoded_data = data.decode('utf-8', errors='ignore').strip()
                
                # A single UDP packet might contain a batch of multiple CSI frames separated by newline
                for line in decoded_data.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                        
                    if line.startswith("SOS_ALERT"):
                        parts = line.split(',')
                        location_name = parts[1] if len(parts) > 1 else "Unknown"
                        if self.data_callback:
                            self.data_callback("SOS", 0, location_name, reader_id=addr[0])
                        continue
                        
                    if line.startswith("CSI_DATA"):
                        parts = line.split(',')
                        if len(parts) > 5:
                            location_name = parts[1]
                            rssi = int(parts[3])
                            csi_len = int(parts[4])
                            
                            try:
                                csi_raw = [int(x) for x in parts[5:] if x]
                            except ValueError:
                                continue # Skip corrupted batched lines
                                
                            if len(csi_raw) >= 128:
                                amplitudes = []
                                for i in range(0, 128, 2):
                                    imag = csi_raw[i]
                                    real = csi_raw[i+1]
                                    amp = np.sqrt(imag**2 + real**2)
                                    amplitudes.append(amp)
                                    
                                # Filter the 52 valid data subcarriers
                                valid_amplitudes = amplitudes[1:28] + amplitudes[38:64]
                                
                                if self.data_callback:
                                    self.data_callback(valid_amplitudes, rssi, location_name, reader_id=addr[0])
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"UDP Read error: {e}")
                time.sleep(0.1)
