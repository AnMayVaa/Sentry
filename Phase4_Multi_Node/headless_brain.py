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
import hmac
import math
from urllib.parse import urlsplit, parse_qs

import serial.tools.list_ports
from serial_reader import SerialReader
from udp_reader import UDPReader
from ml_engine import extract_features, extract_features_np
from line_notifier import send_fall_alert, send_sos_alert
from alarm_broadcaster import send_alarm_broadcast, send_silence_broadcast, send_sos_broadcast

from config_loader import CONFIG as global_config

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "fall_detection_model.pkl")
THRESHOLD = float(global_config["ai_settings"]["variance_threshold"])
HTTP_PORT = int(global_config["networking"]["http_port"])  # Unified HTTP + WebSocket port
UDP_PORT = int(global_config["networking"]["udp_receiver_port"])
CONTROL_TOKEN = global_config["security"].get("control_token", "") or ""

# Dashboard commands that only read state. Everything else changes the system
# (thresholds, readers, simulation, test alerts) and needs the control token
# when one is configured.
READ_ONLY_COMMANDS = {"get_config", "get_nodes"}

MAX_THRESHOLD = 1000.0

# A node sends each SOS a few times (UDP can drop packets). Copies that arrive
# within this window count as the same SOS. A new hold after it is a new SOS.
SOS_DEDUPE_S = 15.0
# How long the dashboard shows "SOS PRESSED" on that node's card.
SOS_SHOW_S = 30.0


def parse_threshold(value):
    """Return a finite, positive threshold or raise ValueError."""
    t = float(value)
    if not math.isfinite(t) or t <= 0 or t > MAX_THRESHOLD:
        raise ValueError(f"threshold out of range: {value!r}")
    return t


def token_matches(supplied):
    """True when no control token is configured, or the supplied one matches."""
    if not CONTROL_TOKEN:
        return True
    if not supplied:
        return False
    return hmac.compare_digest(str(supplied).encode(), CONTROL_TOKEN.encode())


_UNSAFE_NAME_CHARS = set('<>"\'`\\&')


def sanitize_location(name, max_len=48):
    """Node names come from the network and end up inside dashboard HTML and
    onclick handlers, so drop quotes/markup/control characters. A name like
    "Ohm's Room" would otherwise break the dashboard's threshold slider."""
    cleaned = "".join(c for c in str(name) if c.isprintable() and c not in _UNSAFE_NAME_CHARS)
    cleaned = cleaned.strip()[:max_len]
    return cleaned or "Unknown"


def split_path(path):
    """Split '/ws?token=x' into ('/ws', {'token': 'x'})."""
    parts = urlsplit(path)
    query = {k: v[0] for k, v in parse_qs(parts.query).items() if v}
    return parts.path or "/", query

class NodeState:
    def __init__(self):
        self.history = deque(maxlen=45)
        self.raw_buffer = deque(maxlen=3) # Median filter buffer
        self.prediction_history = deque(maxlen=15)
        self.frame_count = 0
        self._processing = False
        self.potential_fall_time = 0
        self.last_line_alert_time = 0
        self.last_sos_time = 0.0
        self.current_state = 0
        self.sim_target_state = 0
        self.last_variance = 0.0
        self.last_seen = time.time()
        self.threshold = THRESHOLD
        self.sim_locked = False
        self.sim_start_time = 0.0
        self.sim_noise = 0.0
        self.sim_base = 0.0  # Smoothly lerped amplitude level
        self.sim_fall_alert_pending = False

