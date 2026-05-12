import os
import requests

BOT_TOKEN = os.getenv("8466880508:AAECt2BpqJB_KzWIJT1Tv27MaJNjGBjrUSc")
CHAT_ID = os.getenv("7739861626")


def send_message(text):

    url = f"https://api.telegram.org/bot{8466880508:AAECt2BpqJB_KzWIJT1Tv27MaJNjGBjrUSc}/sendMessage"

    data = {
        "chat_id": 7739861626,
        "text": text
    }

    requests.post(
        url,
        data=data
    )


def send_photo(photo_path, caption=""):

    url = f"https://api.telegram.org/bot{8466880508:AAECt2BpqJB_KzWIJT1Tv27MaJNjGBjrUSc}/sendDocument"

    with open(photo_path, "rb") as photo:

        files = {
            "document": photo
        }

        data = {
            "chat_id": 7739861626,
            "caption": caption
        }

        requests.post(
            url,
            data=data,
            files=files
        )
