import os
import requests
from aoiwaifu import TOKEN, OWNER_ID, OWNER_USERNAME, WAIFU_START_IMAGE

CHAT_ID = OWNER_ID
BOT_NAME = "Fiona"
IMAGE_URL = WAIFU_START_IMAGE

def send_start_message():
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    caption = (
        f"🌸 *Fiona is now online and operational\\!*\n\n"
        f"👑 *Owner ID:* `{OWNER_ID}`\n"
        f"🚀 *Status:* All modules loaded successfully\\!"
    )
    payload = {
        "chat_id": CHAT_ID,
        "caption": caption,
        "parse_mode": "MarkdownV2"  # Use MarkdownV2 for proper escaping
    }

    response = None
    try:
        if os.path.isfile(IMAGE_URL):
            with open(IMAGE_URL, "rb") as image_file:
                response = requests.post(
                    url,
                    data=payload,
                    files={"photo": image_file},
                    timeout=20,
                )
        else:
            response = requests.post(
                url,
                json={**payload, "photo": IMAGE_URL},
                timeout=20,
            )
        response.raise_for_status()  # Raise exception for HTTP errors
        print("Start message sent successfully.")
    except requests.exceptions.RequestException as e:
        if response is not None:
            print(f"Error response: {response.text}")
        print(f"Failed to send start message: {e}")