class HeadlessBrain:
    def __init__(self, port=None, threshold=THRESHOLD):
        self.readers = {} # port_name -> Reader instance
        self.udp_port = UDP_PORT
        self.tx_mode = "TX_DEDICATED" # 'TX_DEDICATED' or 'TX_ROUTER'
        self.threshold = threshold
        
        self.nodes = {} # Dictionary mapping location_name -> NodeState
        # Reader threads add nodes while the asyncio loop iterates/deletes them.
        self.nodes_lock = threading.Lock()
        self.alarm_receivers = {}  # ip -> {"ip", "last_seen"}

        # Start heartbeat listener for alarm receivers (UDP port 5002)
        threading.Thread(target=self._alarm_heartbeat_listener, daemon=True).start()
        
        self.ml_model = None
        try:
            self.ml_model = joblib.load(MODEL_PATH)
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

    def _alarm_heartbeat_listener(self):
        """Listens for UDP heartbeats from Phase 5 Alarm Receivers on port 5002."""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", 5002))
            sock.settimeout(2.0)
            print("[ALARM] Listening for alarm receiver heartbeats on UDP 5002")
            while True:
                try:
                    data, addr = sock.recvfrom(128)
                    msg = data.decode("utf-8").strip()
                    if msg.startswith("ALARM_READY"):
                        ip = addr[0]
                        self.alarm_receivers[ip] = {"ip": ip, "last_seen": time.time()}
                except socket.timeout:
                    pass
                except Exception:
                    pass
        except Exception as e:
            print(f"[ALARM] Heartbeat listener failed: {e}")

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
        _, query = split_path(getattr(websocket, "path", "") or "")
        authorized = token_matches(query.get("token"))
        self.connected_clients.add(websocket)
        print(f"[IOT] New Web Dashboard Connected! ({len(self.connected_clients)} total)")
        
        # Send initial configuration to all clients (including this new one)
        await self.broadcast_config()

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if not isinstance(data, dict):
                        continue
                    command = data.get("command")
                    if command not in READ_ONLY_COMMANDS and not (authorized or token_matches(data.get("token"))):
                        print(f"[IOT] Rejected unauthorized command: {command}")
                        await websocket.send(json.dumps({"type": "error", "error": "unauthorized", "command": command}))
                        continue
                    if data.get("command") == "simulate_state":
                        node_id = data.get("node_id")
                        state   = int(data.get("state", 0))
                        if state not in (0, 1, 2):
                            raise ValueError(f"invalid state {state}")
                        if node_id and node_id in self.nodes:
                            node = self.nodes[node_id]
                            # Always lock — STATIC/MOVEMENT/FALL all hold until release_sim
                            node.sim_locked = True
                            node.sim_target_state = state
                            node.sim_start_time = time.time()
                            node.sim_noise = 0.0
                            # sim_base starts from current value so amplitude ramps smoothly
                            node.sim_base = node.last_variance
                            if state == 2:
                                node.sim_fall_alert_pending = True
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
                        threading.Thread(target=send_alarm_broadcast, args=(node_id,), daemon=True).start()

                    elif data.get("command") == "get_nodes":
                        with self.nodes_lock:
                            nodes_list = list(self.nodes.keys())
                        await websocket.send(json.dumps({"type": "nodes_list", "nodes": nodes_list}))

                    elif data.get("command") == "set_threshold":
                        new_thresh = parse_threshold(data.get("value", THRESHOLD))
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
                        port = int(data.get("port", UDP_PORT))
                        if not 1 <= port <= 65535:
                            raise ValueError(f"invalid UDP port {port}")
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
                        port = int(data.get("port", UDP_PORT))
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
                        if new_tx_mode not in ("TX_DEDICATED", "TX_ROUTER"):
                            raise ValueError(f"invalid tx_mode {new_tx_mode!r}")
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
            # broadcast_ws() may already have dropped this socket as dead
            self.connected_clients.discard(websocket)
            print(f"[IOT] Web Dashboard Disconnected. ({len(self.connected_clients)} remaining)")

    async def broadcast_ws(self, payload):
        if self.connected_clients:
            message = json.dumps(payload)
            # Use try/except to handle any disconnected clients
            dead = set()
            for ws in list(self.connected_clients):
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
        dashboard_dir = os.path.join(BASE_DIR, 'dashboard')
        path, query = split_path(path)
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
        elif path == "/silence":
            if not token_matches(query.get("token")):
                return (http.HTTPStatus.FORBIDDEN, [("Content-Type", "text/plain; charset=utf-8")], b"Forbidden: missing or wrong token")
            # Trigger UDP silence broadcast to stop ESP32 alarm sirens
            threading.Thread(target=send_silence_broadcast, daemon=True).start()
            html_content = """<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sentry IoT - ปิดเสียงไซเรน</title>
    <style>
        * { box-sizing: border-box; }
        body {
            background: #0f172a;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }
        .card {
            background: rgba(30, 41, 59, 0.9);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 24px;
            padding: 40px 24px;
            text-align: center;
            max-width: 380px;
            width: 100%;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            backdrop-filter: blur(12px);
        }
        .icon {
            font-size: 64px;
            margin-bottom: 16px;
            display: inline-block;
            animation: bounce 1s ease;
        }
        @keyframes bounce {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.15); }
        }
        h1 {
            font-size: 22px;
            margin: 0 0 12px;
            color: #38bdf8;
        }
        p {
            font-size: 15px;
            color: #94a3b8;
            line-height: 1.6;
            margin: 0 0 28px;
        }
        .btn {
            display: block;
            background: linear-gradient(135deg, #0ea5e9, #0284c7);
            color: white;
            text-decoration: none;
            padding: 14px 20px;
            border-radius: 14px;
            font-weight: bold;
            font-size: 15px;
            box-shadow: 0 10px 20px -5px rgba(14, 165, 233, 0.4);
            transition: transform 0.15s ease;
        }
        .btn:active { transform: scale(0.97); }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">🔕</div>
        <h1>ปิดเสียงไซเรนแล้ว</h1>
        <p>ระบบ Sentry ได้ส่งสัญญาณปิดเสียงแจ้งเตือนและไฟกระพริบ (Buzzer & LED) ไปยังอุปกรณ์ในพื้นที่เรียบร้อยแล้วครับ</p>
        <a href="/" class="btn">เปิดหน้า Dashboard</a>
    </div>
</body>
</html>"""
            return (http.HTTPStatus.OK, [("Content-Type", "text/html; charset=utf-8"), ("Cache-Control", "no-cache")], html_content.encode("utf-8"))
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
            with self.nodes_lock:
                stale_nodes = [loc for loc, node in self.nodes.items() if current_time - node.last_seen > 5.0 and not node.sim_locked]
                for loc in stale_nodes:
                    print(f"[IOT] Node disconnected/timed out: {loc}")
                    del self.nodes[loc]
                nodes_snapshot = list(self.nodes.items())
                
            # 2. Build payload of ALL active nodes
            if self.connected_clients:
                import random
                import math
                payload = {"type": "data", "nodes": {}}
                for loc, node in nodes_snapshot:
                    if node.sim_locked:
                        node.last_seen = current_time # Keep alive
                        T = node.threshold
                        elapsed = current_time - node.sim_start_time
                        t = current_time

                        # sim_noise drifts very slowly — only used for subtle offset
                        node.sim_noise += (random.gauss(0, 1) - node.sim_noise) * 0.015

                        # Natural irregular texture: sum of harmonics (no gauss each frame = no teeth)
                        texture = (math.sin(t * 1.1)  * 0.40 +
                                   math.sin(t * 2.7)  * 0.25 +
                                   math.sin(t * 5.3)  * 0.12 +
                                   node.sim_noise     * 0.15)
                        # texture is ~-0.8 to +0.8, gives organic bumps

                        if node.sim_target_state == 0:
                            # STATIC: ramp sim_base down toward 40% of threshold
                            node.current_state = 0
                            node.sim_base += (T * 0.40 - node.sim_base) * 0.04
                            raw = node.sim_base * (1 + texture * 0.10)
                            node.last_variance = min(max(raw, 0.0), T * 0.85)

                        elif node.sim_target_state == 1:
                            # MOVEMENT: ramp sim_base up toward 170% of threshold
                            node.current_state = 1
                            node.sim_base += (T * 1.70 - node.sim_base) * 0.04
                            raw = node.sim_base * (1 + texture * 0.12)
                            node.last_variance = max(raw, T * 1.05)  # hard floor

                        elif node.sim_target_state == 2:
                            # FALL: drive sim_base through a bell curve then settle
                            if elapsed < 1.5:
                                node.current_state = 1
                                progress = elapsed / 1.5
                                target = T * 1.7 * math.sin(progress * math.pi / 2)
                                node.sim_base += (target - node.sim_base) * 0.06
                                raw = node.sim_base + texture * T * 0.025
                                node.last_variance = max(0.0, raw)
                            elif elapsed < 3.0:
                                node.current_state = 1
                                progress = (elapsed - 1.5) / 1.5
                                target = T * 1.7 * math.cos(progress * math.pi / 2)
                                node.sim_base += (target - node.sim_base) * 0.06
                                raw = node.sim_base + texture * T * 0.02
                                node.last_variance = max(0.0, raw)
                            else:
                                # FALL DETECTED — settle quietly below threshold
                                node.current_state = 2
                                node.sim_base += (T * 0.30 - node.sim_base) * 0.04
                                raw = node.sim_base * (1 + texture * 0.10)
                                node.last_variance = min(max(raw, 0.0), T * 0.85)
                                
                                if node.sim_fall_alert_pending:
                                    node.sim_fall_alert_pending = False
                                    if current_time - node.last_line_alert_time > 5.0:
                                        node.last_line_alert_time = current_time
                                        print(f"[{time.strftime('%H:%M:%S')}] DEBUG FALL TRIGGERED IN {loc}!")
                                        threading.Thread(target=send_fall_alert, args=(loc,), daemon=True).start()
                                        threading.Thread(target=send_alarm_broadcast, args=(loc,), daemon=True).start()

                    amps = node.history[-1] if len(node.history) > 0 else [0]*52
                    # Handle the case where SOS string might be in history (it shouldn't be, but just in case)
                    if isinstance(amps, str):
                        amps = [0]*52
                        
                    payload["nodes"][loc] = {
                        "state": int(node.current_state),
                        "variance": round(float(node.last_variance), 2),
                        "threshold": float(node.threshold),
                        "sos": bool(node.last_sos_time and current_time - node.last_sos_time < SOS_SHOW_S),
                        "amplitudes": [round(float(a), 1) for a in amps]
                    }
                # broadcast once per frame, outside the node loop
                await self.broadcast_ws(payload)
                
            await asyncio.sleep(0.066)  # 15 FPS

    async def _ws_main(self):
        import http
        async with websockets.serve(self.ws_handler, "0.0.0.0", HTTP_PORT, process_request=self.process_request):
            # Run broadcast loop alongside the WebSocket server
            await self._broadcast_loop()

    def start_ws_server(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        print(f"[INFO] Unified Web & WebSocket Server running on port {HTTP_PORT}")
        if CONTROL_TOKEN:
            print("[INFO] Control token is set: dashboard controls and /silence need ?token=...")
        else:
            print("[WARNING] No security.control_token set: anyone who can reach the dashboard can change settings")
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
        location_name = sanitize_location(location_name)
        if reader_id:
            # Prefix location_name with port/reader ID if not already there, 
            # so multiple ESP32s with the exact same Arduino string don't merge/sum their data blocks!
            if not location_name.startswith(f"[{reader_id}]"):
                location_name = f"[{reader_id}] {location_name}"
                
        current_time = time.time()
        
        with self.nodes_lock:
            node = self.nodes.get(location_name)
            if node is None:
                node = NodeState()
                node.threshold = self.threshold
                self.nodes[location_name] = node
        node.last_seen = current_time
        
        # --- SOS BUTTON (Phase 8: hold 2 s on the node) ---
        # Uses its own timer so an SOS never blocks a later fall alert.
        if isinstance(amplitudes, str) and amplitudes == "SOS":
            if current_time - node.last_sos_time > SOS_DEDUPE_S:
                node.last_sos_time = current_time
                print(f"[{time.strftime('%H:%M:%S')}] SOS BUTTON PRESSED IN {location_name}!")
                threading.Thread(target=send_sos_alert, args=(location_name,), daemon=True).start()
                threading.Thread(target=send_sos_broadcast, args=(location_name,), daemon=True).start()
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
                                    threading.Thread(target=send_alarm_broadcast, args=(location_name,), daemon=True).start()
                            else:
                                # Keep graph updated in debug mode, just don't change state
                                pass
        finally:
            node._processing = False

if __name__ == "__main__":
    print("=======================================")
    print(" SENTRY: IoT Web Server Processor      ")
    print("=======================================")
    
    # Serial ports are optional: wireless nodes stream over UDP, and USB nodes
    # are connected from the dashboard. Do not exit when no USB device exists.
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("[INFO] No serial ports found. Running in Wi-Fi (UDP) mode only.")

    brain = HeadlessBrain(threshold=THRESHOLD)
    brain.start()
