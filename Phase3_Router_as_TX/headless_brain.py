import sys
import os
import time
import json
import numpy as np
from collections import deque

import joblib
from collections import Counter
import threading
import asyncio
import websockets
import http.server
import socketserver

import serial.tools.list_ports
from serial_reader import SerialReader
from udp_reader import UDPReader
from ml_engine import extract_features, extract_features_np
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
        self.udp_port = 5000
        self.mode = "USB"  # 'USB' or 'UDP'
        self.tx_mode = "TX_DEDICATED" # 'TX_DEDICATED' or 'TX_ROUTER'
        self.threshold = threshold
        
        self.history = deque(maxlen=45)
        self.prediction_history = deque(maxlen=15)
        self.last_broadcast_time = 0
        self.frame_count = 0
        self._processing = False
        
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
        self.last_variance = 0.0
        
        self.reader = None
        
        # IoT Server Variables
        self.connected_clients = set()
        self.loop = None
        self._latest_payload = None  # Shared between reader thread and async loop
        
        # Ping loop for TX_ROUTER mode — always uses Wi-Fi UDP, never serial!
        self.esp32_ip = None
        self.ping_thread = threading.Thread(target=self._router_ping_loop, daemon=True)
        self.ping_thread.start()
        
        # Background thread to discover ESP32's IP via mDNS
        self._discover_esp32_ip()

    def _discover_esp32_ip(self):
        """Try to resolve esp32-csi.local via mDNS so we can UDP-ping it."""
        import socket
        def _resolve():
            while not self.esp32_ip:
                try:
                    ip = socket.gethostbyname("esp32-csi.local")
                    self.esp32_ip = ip
                    print(f"[INFO] Discovered ESP32 IP via mDNS: {ip}")
                except Exception:
                    pass
                time.sleep(2)
        threading.Thread(target=_resolve, daemon=True).start()

    def _router_ping_loop(self):
        import socket
        ping_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while True:
            if self.tx_mode == "TX_ROUTER":
                # Always send UDP over Wi-Fi to stimulate the router
                if self.esp32_ip:
                    try:
                        ping_sock.sendto(b"PING", (self.esp32_ip, 5000))
                    except Exception:
                        pass
                # Also use the reader's send_command if it's UDP-based
                elif self.reader and hasattr(self.reader, 'last_client_addr') and self.reader.last_client_addr:
                    try:
                        self.reader.send_command("PING")
                    except Exception:
                        pass
            time.sleep(0.033)

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
                        await self.broadcast_config()
                        
                    elif data.get("command") == "set_mode":
                        self.mode = data.get("mode", "USB")
                        print(f"[IOT] Switching mode to {self.mode}...")
                        if self.reader:
                            self.reader.disconnect()
                        if self.mode == "USB":
                            self.reader = SerialReader(self.port, 460800, self.data_received)
                            self.reader.connect()
                        else:
                            self.reader = UDPReader(self.udp_port, self.data_received)
                            self.reader.connect()
                        await self.broadcast_config()
                        
                    elif data.get("command") == "set_port":
                        new_port = data.get("port")
                        print(f"[IOT] Switching COM port to {new_port}...")
                        self.port = new_port
                        if self.reader:
                            self.reader.disconnect()
                        if self.mode == "USB":
                            self.reader = SerialReader(self.port, 460800, self.data_received)
                            if self.reader.connect():
                                print(f"[IOT] Successfully reconnected to {self.port}")
                            else:
                                print(f"[IOT] Failed to connect to {self.port}")
                                self.port = ""
                        await self.broadcast_config()
                        
                    elif data.get("command") == "set_udp_port":
                        new_port = int(data.get("port", 5000))
                        print(f"[IOT] Switching UDP port to {new_port}...")
                        self.udp_port = new_port
                        if self.reader:
                            self.reader.disconnect()
                        if self.mode == "UDP":
                            self.reader = UDPReader(self.udp_port, self.data_received)
                            if self.reader.connect():
                                print(f"[IOT] Successfully bound to UDP {self.udp_port}")
                            else:
                                print(f"[IOT] Failed to bind to UDP {self.udp_port}")
                        await self.broadcast_config()
                        
                    elif data.get("command") == "disconnect":
                        print("[IOT] Stopping CSI stream (Disconnecting)...")
                        if self.reader:
                            self.reader.disconnect()
                        if self.mode == "USB":
                            self.port = ""
                        # For UDP, we don't clear the port, just stop listening.
                        # But wait, if we stop the reader, the next connect will use it.
                        await self.broadcast_config()
                        
                    elif data.get("command") == "get_config":
                        await self.broadcast_config()
                        
                    elif data.get("command") == "set_tx_mode":
                        new_tx_mode = data.get("tx_mode", "TX_DEDICATED")
                        self.tx_mode = new_tx_mode
                        print(f"[IOT] Switching TX Mode to {self.tx_mode}...")
                        if self.reader and hasattr(self.reader, 'send_command'):
                            cmd_str = "MODE_ROUTER" if self.tx_mode == "TX_ROUTER" else "MODE_TX_NODE"
                            self.reader.send_command(cmd_str)
                            print(f"[IOT] Transmitted {cmd_str} to ESP32 Receiver.")
                        await self.broadcast_config()
                except Exception as e:
                    print(f"[IOT] Error parsing command: {e}")
        finally:
            self.connected_clients.remove(websocket)
            print(f"[IOT] Web Dashboard Disconnected. ({len(self.connected_clients)} remaining)")

    async def broadcast_ws(self, payload):
        if self.connected_clients:
            message = json.dumps(payload)
            # Use try/except to handle any disconnected clients
            dead = set()
            for ws in self.connected_clients:
                try:
                    await ws.send(message)
                except Exception:
                    dead.add(ws)
            self.connected_clients -= dead
            
    async def broadcast_config(self):
        # A helper to check if reader is actually running
        is_running = self.reader is not None and getattr(self.reader, 'running', False)
        
        cfg_payload = {
            "type": "config",
            "mode": self.mode,
            "tx_mode": self.tx_mode,
            "threshold": self.threshold,
            "port": self.port if is_running and self.mode == "USB" else (self.port if self.mode == "USB" else ""),
            "udp_port": self.udp_port,
            "is_connected": is_running,
            "available_ports": [p.device for p in serial.tools.list_ports.comports()]
        }
        await self.broadcast_ws(cfg_payload)

    # --- UNIFIED HTTP & WEBSOCKET SERVER LOGIC ---
    async def process_request(self, path, request_headers):
        import http
        if path == "/" or path == "/index.html":
            dashboard_dir = os.path.join(os.path.dirname(__file__), 'dashboard')
            index_path = os.path.join(dashboard_dir, 'index.html')
            try:
                with open(index_path, "rb") as f:
                    content = f.read()
                return (http.HTTPStatus.OK, [("Content-Type", "text/html; charset=utf-8")], content)
            except Exception as e:
                return (http.HTTPStatus.INTERNAL_SERVER_ERROR, [], str(e).encode())
        elif path == "/ws":
            return None # Proceed to WebSocket upgrade
        else:
            return (http.HTTPStatus.NOT_FOUND, [], b"Not Found")

    async def _broadcast_loop(self):
        """Fixed-rate broadcast loop. Runs independently at 15Hz.
        Always sends only the LATEST state - never queues up."""
        while True:
            if self._latest_payload and self.connected_clients:
                payload = self._latest_payload
                self._latest_payload = None
                await self.broadcast_ws(payload)
            await asyncio.sleep(0.066)  # 15 FPS - perfect for web dashboard over Cloudflare

    async def _ws_main(self):
        import http
        async with websockets.serve(self.ws_handler, "0.0.0.0", 8000, process_request=self.process_request):
            # Run broadcast loop alongside the WebSocket server
            await self._broadcast_loop()

    def start_ws_server(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        print("[INFO] Unified Web & WebSocket Server running on port 8000")
        try:
            self.loop.run_until_complete(self._ws_main())
        except asyncio.CancelledError:
            pass

    # --- MAIN STARTUP ---
    def start(self):
        print(f"[INFO] Initializing in {self.mode} mode...")
        self.reader = SerialReader(self.port, 460800, self.data_received) if self.mode == "USB" else UDPReader(self.udp_port, self.data_received)
        if self.reader.connect():
            print(f"[SUCCESS] Reader Connected! Listening for CSI data...")
            
            # Start Unified Server in main thread (blocks forever)
            try:
                self.start_ws_server()
            except KeyboardInterrupt:
                print("\n[INFO] Shutting down...")
                self.reader.disconnect()
        else:
            print("[ERROR] Initial connection failed. Starting server anyway so UI can reconfigure...")
            try:
                self.start_ws_server()
            except KeyboardInterrupt:
                pass

    # --- CSI DATA PROCESSING ---
    def data_received(self, amplitudes, rssi):
        current_time = time.time()
        
        # --- PHASE 4: SOS BUTTON INTERRUPT ---
        if isinstance(amplitudes, str) and amplitudes == "SOS":
            print(f"[{time.strftime('%H:%M:%S')}] \U0001f6a8 SOS BUTTON PRESSED! \U0001f6a8")
            if current_time - self.last_line_alert_time > 60.0:
                threading.Thread(target=send_fall_alert, daemon=True).start()
                self.last_line_alert_time = current_time
            return

        # Drop frame if previous one is still processing (prevents backlog)
        if self._processing:
            return
        self._processing = True
        
        try:
            self.history.append(amplitudes)
            self.frame_count += 1
            
            current_variance = self.last_variance
            
            if len(self.history) >= 45:
                # Run ML inference every 2nd frame (15Hz) — plenty for fall detection
                if self.frame_count % 2 == 0:
                    # Direct numpy — no pandas DataFrame overhead!
                    hist_arr = np.array(self.history)
                    features = extract_features_np(hist_arr)
                    
                    raw_pred = int(self.ml_model.predict([features])[0])
                    current_variance = float(features[0])
                    self.last_variance = current_variance
                    
                    # --- SENSITIVITY OVERRIDE (GATEKEEPER) ---
                    if current_variance < self.threshold:
                        raw_pred = 0
                    elif current_variance >= self.threshold and raw_pred == 0:
                        raw_pred = 1
                        
                    self.prediction_history.append(raw_pred)
                    mode_pred = Counter(self.prediction_history).most_common(1)[0][0]
                    
                    # Sequence State Machine
                    if mode_pred == 2:
                        self.potential_fall_time = current_time
                        
                    if (current_time - self.potential_fall_time < 3.0) and mode_pred == 0:
                        if current_time - self.last_line_alert_time > 60.0:
                            print(f"\n[{time.strftime('%H:%M:%S')}] \U0001f6a8 FALL DETECTED! \U0001f6a8")
                            threading.Thread(target=send_fall_alert, daemon=True).start()
                            self.last_line_alert_time = current_time
                    
                    new_state = 1 if mode_pred == 2 else mode_pred 
                    if current_time - self.last_line_alert_time < 3.0:
                        new_state = 2 
                        
                    if new_state != self.current_state:
                        state_names = {0: "STATIC", 1: "MOVEMENT", 2: "FALL DETECTED"}
                        print(f"[{time.strftime('%H:%M:%S')}] STATE: {state_names[new_state]} (Var: {current_variance:.2f})")
                        self.current_state = new_state

            # --- Store latest payload for the broadcast loop ---
            self._latest_payload = {
                "state": int(self.current_state),
                "variance": round(float(current_variance), 2),
                "threshold": float(self.threshold),
                "amplitudes": [round(float(a), 1) for a in amplitudes]
            }
        finally:
            self._processing = False

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
