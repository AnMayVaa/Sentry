import requests
import json
import datetime

# --- CONFIGURATION ---
# Replace these with your actual tokens later!
LINE_CHANNEL_ACCESS_TOKEN = "pBZ5zrGCs9DJm8/9L1jtJfP9/JfGtxNVC8GsTHA34Z3kB1AuQMAW5IcTXgSlSR310hrMsZTK7u9xxGYS5mZB9OFbxg5fEkX3KnGg+RN/kkQzLEN0Gi8QH1ItYz3FCDqzeVRHEKptG6bR6wJ9v5a4CAdB04t89/1O/w1cDnyilFU="
LINE_USER_ID = "Uc6dede4107b73b7f50a1f60d10d39f96"

def send_fall_alert():
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
        "altText": "🚨 EMERGENCY: Fall Detected!",
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
                        "text": "FALL DETECTED!",
                        "weight": "bold",
                        "size": "xxl",
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
    send_fall_alert()
