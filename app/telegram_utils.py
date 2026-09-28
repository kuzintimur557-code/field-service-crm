import os
import threading

import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


def _send_message_payload(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            data={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except requests.RequestException as e:
        print("Telegram sendMessage failed:", e)
        return False

    if not response.ok:
        print("Telegram sendMessage error:", response.status_code, response.text)
        return False

    return True


def _send_document_payload(chat_id, photo_path, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"

    try:
        with open(photo_path, "rb") as photo:
            response = requests.post(
                url,
                data={"chat_id": chat_id, "caption": caption},
                files={"document": photo},
                timeout=20,
            )
    except (OSError, requests.RequestException) as e:
        print("Telegram sendDocument failed:", e)
        return False

    if not response.ok:
        print("Telegram sendDocument error:", response.status_code, response.text)
        return False

    return True


def send_message(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram disabled: BOT_TOKEN or CHAT_ID missing")
        return False

    threading.Thread(
        target=_send_message_payload,
        args=(CHAT_ID, text),
        daemon=True,
    ).start()
    return True


def send_photo(photo_path, caption=""):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram disabled: BOT_TOKEN or CHAT_ID missing")
        return False

    threading.Thread(
        target=_send_document_payload,
        args=(CHAT_ID, photo_path, caption),
        daemon=True,
    ).start()
    return True


def send_message_to_chat(chat_id, text):
    if not BOT_TOKEN or not chat_id:
        print("Telegram user notification disabled: BOT_TOKEN or chat_id missing")
        return False

    threading.Thread(
        target=_send_message_payload,
        args=(chat_id, text),
        daemon=True,
    ).start()
    return True
