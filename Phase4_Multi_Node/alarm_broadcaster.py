"""
alarm_broadcaster.py
Sentry Phase 5/8 - Physical Alarm UDP Broadcaster

Sends a UDP broadcast packet to all Alarm Receiver / Alert Station nodes on
the network. This is separate from LINE notifications.

Messages (UDP port alarm.udp_port, default 5005):
    FALL_ALERT:<location>   fall detected by the CSI model -> fall siren
    SOS_ALERT:<location>    someone held the SOS button    -> SOS siren
    FALL_SILENCE            stop every siren (LINE button / dashboard)

Design principles:
- Non-blocking: always runs in a daemon thread
- Broadcast: sends to 255.255.255.255 so any receiver on LAN gets it
- Tiny packet - no bandwidth impact on CSI stream
- Graceful: all exceptions caught, never crashes headless_brain.py
"""

import socket

from config_loader import CONFIG

ALARM_UDP_PORT = int(CONFIG["alarm"].get("udp_port", 5005))
ALARM_ENABLED = bool(CONFIG["alarm"].get("enabled", True))


def _broadcast(message: str, label: str) -> bool:
    if not ALARM_ENABLED:
        print("[ALARM] UDP alarm broadcast is disabled in config.json", flush=True)
        return False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.0)
            sock.sendto(message.encode("utf-8"), ("255.255.255.255", ALARM_UDP_PORT))
        finally:
            sock.close()
        print(f"[ALARM] {label} broadcast sent → UDP 255.255.255.255:{ALARM_UDP_PORT} | {message}", flush=True)
        return True
    except Exception as e:
        print(f"[ALARM] Failed to send {label} broadcast: {e}", flush=True)
        return False


def send_alarm_broadcast(location_name: str = "Unknown") -> bool:
    """Broadcast a fall alert. Safe to call from any thread. Never raises."""
    return _broadcast(f"FALL_ALERT:{location_name}", "Fall")


def send_sos_broadcast(location_name: str = "Unknown") -> bool:
    """Broadcast an SOS-button alert. Safe to call from any thread. Never raises."""
    return _broadcast(f"SOS_ALERT:{location_name}", "SOS")


def send_silence_broadcast() -> bool:
    """Broadcast a silence command so every siren/LED stops. Never raises."""
    return _broadcast("FALL_SILENCE", "Silence")


# For manual testing
if __name__ == "__main__":
    print(f"[ALARM] Testing broadcast to port {ALARM_UDP_PORT}...")
    result = send_alarm_broadcast("Living Room")
    print(f"[ALARM] Result: {'OK' if result else 'FAILED'}")
