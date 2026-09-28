import hashlib
import json
import re
from datetime import datetime, timedelta

from app.database import begin_locked_transaction, connect

MAX_SUBJECT_LENGTH = 500
MAX_FROM_LENGTH = 320
MAX_MESSAGE_ID_LENGTH = 500
MAX_PROVIDER_LENGTH = 60
MAX_BODY_LENGTH = 100000
MAX_RAW_LENGTH = 200000

EMAIL_STATUS_NEW = "new"

PHONE_RE = re.compile(
    r"(?:\+7|8)[\s\-\(]*\d{3}[\)\s\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}"
)
ADDRESS_LABEL_RE = re.compile(r"адрес\s*[:\-]\s*(?P<addr>[^\n]{3,160})", re.IGNORECASE)
ADDRESS_STREET_RE = re.compile(
    r"(?i)(ул\.|улица|проспект|просп\.|пр-т|пр\.|пер\.|переулок|шоссе|ш\.|"
    r"бульвар|б-р|набережная|наб\.|площадь|пл\.)\s+(?P<addr>[^\n]{2,150})"
)
NAME_RE = re.compile(r"меня зовут\s+([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)", re.IGNORECASE)
DATE_NUMERIC_RE = re.compile(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b")

RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5,
    "июня": 6, "июля": 7, "августа": 8, "сентября": 9, "октября": 10,
    "ноября": 11, "декабря": 12,
}
RU_WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "среда": 2, "среду": 2, "четверг": 3,
    "пятница": 4, "пятницу": 4, "суббота": 5, "субботу": 5,
    "воскресенье": 6,
}


def _extract_phone(text):
    match = PHONE_RE.search(text)
    if not match:
        return ""
    digits = re.sub(r"\D", "", match.group(0))
    if digits.startswith("8"):
        digits = "7" + digits[1:]
    return "+" + digits


def _extract_address(body_text):
    for line in str(body_text or "").splitlines():
        label = ADDRESS_LABEL_RE.search(line)
        if label:
            return label.group("addr").strip(" ,.;\t")[:160]
        street = ADDRESS_STREET_RE.search(line)
        if street:
            return line[street.start():].strip(" ,.;\t")[:160]
    return ""


def _extract_name(body_text, from_name):
    if from_name:
        return from_name
    match = NAME_RE.search(str(body_text or ""))
    return match.group(1) if match else ""


def _extract_date(text, now):
    lowered = text.lower()

    if "послезавтра" in lowered:
        return (now + timedelta(days=2)).strftime("%Y-%m-%d")
    if "завтра" in lowered:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")

    month_match = re.search(
        r"\b(\d{1,2})\s+(" + "|".join(RU_MONTHS) + r")\b", lowered
    )
    if month_match:
        day = int(month_match.group(1))
        month = RU_MONTHS[month_match.group(2)]
        try:
            return datetime(now.year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return ""

    numeric = DATE_NUMERIC_RE.search(text)
    if numeric:
        day, month = int(numeric.group(1)), int(numeric.group(2))
        year = int(numeric.group(3)) if numeric.group(3) else now.year
        if year < 100:
            year += 2000
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return ""

    for word, weekday in RU_WEEKDAYS.items():
        if re.search(r"\b" + word + r"\b", lowered):
            days_ahead = (weekday - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    return ""


def _extract_service(text, service_names):
    lowered = text.lower()
    best = ""
    for name in service_names:
        name_text = str(name or "").strip()
        if len(name_text) < 3:
            continue
        if name_text.lower() in lowered and len(name_text) > len(best):
            best = name_text
    return best


def extract_email_fields(body_text, subject, from_name, service_names, now=None):
    now = now or datetime.now()
    text = "\n".join([str(subject or ""), str(body_text or "")])

    return {
        "name": _extract_name(body_text, from_name),
        "phone": _extract_phone(text),
        "address": _extract_address(body_text),
        "date": _extract_date(text, now),
        "service": _extract_service(text, service_names),
    }


def get_company_service_names(company_id):
    conn = connect()

    try:
        c = conn.cursor()
        rows = c.execute("""
        SELECT name
        FROM catalog_items
        WHERE company_id=? AND COALESCE(active, 1)=1
        ORDER BY name
        LIMIT 500
        """, (company_id,)).fetchall()
        return [row["name"] for row in rows]
    finally:
        conn.close()


def parse_extracted_fields(raw_json):
    try:
        data = json.loads(raw_json or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


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

        extracted = extract_email_fields(
            payload["body_text"],
            payload["subject"],
            payload["from_name"],
            get_company_service_names(payload["company_id"]),
        )

        c.execute("""
        INSERT INTO email_messages (
            company_id, provider, dedupe_key, message_id,
            from_email, from_name, subject, body_text, raw_source,
            status, received_at, created_at, extracted_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
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
            json.dumps(extracted, ensure_ascii=False),
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
