import requests
import json
import datetime
import os

# Load config from root directory
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
try:
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
        LINE_CHANNEL_ACCESS_TOKEN = config["notifications"]["line_channel_access_token"]
        LINE_USER_ID = config["notifications"]["line_user_id"]
except Exception as e:
    print(f"Failed to load config.json: {e}")
    LINE_CHANNEL_ACCESS_TOKEN = "YOUR_CHANNEL_ACCESS_TOKEN"
    LINE_USER_ID = "YOUR_USER_ID"

def send_fall_alert(location_name="Unknown Location"):
    if LINE_CHANNEL_ACCESS_TOKEN == "YOUR_CHANNEL_ACCESS_TOKEN":
        print("LINE Alert Disabled: Please configure your tokens in line_notifier.py")
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
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        if response.status_code == 200:
            print("Successfully sent LINE Flex Message!")
            return True
        else:
            print(f"Failed to send LINE message: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Error connecting to LINE API: {e}")
        return False

# For manual testing
if __name__ == "__main__":
    send_fall_alert("Living Room")
