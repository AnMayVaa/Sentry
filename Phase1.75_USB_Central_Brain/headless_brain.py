import sys
import os
import time
import json
import numpy as np
import pandas as pd
import joblib
from collections import Counter
import threading
import asyncio
import websockets
import http.server
import socketserver

import serial.tools.list_ports
from serial_reader import SerialReader
from ml_engine import extract_features
from line_notifier import send_fall_alert

# Load Config
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
try:
    with open(CONFIG_PATH, "r") as f:
        global_config = json.load(f)
except Exception as e:
    print(f"Error loading config.json: {e}")
    global_config = {"ai_settings": {"variance_threshold": 2.0}, "networking": {"websocket_port": 8765, "http_port": 8000}}

# --- CONFIGURATION ---
THRESHOLD = global_config["ai_settings"]["variance_threshold"]
WS_PORT = global_config["networking"]["websocket_port"]
HTTP_PORT = global_config["networking"]["http_port"]

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
        
        # IoT Server Variables
        self.connected_clients = set()
        self.loop = None

    # --- WEBSOCKET SERVER LOGIC ---
    async def ws_handler(self, websocket):
        self.connected_clients.add(websocket)
        print(f"[IOT] New Web Dashboard Connected! ({len(self.connected_clients)} total)")
        
        # Send initial configuration
        ports = [p.device for p in serial.tools.list_ports.comports()]
        init_msg = json.dumps({
            "type": "config",
            "threshold": self.threshold,
            "port": self.port,
            "available_ports": ports
        })
        try:
            await websocket.send(init_msg)
        except:
            pass

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get("command") == "set_threshold":
                        self.threshold = float(data.get("value", 2.0))
                        print(f"[IOT] Threshold updated to {self.threshold}")
                    elif data.get("command") == "set_port":
                        new_port = data.get("port")
                        print(f"[IOT] Switching COM port to {new_port}...")
                        self.port = new_port
                        self.reader.disconnect()
                        self.reader = SerialReader(self.port, 460800, self.data_received)
                        if self.reader.connect():
                            print(f"[IOT] Successfully reconnected to {self.port}")
                        else:
                            print(f"[IOT] Failed to connect to {self.port}")
                    elif data.get("command") == "get_config":
                        ports = [p.device for p in serial.tools.list_ports.comports()]
                        cfg_msg = json.dumps({
                            "type": "config",
                            "threshold": self.threshold,
                            "port": self.port,
                            "available_ports": ports
                        })
                        await websocket.send(cfg_msg)
                except Exception as e:
                    print(f"[IOT] Error parsing command: {e}")
        finally:
            self.connected_clients.remove(websocket)
            print(f"[IOT] Web Dashboard Disconnected. ({len(self.connected_clients)} remaining)")

    async def broadcast_ws(self, payload):
        if self.connected_clients:
            message = json.dumps(payload)
            websockets.broadcast(self.connected_clients, message)

    async def _ws_main(self):
        async with websockets.serve(self.ws_handler, "0.0.0.0", 8765):
            await asyncio.Future()

    def start_ws_server(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        print("[INFO] WebSocket Server running on port 8765")
        try:
            self.loop.run_until_complete(self._ws_main())
        except asyncio.CancelledError:
            pass

    # --- HTTP SERVER LOGIC ---
    def start_http_server(self):
        # Serve the /dashboard folder
        dashboard_dir = os.path.join(os.path.dirname(__file__), 'dashboard')
        os.chdir(dashboard_dir)
        handler = http.server.SimpleHTTPRequestHandler
        # Handle Address already in use
        socketserver.TCPServer.allow_reuse_address = True
        try:
            with socketserver.TCPServer(("0.0.0.0", 8000), handler) as httpd:
                print("[INFO] HTTP Dashboard serving at port 8000 (Open this in your iPad/Phone)")
                httpd.serve_forever()
        except Exception as e:
            print(f"[ERROR] HTTP Server failed to start: {e}")

    # --- MAIN STARTUP ---
    def start(self):
        print(f"[INFO] Connecting to {self.port}...")
        if self.reader.connect():
            print(f"[SUCCESS] Connected to {self.port}! Listening for CSI data...")
            
            # Start HTTP Server in background thread
            threading.Thread(target=self.start_http_server, daemon=True).start()
            
            # Start WebSocket Server in main thread (blocks forever)
            try:
                self.start_ws_server()
            except KeyboardInterrupt:
                print("\n[INFO] Shutting down...")
                self.reader.disconnect()
        else:
            print("[ERROR] Connection failed. Check USB connection and permissions.")

    # --- CSI DATA PROCESSING ---
    def data_received(self, amplitudes, rssi):
        current_time = time.time()
        
        # --- PHASE 4: SOS BUTTON INTERRUPT ---
        if isinstance(amplitudes, str) and amplitudes == "SOS":
            print(f"[{time.strftime('%H:%M:%S')}] 🚨 SOS BUTTON PRESSED! 🚨")
            if current_time - self.last_line_alert_time > 60.0:
                threading.Thread(target=send_fall_alert, daemon=True).start()
                self.last_line_alert_time = current_time
            return

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
            
            # --- SENSITIVITY OVERRIDE ---
            if current_variance > self.threshold and raw_pred == 0:
                raw_pred = 1 # Force MOVEMENT
                
            # Debounce Logic
            self.prediction_history.append(raw_pred)
            if len(self.prediction_history) > 15:
                self.prediction_history.pop(0)
                
            mode_pred = Counter(self.prediction_history).most_common(1)[0][0]
            
            # Sequence State Machine
            if mode_pred == 2:
                self.potential_fall_time = current_time
                
            if (current_time - self.potential_fall_time < 3.0) and mode_pred == 0:
                if current_time - self.last_line_alert_time > 60.0:
                    print(f"\n[{time.strftime('%H:%M:%S')}] 🚨 FALL DETECTED! CONFIRMED STATIC POSTURE! 🚨")
                    threading.Thread(target=send_fall_alert, daemon=True).start()
                    self.last_line_alert_time = current_time
            
            new_state = 1 if mode_pred == 2 else mode_pred 
            if current_time - self.last_line_alert_time < 3.0:
                new_state = 2 
                
            if new_state != self.current_state:
                state_names = {0: "🟢 STATIC", 1: "🟠 MOVEMENT", 2: "🔴 FALL DETECTED"}
                print(f"[{time.strftime('%H:%M:%S')}] STATE CHANGE: {state_names[new_state]} (Var: {current_variance:.2f})")
                self.current_state = new_state

            # --- IOT BROADCAST ---
            if self.loop and self.loop.is_running():
                payload = {
                    "state": self.current_state,
                    "variance": current_variance,
                    "threshold": self.threshold,
                    "amplitudes": amplitudes
                }
                asyncio.run_coroutine_threadsafe(self.broadcast_ws(payload), self.loop)

if __name__ == "__main__":
    print("=======================================")
    print(" SENTRY: IoT Web Server Processor      ")
    print("=======================================")
    
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("[ERROR] No serial ports found. Is the ESP32 plugged in?")
        sys.exit(1)
        
    target_port = ports[0].device
    for p in ports:
        if "USB" in p.device:
            target_port = p.device
            break
            
    brain = HeadlessBrain(port=target_port, threshold=2.0)
    brain.start()
