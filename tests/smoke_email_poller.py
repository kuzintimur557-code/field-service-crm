import os
import sys
import tempfile
import threading
import urllib.request
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "scripts"))
import email_poller


class IntakeStub(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        secret = self.headers.get("x-inbox-secret", "")
        if secret != "poller-test-secret":
            self.send_response(403)
            self.end_headers()
            return
        IntakeStub.received.append((self.path, body))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "created": True, "id": 1}).encode())

    def log_message(self, *args):
        pass


def main():
    with tempfile.TemporaryDirectory():
        # url builder
        assert email_poller.build_intake_url("http://x.ru", 5) == (
            "http://x.ru/api/inbox/email?company_id=5"
        )

        # config validation
        with patch.dict(
            os.environ,
            {
                "IMAP_HOST": "imap.test",
                "IMAP_USER": "u",
                "IMAP_PASSWORD": "p",
                "INBOX_COMPANY_ID": "3",
                "INBOX_WEBHOOK_SECRET": "s",
                "APP_BASE_URL": "http://x.ru",
            },
            clear=False,
        ):
            config = email_poller.get_poller_config()
            assert email_poller.validate_config(config) == []
            assert config["mailbox"] == "INBOX"

        with patch.dict(os.environ, {"IMAP_HOST": ""}, clear=False):
            missing = email_poller.validate_config(email_poller.get_poller_config())
            assert "imap_host" in missing

        # stub intake endpoint
        server = HTTPServer(("127.0.0.1", 0), IntakeStub)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()

        url = f"http://127.0.0.1:{port}/api/inbox/email?company_id=1"
        status, body = email_poller.post_raw_email(
            url, "poller-test-secret", b"From: a@b.c\r\n\r\nhi"
        )
        assert status == 200 and '"ok": true' in body
        assert IntakeStub.received[0][1].startswith(b"From: a@b.c")

        # wrong secret rejected
        try:
            email_poller.post_raw_email(url, "wrong", b"x")
        except urllib.error.HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("wrong secret must be rejected")
        server.shutdown()

        # full poller against fake IMAP
        import imaplib

        class FakeImap:
            def __init__(self, *args, **kwargs):
                self.marked = []
                self.logged_out = False

            def login(self, user, password):
                self.user = user

            def select(self, mailbox):
                self.mailbox = mailbox

            def search(self, charset, criterion):
                return "OK", [b"101 102"]

            def fetch(self, message_id, spec):
                return "OK", [(b"1 (RFC822 {64}", b"From: ivan@x.ru\r\n\r\nbody" + message_id)]

            def store(self, message_id, cmd, flags):
                self.marked.append(message_id)
                return "OK", None

            def logout(self):
                self.logged_out = True

        fake = FakeImap()

        with patch.object(email_poller.imaplib, "IMAP4_SSL", return_value=fake), \
             patch.dict(
                os.environ,
                {
                    "IMAP_HOST": "imap.test",
                    "IMAP_USER": "u",
                    "IMAP_PASSWORD": "p",
                    "INBOX_COMPANY_ID": "1",
                    "INBOX_WEBHOOK_SECRET": "poller-test-secret",
                    "APP_BASE_URL": "http://127.0.0.1:1",  # unreachable on purpose
                },
                clear=False,
             ):
            # delivery fails -> message stays unseen, poller reports failure
            summary = email_poller.run_poller(
                email_poller.get_poller_config(), log=lambda m: None
            )
            assert summary == {"delivered": 0, "failed": 2}
            assert fake.marked == []

        # main() reports missing config
        with patch.dict(
            os.environ,
            {"IMAP_HOST": "", "IMAP_USER": "", "IMAP_PASSWORD": "", "INBOX_WEBHOOK_SECRET": "", "APP_BASE_URL": "", "INBOX_COMPANY_ID": ""},
            clear=False,
        ):
            assert email_poller.main() == 2

    print("Email poller smoke passed.")


if __name__ == "__main__":
    main()
