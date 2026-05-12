import os
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


def send_message(text):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": text
    }

    requests.post(
        url,
        data=data
    )


def send_photo(photo_path, caption=""):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"

    with open(photo_path, "rb") as photo:

        files = {
            "document": photo
        }

        data = {
            "chat_id": CHAT_ID,
            "caption": caption
        }

        requests.post(
            url,
            data=data,
            files=files
        )
