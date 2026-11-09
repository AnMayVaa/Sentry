import requests
import json
import datetime
from urllib.parse import quote

from config_loader import CONFIG, is_configured

LINE_CHANNEL_ACCESS_TOKEN = CONFIG["notifications"].get("line_channel_access_token", "")
LINE_USER_ID = CONFIG["notifications"].get("line_user_id", "")
PUBLIC_URL = CONFIG["notifications"].get("public_url", "").rstrip("/")
CONTROL_TOKEN = CONFIG["security"].get("control_token", "")
LINE_TIMEOUT_S = 10


def silence_url():
    url = f"{PUBLIC_URL}/silence"
    if CONTROL_TOKEN:
        url += f"?token={quote(CONTROL_TOKEN)}"
    return url


# Text for each alert kind. "fall" comes from the CSI model, "sos" from someone
# holding the SOS button on a node (Phase 8).
ALERT_TEXT = {
    "fall": {
        "alt": "🚨 EMERGENCY: Fall Detected in {loc}!",
        "header": "🚨 EMERGENCY ALERT",
        "title": "FALL DETECTED IN: {loc}",
        "body": "The invisible Wi-Fi CSI system has detected a potential fall.",
        "color": "#ff0000",
    },
    "sos": {
        "alt": "🆘 SOS: Help requested in {loc}!",
        "header": "🆘 SOS BUTTON PRESSED",
        "title": "HELP REQUESTED IN: {loc}",
        "body": "Someone held the SOS button on the Sentry node. Please check on them now.",
        "color": "#e11d48",
    },
}


def build_alert_message(location_name, kind="fall", now=None):
    """Return the LINE Flex message dict for a fall or SOS alert."""
    text = ALERT_TEXT[kind]
    current_time = (now or datetime.datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    loc_upper = location_name.upper()
    return _flex(text, location_name, loc_upper, current_time)


def send_sos_alert(location_name="Unknown Location"):
    return send_fall_alert(location_name, kind="sos")


def send_fall_alert(location_name="Unknown Location", kind="fall"):
    print(f"[LINE_NOTIFIER] Attempting to send {kind} alert for {location_name}...", flush=True)
    if not (is_configured(LINE_CHANNEL_ACCESS_TOKEN) and is_configured(LINE_USER_ID)):
        print("[LINE_NOTIFIER] LINE Alert Disabled: set line_channel_access_token and line_user_id "
              "in config.local.json (or SENTRY_LINE_TOKEN / SENTRY_LINE_USER_ID)", flush=True)
        return False
        
    url = "https://api.line.me/v2/bot/message/push"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    
    flex_message = build_alert_message(location_name, kind)

    payload = {
        "to": LINE_USER_ID,
        "messages": [flex_message]
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=LINE_TIMEOUT_S)
        if response.status_code == 200:
            print("[LINE_NOTIFIER] Successfully sent LINE Flex Message!", flush=True)
            return True
        else:
            print(f"[LINE_NOTIFIER] Failed to send LINE message: {response.status_code} - {response.text}", flush=True)
            return False
    except Exception as e:
        print(f"[LINE_NOTIFIER] Error connecting to LINE API: {e}", flush=True)
        return False

def _flex(text, location_name, loc_upper, current_time):
    # Beautiful Flex Message Card for NSC Judges
    return {
        "type": "flex",
        "altText": text["alt"].format(loc=location_name),
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": text["header"],
                        "weight": "bold",
                        "color": "#ffffff",
                        "size": "xl"
                    }
                ],
                "backgroundColor": text["color"]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": text["title"].format(loc=loc_upper),
                        "weight": "bold",
                        "size": "xl",
                        "wrap": True,
                        "color": text["color"]
                    },
                    {
                        "type": "text",
                        "text": text["body"],
                        "wrap": True,
                        "margin": "md"
                    },
                    {
                        "type": "separator",
                        "margin": "xxl"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "xxl",
                        "spacing": "sm",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "Time",
                                        "size": "sm",
                                        "color": "#aaaaaa",
                                        "flex": 1
                                    },
                                    {
                                        "type": "text",
                                        "text": current_time,
                                        "size": "sm",
                                        "color": "#000000",
                                        "weight": "bold",
                                        "flex": 3
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "action": {
                            "type": "uri",
                            "label": "Call Ambulance (1669)",
                            "uri": "tel:1669"
                        },
                        "style": "primary",
                        "color": "#ff0000"
                    },
                    {
                        "type": "button",
                        "action": {
                            "type": "uri",
                            "label": "🔕 ปิดเสียงไซเรน (Silence Alarm)",
                            "uri": silence_url()
                        },
                        "style": "secondary"
                    }
                ]
            }
        }
    }
    

# For manual testing
if __name__ == "__main__":
    send_fall_alert("Living Room")
