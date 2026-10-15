"""Poll a mailbox over IMAP and forward unseen emails to the app inbox endpoint.

Configuration (environment variables):

    IMAP_HOST, IMAP_PORT, IMAP_USER, IMAP_PASSWORD  - mailbox credentials
    INBOX_COMPANY_ID                                 - target company id
    INBOX_WEBHOOK_SECRET                             - app intake secret
    APP_BASE_URL                                     - e.g. http://127.0.0.1:8000
    IMAP_MAILBOX                                     - default INBOX
    POLL_LIMIT                                       - max messages per run

Run manually or via cron:

    python scripts/email_poller.py

On successful delivery the message is marked as Seen; on failure it stays
unseen and will be retried on the next run.
"""

import imaplib
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def get_poller_config():
    return {
        "imap_host": os.getenv("IMAP_HOST", "").strip(),
        "imap_port": int(os.getenv("IMAP_PORT") or 993),
        "imap_user": os.getenv("IMAP_USER", "").strip(),
        "imap_password": os.getenv("IMAP_PASSWORD", "").strip(),
        "mailbox": os.getenv("IMAP_MAILBOX", "INBOX").strip() or "INBOX",
        "limit": max(1, int(os.getenv("POLL_LIMIT") or 20)),
        "company_id": int(os.getenv("INBOX_COMPANY_ID") or 0),
        "secret": os.getenv("INBOX_WEBHOOK_SECRET", "").strip(),
        "base_url": os.getenv("APP_BASE_URL", "").rstrip("/"),
    }


def validate_config(config):
    missing = [
        key for key in ("imap_host", "imap_user", "imap_password", "secret", "base_url")
        if not config[key]
    ]
    if config["company_id"] <= 0:
        missing.append("INBOX_COMPANY_ID")
    return missing


def build_intake_url(base_url, company_id):
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}/api/inbox/email?company_id={company_id}"


def post_raw_email(url, secret, raw_bytes, timeout=30):
    request = urllib.request.Request(
        url,
        data=raw_bytes,
        headers={
            "Content-Type": "message/rfc822",
            "x-inbox-secret": secret,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", errors="replace")[:500]


def fetch_unseen_raw_messages(connection, mailbox, limit):
    connection.select(mailbox)
    status, data = connection.search(None, "UNSEEN")
    if status != "OK":
        raise RuntimeError("IMAP search failed")

    message_ids = data[0].split()[:limit]
    messages = []

    for message_id in message_ids:
        status, fetched = connection.fetch(message_id, "(RFC822)")
        if status != "OK" or not fetched or not fetched[0]:
            continue
        messages.append((message_id, fetched[0][1]))

    return messages


def mark_seen(connection, message_id):
    connection.store(message_id, "+FLAGS", "\\Seen")


def run_poller(config, log=print):
    import ssl

    delivered = 0
    failed = 0

    context = ssl.create_default_context()
    connection = imaplib.IMAP4_SSL(
        config["imap_host"], config["imap_port"], ssl_context=context
    )

    try:
        connection.login(config["imap_user"], config["imap_password"])
        messages = fetch_unseen_raw_messages(
            connection, config["mailbox"], config["limit"]
        )
        url = build_intake_url(config["base_url"], config["company_id"])

        for message_id, raw_bytes in messages:
            try:
                status, body = post_raw_email(url, config["secret"], raw_bytes)
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                failed += 1
                log(f"delivery failed for uid {message_id.decode()}: {error}")
                continue

            if status == 200:
                mark_seen(connection, message_id)
                delivered += 1
                log(f"delivered uid {message_id.decode()}: {body[:160]}")
            else:
                failed += 1
                log(f"intake rejected uid {message_id.decode()}: HTTP {status} {body[:160]}")

    finally:
        try:
            connection.logout()
        except Exception:
            pass

    return {"delivered": delivered, "failed": failed}


def main():
    config = get_poller_config()
    missing = validate_config(config)
    if missing:
        print(f"Missing configuration: {', '.join(missing)}")
        print(
            "Set IMAP_HOST, IMAP_USER, IMAP_PASSWORD, INBOX_COMPANY_ID, "
            "INBOX_WEBHOOK_SECRET and APP_BASE_URL."
        )
        return 2

    try:
        summary = run_poller(config)
    except (imaplib.IMAP4.error, OSError) as error:
        print(f"Poller error: {error}")
        return 1

    print(f"Done. Delivered: {summary['delivered']}. Failed: {summary['failed']}.")
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
