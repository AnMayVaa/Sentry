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


def send_fall_alert(location_name="Unknown Location"):
    print(f"[LINE_NOTIFIER] Attempting to send alert for {location_name}...", flush=True)
    if not (is_configured(LINE_CHANNEL_ACCESS_TOKEN) and is_configured(LINE_USER_ID)):
        print("[LINE_NOTIFIER] LINE Alert Disabled: set line_channel_access_token and line_user_id "
              "in config.local.json (or SENTRY_LINE_TOKEN / SENTRY_LINE_USER_ID)", flush=True)
        return False
        
    url = "https://api.line.me/v2/bot/message/push"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Beautiful Flex Message Card for NSC Judges
    flex_message = {
        "type": "flex",
        "altText": f"🚨 EMERGENCY: Fall Detected in {location_name}!",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "🚨 EMERGENCY ALERT",
                        "weight": "bold",
                        "color": "#ffffff",
                        "size": "xl"
                    }
                ],
                "backgroundColor": "#ff0000"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"FALL DETECTED IN: {location_name.upper()}",
                        "weight": "bold",
                        "size": "xl",
                        "wrap": True,
                        "color": "#ff0000"
                    },
                    {
                        "type": "text",
                        "text": "The invisible Wi-Fi CSI system has detected a potential fall.",
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

# For manual testing
if __name__ == "__main__":
    send_fall_alert("Living Room")
