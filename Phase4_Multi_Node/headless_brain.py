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
import functools

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

class NodeState:
    def __init__(self):
        self.history = deque(maxlen=45)
        self.raw_buffer = deque(maxlen=3) # Median filter buffer
        self.prediction_history = deque(maxlen=15)
        self.frame_count = 0
        self._processing = False
        self.potential_fall_time = 0
        self.last_line_alert_time = 0
        self.current_state = 0
        self.sim_target_state = 0
        self.last_variance = 0.0
        self.last_seen = time.time()
        self.threshold = THRESHOLD
        self.sim_locked = False  # When True, CSI inference won't overwrite current_state
        self.sim_start_time = 0.0

class HeadlessBrain:
    def __init__(self, port, threshold=2.0):
        self.readers = {} # port_name -> Reader instance
        self.udp_port = 5000
        self.tx_mode = "TX_DEDICATED" # 'TX_DEDICATED' or 'TX_ROUTER'
        self.threshold = threshold
        
        self.nodes = {} # Dictionary mapping location_name -> NodeState
        
        self.ml_model = None
        try:
            self.ml_model = joblib.load("fall_detection_model.pkl")
            print("[INFO] Loaded Fall Detection ML model successfully!")
        except Exception as e:
            print(f"[WARNING] Could not load ML model: {e}")
            sys.exit(1)

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
        
        # Background thread to poll COM ports
        self._poll_com_ports()

    def _poll_com_ports(self):
        def _poll():
            last_ports = []
            while True:
                current_ports = [p.device for p in serial.tools.list_ports.comports()]
                if current_ports != last_ports:
                    last_ports = current_ports
                    if self.loop and self.loop.is_running():
                        asyncio.run_coroutine_threadsafe(self.broadcast_config(), self.loop)
                time.sleep(2)
        threading.Thread(target=_poll, daemon=True).start()

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
                # Always send UDP over Wi-Fi to stimulate the router.
                # We broadcast this to the subnet instead of hitting the ESP32 directly to avoid overwhelming its command buffer.
                try:
                    ping_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    ping_sock.sendto(b"ROUTER_STIMULUS", ('255.255.255.255', 5001))
                except Exception:
                    pass
            time.sleep(0.033)

    # --- WEBSOCKET SERVER LOGIC ---
    async def ws_handler(self, websocket):
        self.connected_clients.add(websocket)
        print(f"[IOT] New Web Dashboard Connected! ({len(self.connected_clients)} total)")
        
        # Send initial configuration to all clients (including this new one)
        await self.broadcast_config()

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get("command") == "simulate_state":
                        node_id = data.get("node_id")
                        state   = int(data.get("state", 0))
                        if node_id and node_id in self.nodes:
                            node = self.nodes[node_id]
                            # Always lock — STATIC/MOVEMENT/FALL all hold until release_sim
                            node.sim_locked = True
                            node.sim_target_state = state
                            node.sim_start_time = time.time()
                            if state == 2:
                                # Debug FALL: fire LINE with short 5s cooldown (for testing)
                                now = time.time()
                                if now - node.last_line_alert_time > 5.0:
                                    node.last_line_alert_time = now
                                    threading.Thread(target=send_fall_alert, args=(node_id,), daemon=True).start()
                            print(f"[DEBUG] Locked state={state} on {node_id}")

                    elif data.get("command") == "release_sim":
                        node_id = data.get("node_id")
                        if node_id and node_id in self.nodes:
                            self.nodes[node_id].sim_locked = False
                            self.nodes[node_id].current_state = 0
                            self.nodes[node_id].sim_target_state = 0
                            print(f"[DEBUG] Released sim lock on {node_id}")

                    elif data.get("command") == "test_line_alert":
                        node_id = data.get("node_id", "Debug")
                        print(f"[DEBUG] Triggering LINE alert for {node_id}")
                        threading.Thread(target=send_fall_alert, args=(node_id,), daemon=True).start()

                    elif data.get("command") == "get_nodes":
                        nodes_list = list(self.nodes.keys())
                        await websocket.send(json.dumps({"type": "nodes_list", "nodes": nodes_list}))

                    elif data.get("command") == "set_threshold":
                        new_thresh = float(data.get("value", 2.0))
                        node_id = data.get("node_id")
                        if node_id and node_id in self.nodes:
                            self.nodes[node_id].threshold = new_thresh
                            print(f"[IOT] Threshold for {node_id} updated to {new_thresh}")
                        else:
                            self.threshold = new_thresh
                            for node in self.nodes.values():
                                node.threshold = new_thresh
                            print(f"[IOT] Global threshold updated to {self.threshold}")
                        # No need to broadcast config, threshold is sent in data payload
                        
                    elif data.get("command") == "connect_serial":
                        port = data.get("port")
                        if port and port not in self.readers:
                            reader = SerialReader(port, 460800, functools.partial(self.data_received, reader_id=port))
                            if reader.connect():
                                self.readers[port] = reader
                                cmd_str = "MODE_ROUTER" if self.tx_mode == "TX_ROUTER" else "MODE_TX_NODE"
                                reader.send_command(cmd_str)
                                print(f"[IOT] Connected to {port}")
                            else:
                                print(f"[IOT] Failed to connect to {port}")
                        await self.broadcast_config()
                        
                    elif data.get("command") == "disconnect_serial":
                        port = data.get("port")
                        if port in self.readers:
                            self.readers[port].disconnect()
                            del self.readers[port]
                            print(f"[IOT] Disconnected from {port}")
                        await self.broadcast_config()
                        
                    elif data.get("command") == "connect_udp":
                        port = int(data.get("port", 5000))
                        key = f"UDP_{port}"
                        if key not in self.readers:
                            reader = UDPReader(port, self.data_received)
                            if reader.connect():
                                self.readers[key] = reader
                                cmd_str = "MODE_ROUTER" if self.tx_mode == "TX_ROUTER" else "MODE_TX_NODE"
                                reader.send_command(cmd_str)
                                print(f"[IOT] Listening on UDP {port}")
                            else:
                                print(f"[IOT] Failed to bind to UDP {port}")
                        await self.broadcast_config()
                        
                    elif data.get("command") == "disconnect_udp":
                        port = int(data.get("port", 5000))
                        key = f"UDP_{port}"
                        if key in self.readers:
                            self.readers[key].disconnect()
                            del self.readers[key]
                            print(f"[IOT] Stopped listening on UDP {port}")
                        await self.broadcast_config()
                        
                    elif data.get("command") == "get_config":
                        await self.broadcast_config()
                        
                    elif data.get("command") == "set_tx_mode":
                        new_tx_mode = data.get("tx_mode", "TX_DEDICATED")
                        self.tx_mode = new_tx_mode
                        print(f"[IOT] Switching TX Mode to {self.tx_mode}...")
                        for r in self.readers.values():
                            if hasattr(r, 'send_command'):
                                cmd_str = "MODE_ROUTER" if self.tx_mode == "TX_ROUTER" else "MODE_TX_NODE"
                                r.send_command(cmd_str)
                        print(f"[IOT] Transmitted TX mode command to all relevant receivers.")
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
        active_serial_ports = [k for k in self.readers.keys() if not k.startswith("UDP")]
        active_udp_ports = [int(k.split("_")[1]) for k in self.readers.keys() if k.startswith("UDP")]
        
        cfg_payload = {
            "type": "config",
            "tx_mode": self.tx_mode,
            "threshold": self.threshold,
            "active_serial_ports": active_serial_ports,
            "active_udp_ports": active_udp_ports,
            "available_ports": [p.device for p in serial.tools.list_ports.comports()]
        }
        await self.broadcast_ws(cfg_payload)

    # --- UNIFIED HTTP & WEBSOCKET SERVER LOGIC ---
    async def process_request(self, path, request_headers):
        import http
        dashboard_dir = os.path.join(os.path.dirname(__file__), 'dashboard')
        if path == "/" or path == "/index.html":
            index_path = os.path.join(dashboard_dir, 'index.html')
            try:
                with open(index_path, "rb") as f:
                    content = f.read()
                return (http.HTTPStatus.OK, [("Content-Type", "text/html; charset=utf-8"), ("Cache-Control", "no-cache")], content)
            except Exception as e:
                return (http.HTTPStatus.INTERNAL_SERVER_ERROR, [], str(e).encode())
        elif path == "/debug":
            debug_path = os.path.join(dashboard_dir, 'debug.html')
            try:
                with open(debug_path, "rb") as f:
                    content = f.read()
                return (http.HTTPStatus.OK, [("Content-Type", "text/html; charset=utf-8"), ("Cache-Control", "no-cache")], content)
            except Exception as e:
                return (http.HTTPStatus.INTERNAL_SERVER_ERROR, [], str(e).encode())
        elif path == "/ws":
            return None  # Proceed to WebSocket upgrade
        else:
            return (http.HTTPStatus.NOT_FOUND, [], b"Not Found")

    async def _broadcast_loop(self):
        """Fixed-rate broadcast loop. Runs independently at 15Hz.
        Always sends only the LATEST state - never queues up."""
        while True:
            current_time = time.time()
            
            # 1. Clean up stale nodes (no data for 5 seconds)
            stale_nodes = [loc for loc, node in self.nodes.items() if current_time - node.last_seen > 5.0 and not node.sim_locked]
            for loc in stale_nodes:
                print(f"[IOT] Node disconnected/timed out: {loc}")
                del self.nodes[loc]
                
            # 2. Build payload of ALL active nodes
            if self.connected_clients:
                import random
                import math
                payload = {"type": "data", "nodes": {}}
                for loc, node in self.nodes.items():
                    if node.sim_locked:
                        node.last_seen = current_time # Keep alive
                        elapsed = current_time - node.sim_start_time
                        
                        smooth_wave = math.sin(current_time * 4.0) * 0.15
                        slow_wave = math.sin(current_time * 1.5) * 0.8
                        
                        if node.sim_target_state == 0:
                            # Static: smooth small waves + micro jitter
                            node.current_state = 0
                            target = (node.threshold * 0.4) + smooth_wave + random.uniform(-0.1, 0.1)
                            node.last_variance += (max(0.0, target) - node.last_variance) * 0.15
                        elif node.sim_target_state == 1:
                            # Movement: smooth large waves + medium jitter
                            node.current_state = 1
                            target = (node.threshold * 1.5) + slow_wave + random.uniform(-0.4, 0.4)
                            node.last_variance += (max(node.threshold + 0.1, target) - node.last_variance) * 0.15
                        elif node.sim_target_state == 2:
                            # Fall: realistic peak and drop + high jitter on impact
                            if elapsed < 0.8:
                                node.current_state = 1 # MOVEMENT while peaking
                                progress = elapsed / 0.8
                                target = (node.threshold * 2.5) * math.sin(progress * (math.pi / 2)) + random.uniform(-0.4, 0.4)
                                node.last_variance = max(0.0, target)
                            elif elapsed < 1.5:
                                node.current_state = 1 # MOVEMENT while dropping
                                progress = (elapsed - 0.8) / 0.7
                                target = (node.threshold * 2.5) * math.cos(progress * (math.pi / 2)) + random.uniform(-0.2, 0.2)
                                node.last_variance = max(0.0, target)
                            else:
                                node.current_state = 2 # FALL DETECTED
                                target = (node.threshold * 0.2) + smooth_wave + random.uniform(-0.1, 0.1)
                                node.last_variance += (max(0.0, target) - node.last_variance) * 0.15
                                
                    amps = node.history[-1] if len(node.history) > 0 else [0]*52
                    # Handle the case where SOS string might be in history (it shouldn't be, but just in case)
                    if isinstance(amps, str):
                        amps = [0]*52
                        
                    payload["nodes"][loc] = {
                        "state": int(node.current_state),
                        "variance": round(float(node.last_variance), 2),
                        "threshold": float(node.threshold),
                        "amplitudes": [round(float(a), 1) for a in amps]
                    }
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
        print(f"[INFO] Initializing Sentry IoT server...")
        
        # Start UDP listener by default so headless Wi-Fi operation works automatically
        udp = UDPReader(self.udp_port, self.data_received)
        if udp.connect():
            self.readers[f"UDP_{self.udp_port}"] = udp
            print(f"[SUCCESS] Default UDP Reader Connected on port {self.udp_port}")
            
        try:
            self.start_ws_server()
        except KeyboardInterrupt:
            print("\n[INFO] Shutting down...")
            for r in self.readers.values():
                r.disconnect()

    # --- CSI DATA PROCESSING ---
    def data_received(self, amplitudes, rssi, location_name="Unknown", reader_id=None):
        if reader_id:
            # Prefix location_name with port/reader ID if not already there, 
            # so multiple ESP32s with the exact same Arduino string don't merge/sum their data blocks!
            if not location_name.startswith(f"[{reader_id}]"):
                location_name = f"[{reader_id}] {location_name}"
                
        current_time = time.time()
        
        if location_name not in self.nodes:
            self.nodes[location_name] = NodeState()
        node = self.nodes[location_name]
        node.last_seen = current_time
        
        # --- PHASE 4: SOS BUTTON INTERRUPT ---
        if isinstance(amplitudes, str) and amplitudes == "SOS":
            print(f"[{time.strftime('%H:%M:%S')}] SOS BUTTON PRESSED IN {location_name}!")
            if current_time - node.last_line_alert_time > 60.0:
                threading.Thread(target=send_fall_alert, args=(location_name,), daemon=True).start()
                node.last_line_alert_time = current_time
            return

        # Drop frame if previous one is still processing (prevents backlog)
        if node._processing:
            return
        node._processing = True
        
        try:
            # Temporal Median Filter (rejects 1-frame router glitches)
            node.raw_buffer.append(amplitudes)
            if len(node.raw_buffer) == 3:
                filtered_amplitudes = np.median(node.raw_buffer, axis=0).tolist()
            else:
                filtered_amplitudes = amplitudes
                
            node.history.append(filtered_amplitudes)
            node.frame_count += 1

            current_variance = node.last_variance
            
            if len(node.history) >= 45:
                if node.frame_count % 2 == 0:
                    hist_arr = np.array(node.history)
                    features = extract_features_np(hist_arr)
                    
                    if self.ml_model is not None:
                        raw_pred = int(self.ml_model.predict([features])[0])
                        current_variance = float(features[0])
                        node.last_variance = current_variance
                        
                        # SENSITIVITY GATEKEEPER
                        if current_variance < node.threshold:
                            raw_pred = 0
                        elif current_variance >= node.threshold and raw_pred == 0:
                            raw_pred = 1
                            
                        node.prediction_history.append(raw_pred)
                        mode_pred = Counter(node.prediction_history).most_common(1)[0][0]
                        
                        # Sequence State Machine
                        if mode_pred == 2:
                            node.potential_fall_time = current_time
                            
                        new_state = 1 if mode_pred == 2 else mode_pred
                        if (current_time - node.potential_fall_time < 3.0) and mode_pred == 0:
                            new_state = 2
                        if current_time - node.last_line_alert_time < 3.0:
                            new_state = 2

                        if new_state != node.current_state:
                            if not node.sim_locked:
                                state_names = {0: "STATIC", 1: "MOVEMENT", 2: "FALL DETECTED"}
                                print(f"[{time.strftime('%H:%M:%S')}] STATE [{location_name}]: {state_names[new_state]} (Var: {current_variance:.2f})")
                                node.current_state = new_state
                                # Fire LINE whenever state transitions to FALL
                                if new_state == 2 and current_time - node.last_line_alert_time > 60.0:
                                    node.last_line_alert_time = current_time
                                    print(f"[{time.strftime('%H:%M:%S')}] FALL DETECTED IN {location_name}!")
                                    threading.Thread(target=send_fall_alert, args=(location_name,), daemon=True).start()
                            else:
                                # Keep graph updated in debug mode, just don't change state
                                pass
        finally:
            node._processing = False

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
