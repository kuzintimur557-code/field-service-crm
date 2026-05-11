import requests
import os


BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


def send_message(text):

    if not BOT_TOKEN:
        return

    if not CHAT_ID:
        return

    url = (
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": CHAT_ID,
        "text": text
    }

    try:

        requests.post(
            url,
            data=data,
            timeout=10
        )

    except:
        pass
