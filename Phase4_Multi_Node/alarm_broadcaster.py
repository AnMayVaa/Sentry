"""
alarm_broadcaster.py
Sentry Phase 5 - Physical Alarm UDP Broadcaster

Sends a UDP broadcast packet to all Alarm Receiver nodes on the network
when a fall is detected. This is separate from LINE notifications.

Design principles:
- Non-blocking: always runs in a daemon thread
- Broadcast: sends to 255.255.255.255 so any receiver on LAN gets it
- Tiny packet: just "FALL_ALERT:<location>" - no bandwidth impact on CSI stream
- Graceful: all exceptions caught, never crashes headless_brain.py
"""

import socket
import json
import os

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
try:
    with open(CONFIG_PATH, "r") as f:
        _config = json.load(f)
    ALARM_UDP_PORT = _config.get("alarm", {}).get("udp_port", 5001)
    ALARM_ENABLED  = _config.get("alarm", {}).get("enabled", True)
except Exception:
    ALARM_UDP_PORT = 5001
    ALARM_ENABLED  = True


def send_alarm_broadcast(location_name: str = "Unknown") -> bool:
    """
    Broadcast a UDP fall alert to all alarm receivers on the local network.
    Safe to call from any thread. Never raises an exception.
    Returns True on success, False on failure.
    """
    if not ALARM_ENABLED:
        print("[ALARM] UDP alarm broadcast is disabled in config.json", flush=True)
        return False

    message = f"FALL_ALERT:{location_name}"
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1.0)
        sock.sendto(message.encode("utf-8"), ("255.255.255.255", ALARM_UDP_PORT))
        sock.close()
        print(f"[ALARM] Broadcast sent → UDP 255.255.255.255:{ALARM_UDP_PORT} | {message}", flush=True)
        return True
    except Exception as e:
        print(f"[ALARM] Failed to send UDP broadcast: {e}", flush=True)
        return False


# For manual testing
if __name__ == "__main__":
    print(f"[ALARM] Testing broadcast to port {ALARM_UDP_PORT}...")
    result = send_alarm_broadcast("Living Room")
    print(f"[ALARM] Result: {'OK' if result else 'FAILED'}")
