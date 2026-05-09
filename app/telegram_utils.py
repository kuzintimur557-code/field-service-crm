import requests

BOT_TOKEN = "8466880508:AAECt2BpqJB_KzWIJT1Tv27MaJNjGBjrUSc"
CHAT_ID = "7739861626"


def send_message(text):

    try:

        url = f"https://api.telegram.org/bot{8466880508:AAECt2BpqJB_KzWIJT1Tv27MaJNjGBjrUSc}/sendMessage"

        requests.post(url, data={
            "chat_id": 7739861626,
            "text": text
        })

    except:
        pass


def send_photo(filepath, caption=""):

    try:

        url = f"https://api.telegram.org/bot{8466880508:AAECt2BpqJB_KzWIJT1Tv27MaJNjGBjrUSc}/sendPhoto"

        with open(filepath, "rb") as photo:

            requests.post(
                url,
                data={
                    "chat_id": 7739861626,
                    "caption": caption
                },
                files={
                    "photo": photo
                }
            )

    except:
        pass