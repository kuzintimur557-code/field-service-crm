import os
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


def send_message(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram disabled: BOT_TOKEN or CHAT_ID missing")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": text
    }

    response = requests.post(url, data=data, timeout=10)

    if not response.ok:
        print("Telegram send_message error:", response.status_code, response.text)
        return False

    return True


def send_photo(photo_path, caption=""):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram disabled: BOT_TOKEN or CHAT_ID missing")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"

    with open(photo_path, "rb") as photo:
        files = {
            "document": photo
        }

        data = {
            "chat_id": CHAT_ID,
            "caption": caption
        }

        response = requests.post(url, data=data, files=files, timeout=20)

    if not response.ok:
        print("Telegram send_photo error:", response.status_code, response.text)
        return False

    return True



def send_message_to_chat(chat_id, text):
    if not BOT_TOKEN or not chat_id:
        print("Telegram user notification disabled: BOT_TOKEN or chat_id missing")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": chat_id,
        "text": text
    }

    response = requests.post(url, data=data, timeout=10)

    if not response.ok:
        print("Telegram send_message_to_chat error:", response.status_code, response.text)
        return False

    return True
