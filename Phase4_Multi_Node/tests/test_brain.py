"""Tests for the Phase 4 headless brain. Run from the repo root:
    python -m pytest Phase4_Multi_Node/tests -q
"""
import asyncio
import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PHASE4 = os.path.dirname(HERE)
REPO = os.path.dirname(PHASE4)
sys.path.insert(0, PHASE4)

import config_loader  # noqa: E402
import headless_brain as hb  # noqa: E402


# ---------- config ----------

def test_local_config_and_env_override(tmp_path):
    base = tmp_path / "config.json"
    local = tmp_path / "config.local.json"
    base.write_text(json.dumps({"notifications": {"line_user_id": "", "line_channel_access_token": ""},
                                "ai_settings": {"variance_threshold": 3.0}}))
    local.write_text(json.dumps({"notifications": {"line_channel_access_token": "from-local"}}))
    cfg = config_loader.load_config(str(base), str(local), environ={"SENTRY_LINE_USER_ID": "U123"})
    assert cfg["notifications"]["line_channel_access_token"] == "from-local"
    assert cfg["notifications"]["line_user_id"] == "U123"
    assert cfg["ai_settings"]["variance_threshold"] == 3.0
    assert cfg["alarm"]["udp_port"] == 5005  # default kept


def test_tracked_config_has_no_secrets():
    with open(os.path.join(REPO, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    assert cfg["notifications"]["line_channel_access_token"] == ""
    assert cfg["notifications"]["line_user_id"] == ""
    assert cfg["security"]["control_token"] == ""


# ---------- helpers ----------

@pytest.mark.parametrize("value", ["nan", "inf", "-1", "0", "1e9", "abc"])
def test_parse_threshold_rejects_bad_values(value):
    with pytest.raises(ValueError):
        hb.parse_threshold(value)


def test_parse_threshold_accepts_normal():
    assert hb.parse_threshold("2.5") == 2.5


def test_sanitize_location():
    assert hb.sanitize_location("Ohm's Room") == "Ohms Room"
    assert hb.sanitize_location('<img src=x onerror="alert(1)">') == "img src=x onerror=alert(1)"
    assert hb.sanitize_location("ห้องนอน") == "ห้องนอน"  # Thai names survive
    assert hb.sanitize_location("") == "Unknown"
    assert len(hb.sanitize_location("x" * 500)) == 48


def test_split_path():
    assert hb.split_path("/ws?token=abc") == ("/ws", {"token": "abc"})
    assert hb.split_path("/") == ("/", {})


# ---------- brain without hardware ----------

class FakeModel:
    def __init__(self):
        self.next = 0

    def predict(self, X):
        return [self.next]


def make_brain():
    brain = object.__new__(hb.HeadlessBrain)
    brain.readers = {}
    brain.udp_port = hb.UDP_PORT
    brain.tx_mode = "TX_DEDICATED"
    brain.threshold = 2.0
    brain.nodes = {}
    brain.nodes_lock = threading.Lock()
    brain.alarm_receivers = {}
    brain.ml_model = FakeModel()
    brain.connected_clients = set()
    brain.loop = None
    return brain


@pytest.fixture
def alerts(monkeypatch):
    sent = []
    monkeypatch.setattr(hb, "send_fall_alert", lambda loc: sent.append(("line", loc)))
    monkeypatch.setattr(hb, "send_alarm_broadcast", lambda loc: sent.append(("alarm", loc)))
    monkeypatch.setattr(hb, "send_sos_alert", lambda loc: sent.append(("sos_line", loc)))
    monkeypatch.setattr(hb, "send_sos_broadcast", lambda loc: sent.append(("sos_alarm", loc)))
    return sent


def feed(brain, n, amp_fn):
    for i in range(n):
        brain.data_received(amp_fn(i), -50, "Room", reader_id="10.0.0.2")
    time.sleep(0.05)  # alert threads


def test_fall_sequence_triggers_one_alert(alerts):
    brain = make_brain()
    rng = np.random.default_rng(0)
    moving = lambda i: list(20 + rng.normal(0, 5, 53))
    still = lambda i: [20.0] * 53

    brain.ml_model.next = 2          # impact
    feed(brain, 80, moving)
    brain.ml_model.next = 0          # then still
    feed(brain, 80, still)
    node = brain.nodes["[10.0.0.2] Room"]
    assert node.current_state == 2
    assert [a for a in alerts if a[0] == "line"] == [("line", "[10.0.0.2] Room")]
    assert ("alarm", "[10.0.0.2] Room") in alerts


def test_walking_only_never_alerts(alerts):
    brain = make_brain()
    rng = np.random.default_rng(1)
    brain.ml_model.next = 1
    feed(brain, 200, lambda i: list(20 + rng.normal(0, 5, 53)))
    assert alerts == []


def test_sos_retries_count_as_one_alert(alerts):
    brain = make_brain()
    for _ in range(3):  # the node sends each SOS 3 times
        brain.data_received("SOS", 0, "Room", reader_id="10.0.0.2")
    time.sleep(0.05)
    assert sorted(alerts) == [("sos_alarm", "[10.0.0.2] Room"), ("sos_line", "[10.0.0.2] Room")]


def test_new_sos_after_dedupe_window_alerts_again(alerts):
    brain = make_brain()
    brain.data_received("SOS", 0, "Room", reader_id="10.0.0.2")
    brain.nodes["[10.0.0.2] Room"].last_sos_time -= hb.SOS_DEDUPE_S + 1
    brain.data_received("SOS", 0, "Room", reader_id="10.0.0.2")
    time.sleep(0.05)
    assert [a for a in alerts if a[0] == "sos_line"] == [("sos_line", "[10.0.0.2] Room")] * 2


def test_sos_does_not_block_a_following_fall_alert(alerts):
    brain = make_brain()
    brain.data_received("SOS", 0, "Room", reader_id="10.0.0.2")
    rng = np.random.default_rng(0)
    brain.ml_model.next = 2
    feed(brain, 80, lambda i: list(20 + rng.normal(0, 5, 53)))
    brain.ml_model.next = 0
    feed(brain, 80, lambda i: [20.0] * 53)
    assert ("line", "[10.0.0.2] Room") in alerts
    assert ("alarm", "[10.0.0.2] Room") in alerts


@pytest.mark.parametrize("line,expected", [
    ("SOS_ALERT,Bath Room", "Bath Room"),
    ("SOS_ALERT:Bath Room", "Bath Room"),
    ("SOS_ALERT", "Unknown"),
    ("SOS_ALERT,", "Unknown"),
    ("CSI_DATA,Room,1,2,3", None),
    ("HEARTBEAT", None),
])
def test_parse_sos_line(line, expected):
    from udp_reader import parse_sos_line
    assert parse_sos_line(line) == expected


def test_udp_reader_turns_sos_packet_into_callback():
    import socket
    from udp_reader import UDPReader
    got = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    reader = UDPReader(port, lambda *a, **k: got.append((a, k)))
    assert reader.connect()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
            tx.sendto(b"SOS_ALERT,Bath Room\n", ("127.0.0.1", port))
        for _ in range(50):
            if got:
                break
            time.sleep(0.05)
    finally:
        reader.disconnect()
    assert got == [(("SOS", 0, "Bath Room"), {"reader_id": "127.0.0.1"})]


def test_alarm_broadcast_messages(monkeypatch):
    import alarm_broadcaster as ab
    sent = []

    class FakeSock:
        def __init__(self, *a): pass
        def setsockopt(self, *a): pass
        def settimeout(self, *a): pass
        def sendto(self, data, addr): sent.append((data.decode(), addr))
        def close(self): pass

    monkeypatch.setattr(ab.socket, "socket", FakeSock)
    monkeypatch.setattr(ab, "ALARM_ENABLED", True)
    assert ab.send_alarm_broadcast("Bath Room")
    assert ab.send_sos_broadcast("Bath Room")
    assert ab.send_silence_broadcast()
    port = ab.ALARM_UDP_PORT
    assert sent == [("FALL_ALERT:Bath Room", ("255.255.255.255", port)),
                    ("SOS_ALERT:Bath Room", ("255.255.255.255", port)),
                    ("FALL_SILENCE", ("255.255.255.255", port))]


def test_line_sos_message_differs_from_fall():
    import line_notifier as ln
    fall = ln.build_alert_message("Bath Room", "fall")
    sos = ln.build_alert_message("Bath Room", "sos")
    assert "Fall" in fall["altText"] and "SOS" in sos["altText"]
    assert sos["contents"]["body"]["contents"][0]["text"] == "HELP REQUESTED IN: BATH ROOM"
    # both keep the call-ambulance and silence buttons
    assert [b["action"]["type"] for b in sos["contents"]["footer"]["contents"]] == ["uri", "uri"]


def test_new_node_inherits_current_global_threshold():
    brain = make_brain()
    brain.threshold = 7.5
    brain.data_received([1.0] * 53, -50, "Room")
    assert brain.nodes["Room"].threshold == 7.5


def test_model_loads_from_any_cwd(tmp_path, monkeypatch):
    import joblib
    monkeypatch.chdir(tmp_path)
    model = joblib.load(hb.MODEL_PATH)
    feats = hb.extract_features_np(np.full((45, 53), 20.0))
    assert int(model.predict([feats])[0]) in (0, 1, 2)


# ---------- HTTP / WebSocket server with a control token ----------

@pytest.fixture
def server(monkeypatch):
    import socket
    import websockets
    monkeypatch.setattr(hb, "CONTROL_TOKEN", "s3cret")
    silenced = []
    monkeypatch.setattr(hb, "send_silence_broadcast", lambda: silenced.append(1))
    brain = make_brain()
    brain.broadcast_config = lambda: asyncio.sleep(0)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    async def main():
        async with websockets.serve(brain.ws_handler, "127.0.0.1", port, process_request=brain.process_request):
            ready.set()
            await asyncio.Event().wait()

    t = threading.Thread(target=lambda: loop.run_until_complete(main()), daemon=True)
    t.start()
    assert ready.wait(5)
    yield brain, port, silenced


def http_status(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_http_routes(server):
    brain, port, silenced = server
    base = f"http://127.0.0.1:{port}"
    assert http_status(base + "/") == 200
    assert http_status(base + "/?token=s3cret") == 200
    assert http_status(base + "/silence") == 403
    assert http_status(base + "/silence?token=wrong") == 403
    assert http_status(base + "/silence?token=s3cret") == 200
    time.sleep(0.05)
    assert silenced == [1]


def ws_exchange(port, path, messages):
    import websockets

    async def go():
        async with websockets.connect(f"ws://127.0.0.1:{port}{path}") as ws:
            replies = []
            for m in messages:
                await ws.send(json.dumps(m))
                try:
                    replies.append(json.loads(await asyncio.wait_for(ws.recv(), 0.5)))
                except asyncio.TimeoutError:
                    replies.append(None)
            return replies
    return asyncio.run(go())


def test_ws_rejects_control_without_token(server):
    brain, port, _ = server
    brain.threshold = 2.0
    replies = ws_exchange(port, "/ws", [{"command": "set_threshold", "value": 99}])
    assert replies[0]["error"] == "unauthorized"
    assert brain.threshold == 2.0


def test_ws_accepts_control_with_token(server):
    brain, port, _ = server
    ws_exchange(port, "/ws?token=s3cret", [{"command": "set_threshold", "value": 4}])
    assert brain.threshold == 4.0


def test_ws_rejects_nan_threshold(server):
    brain, port, _ = server
    brain.threshold = 2.0
    ws_exchange(port, "/ws?token=s3cret", [{"command": "set_threshold", "value": "nan"}])
    assert brain.threshold == 2.0


# ---------- live input matches the training data ----------

def _csv_windows(name):
    path = os.path.join(REPO, "ML_Training_Tools", "livingroom_data", f"{name}.csv")
    with open(path) as f:
        rows = [line.strip().split(",") for line in f.readlines()[1:]]
    vals = np.array([[float(x) for x in r[2:]] for r in rows if len(r) == 55])  # 53 values per row
    # Rebuild the 64-amplitude vector the reader sees: values = amp[1:28] + amp[38:64]
    amps = np.zeros((len(vals), 64))
    amps[:, 1:28] = vals[:, :27]
    amps[:, 38:64] = vals[:, 27:]
    import ml_engine
    return np.array([ml_engine.select_subcarriers(a) for a in amps])


def test_select_subcarriers_matches_training_columns():
    import ml_engine
    amps = list(range(64))
    picked = ml_engine.select_subcarriers(amps)
    assert len(picked) == 52
    assert picked[0] == 2 and picked[25] == 27 and picked[26] == 38 and picked[-1] == 63


@pytest.mark.parametrize("name", ["static", "walking"])
def test_model_does_not_call_falls_on_non_fall_recordings(name):
    import joblib
    X = _csv_windows(name)
    model = joblib.load(hb.MODEL_PATH)
    preds = [int(model.predict([hb.extract_features_np(X[s:s + 45])])[0]) for s in range(0, len(X) - 45, 15)]
    assert preds.count(2) == 0


def test_udp_reader_parses_frame_end_to_end():
    import socket
    from udp_reader import UDPReader
    got = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    reader = UDPReader(port, lambda amps, rssi, loc, reader_id=None: got.append((amps, rssi, loc)))
    assert reader.connect()
    try:
        raw = ",".join(str(v) for v in ([3, 4] * 64))  # every subcarrier amplitude = 5
        frame = f"CSI_DATA,Bath Room,212,-53,128,{raw}\nHEARTBEAT\n"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(frame.encode(), ("127.0.0.1", port))
        for _ in range(50):
            if got:
                break
            time.sleep(0.02)
    finally:
        reader.disconnect()
    amps, rssi, loc = got[0]
    assert loc == "Bath Room" and rssi == -53
    assert len(amps) == 52 and all(abs(a - 5.0) < 1e-9 for a in amps)
