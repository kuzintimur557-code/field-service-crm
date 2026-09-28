import hashlib

from app.database import begin_locked_transaction, connect

MAX_SUBJECT_LENGTH = 500
MAX_FROM_LENGTH = 320
MAX_MESSAGE_ID_LENGTH = 500
MAX_PROVIDER_LENGTH = 60
MAX_BODY_LENGTH = 100000
MAX_RAW_LENGTH = 200000

EMAIL_STATUS_NEW = "new"


def _clip(value, limit):
    return str(value or "").strip()[:limit]


def normalize_inbox_payload(data):
    if not isinstance(data, dict):
        raise ValueError("invalid_payload")

    try:
        company_id = int(data.get("company_id") or 0)
    except (TypeError, ValueError):
        raise ValueError("invalid_company_id")

    if company_id <= 0:
        raise ValueError("invalid_company_id")

    payload = {
        "company_id": company_id,
        "provider": _clip(data.get("provider"), MAX_PROVIDER_LENGTH),
        "message_id": _clip(data.get("message_id"), MAX_MESSAGE_ID_LENGTH),
        "from_email": _clip(data.get("from_email") or data.get("from"), MAX_FROM_LENGTH),
        "from_name": _clip(data.get("from_name"), MAX_FROM_LENGTH),
        "subject": _clip(data.get("subject"), MAX_SUBJECT_LENGTH),
        "body_text": _clip(data.get("text") or data.get("body"), MAX_BODY_LENGTH),
        "raw_source": _clip(data.get("raw"), MAX_RAW_LENGTH),
        "received_at": _clip(data.get("received_at") or data.get("date"), 40),
    }

    if not payload["from_email"] and not payload["subject"] and not payload["body_text"]:
        raise ValueError("empty_message")

    if not payload["raw_source"]:
        payload["raw_source"] = payload["body_text"]

    payload["dedupe_key"] = build_email_dedupe_key(payload)
    return payload


def build_email_dedupe_key(payload):
    provider = payload.get("provider", "")
    message_id = payload.get("message_id", "")

    if message_id:
        source = f"id:{provider}:{message_id}"
    else:
        source = "\x1f".join([
            "hash",
            provider,
            payload.get("from_email", "").lower(),
            payload.get("subject", ""),
            payload.get("received_at", ""),
            payload.get("body_text", "")[:2000],
        ])

    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def save_email_message(payload):
    conn = connect()

    try:
        c = conn.cursor()
        begin_locked_transaction(
            c,
            "email_inbox_save",
            payload["company_id"],
            payload["dedupe_key"],
        )

        existing = c.execute("""
        SELECT *
        FROM email_messages
        WHERE company_id=? AND dedupe_key=?
        """, (payload["company_id"], payload["dedupe_key"])).fetchone()

        if existing:
            conn.commit()
            return {"created": False, "message": dict(existing)}

        c.execute("""
        INSERT INTO email_messages (
            company_id, provider, dedupe_key, message_id,
            from_email, from_name, subject, body_text, raw_source,
            status, received_at, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            payload["company_id"],
            payload["provider"],
            payload["dedupe_key"],
            payload["message_id"],
            payload["from_email"],
            payload["from_name"],
            payload["subject"],
            payload["body_text"],
            payload["raw_source"],
            EMAIL_STATUS_NEW,
            payload["received_at"],
        ))

        message_id = c.lastrowid
        saved = c.execute(
            "SELECT * FROM email_messages WHERE id=?",
            (message_id,),
        ).fetchone()
        conn.commit()
        return {"created": True, "message": dict(saved)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_email_messages(company_id, status="", limit=100):
    conn = connect()

    try:
        c = conn.cursor()
        query = """
        SELECT *
        FROM email_messages
        WHERE company_id=?
        """
        params = [company_id]

        if status:
            query += " AND status=?"
            params.append(status)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        return [dict(row) for row in c.execute(query, params).fetchall()]
    finally:
        conn.close()
