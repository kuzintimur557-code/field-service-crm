"""Billing invoice helpers: summaries, reminders, invoices, exports."""

import calendar
from datetime import datetime, timedelta
from urllib.parse import urlencode

from app.database import connect
from app.services.common import create_notification
from app.services.plans import (
    format_rub_amount,
    get_plan_label,
    get_plan_monthly_price,
    get_plan_price_label,
    normalize_plan,
)

BILLING_INVOICE_STATUSES = {
    "draft": {
        "label": "Черновик",
        "tone": "muted",
    },
    "issued": {
        "label": "Выставлен",
        "tone": "warning",
    },
    "paid": {
        "label": "Оплачен",
        "tone": "ok",
    },
    "overdue": {
        "label": "Просрочен",
        "tone": "danger",
    },
    "canceled": {
        "label": "Отменён",
        "tone": "muted",
    },
}

def fetch_billing_plan_history(c, company_id, limit=6):
    query = """
    SELECT *
    FROM company_settings_history
    WHERE company_id=?
      AND details LIKE '%Тариф:%'
    ORDER BY id DESC
    """
    params = [company_id]

    if limit:
        query += "\nLIMIT ?"
        params.append(limit)

    return c.execute(query, params).fetchall()

def normalize_billing_invoice_status(status):
    normalized_status = str(status or "draft").strip().lower()
    return (
        normalized_status
        if normalized_status in BILLING_INVOICE_STATUSES
        else "draft"
    )


def normalize_billing_invoice_filter(status):
    normalized_status = str(status or "all").strip().lower()
    return (
        normalized_status
        if normalized_status == "all" or normalized_status in BILLING_INVOICE_STATUSES
        else "all"
    )


def get_billing_invoice_status_meta(status):
    return BILLING_INVOICE_STATUSES[normalize_billing_invoice_status(status)]


def get_billing_invoice_status_options():
    return [
        {
            "key": "all",
            "label": "Все",
        },
        *[
            {
                "key": status_key,
                "label": status_meta["label"],
            }
            for status_key, status_meta in BILLING_INVOICE_STATUSES.items()
        ],
    ]

def build_billing_invoice_rows(rows):
    invoice_rows = []

    for row in rows:
        invoice = dict(row)
        status_meta = get_billing_invoice_status_meta(invoice.get("status"))
        invoice["status_code"] = normalize_billing_invoice_status(
            invoice.get("status")
        )
        invoice["status_label"] = status_meta["label"]
        invoice["status_tone"] = status_meta["tone"]
        invoice["plan_label"] = get_plan_label(invoice.get("plan"))
        invoice["amount_label"] = format_rub_amount(invoice.get("amount"))
        invoice_rows.append(invoice)

    return invoice_rows


def build_billing_invoice_summary(invoices):
    total_amount = sum(float(invoice.get("amount") or 0) for invoice in invoices)
    unpaid_amount = sum(
        float(invoice.get("amount") or 0)
        for invoice in invoices
        if invoice.get("status_code") in ("draft", "issued", "overdue")
    )
    paid_amount = sum(
        float(invoice.get("amount") or 0)
        for invoice in invoices
        if invoice.get("status_code") == "paid"
    )

    return {
        "count": len(invoices),
        "total_amount": round(total_amount, 2),
        "paid_amount": round(paid_amount, 2),
        "unpaid_amount": round(unpaid_amount, 2),
        "total_amount_label": format_rub_amount(total_amount),
        "paid_amount_label": format_rub_amount(paid_amount),
        "unpaid_amount_label": format_rub_amount(unpaid_amount),
        "overdue_count": sum(
            1 for invoice in invoices if invoice.get("status_code") == "overdue"
        ),
    }


def parse_billing_due_date(value):
    try:
        return datetime.strptime(str(value or ""), "%Y-%m-%d").date()
    except ValueError:
        return None


def build_billing_next_payment_summary(invoices, today=None):
    today = today or datetime.now().date()
    unpaid_statuses = {"draft", "issued", "overdue"}
    candidates = []

    for invoice in invoices:
        status = normalize_billing_invoice_status(invoice.get("status_code"))

        if status not in unpaid_statuses:
            continue

        due_date = parse_billing_due_date(invoice.get("due_date"))
        sort_date = due_date or datetime.max.date()
        candidates.append((sort_date, int(invoice.get("id") or 0), invoice))

    if not candidates:
        return {
            "has_invoice": False,
            "invoice": None,
            "label": "Нет платежей",
            "tone": "ok",
            "days_left": None,
            "overdue": False,
            "link": "/billing/invoices",
        }

    candidates.sort(key=lambda item: (item[0], item[1]))
    _, _, invoice = candidates[0]
    due_date = parse_billing_due_date(invoice.get("due_date"))
    days_left = None
    overdue = False
    tone = "warning"

    if due_date:
        days_left = (due_date - today).days

        if days_left < 0:
            overdue = True
            label = f"Просрочен на {abs(days_left)} дн."
            tone = "danger"
        elif days_left == 0:
            label = "Оплатить сегодня"
        elif days_left <= 7:
            label = f"Оплатить через {days_left} дн."
        else:
            label = f"Оплатить до {invoice['due_date']}"
            tone = "ok"
    else:
        label = "Дата оплаты не указана"

    return {
        "has_invoice": True,
        "invoice": invoice,
        "label": label,
        "tone": tone,
        "days_left": days_left,
        "overdue": overdue,
        "link": f"/billing/invoices/{invoice['id']}",
    }


def build_platform_billing_risk_summary(invoices, today=None):
    today = today or datetime.now().date()
    due_soon_end = today + timedelta(days=7)
    unpaid_statuses = {"draft", "issued", "overdue"}
    overdue_by_date = []
    due_soon = []

    for invoice in invoices:
        status = normalize_billing_invoice_status(invoice.get("status_code"))
        due_date = parse_billing_due_date(invoice.get("due_date"))

        if not due_date or status not in unpaid_statuses:
            continue

        if due_date < today:
            overdue_by_date.append(invoice)
        elif today <= due_date <= due_soon_end:
            due_soon.append(invoice)

    overdue_amount = sum(float(invoice.get("amount") or 0) for invoice in overdue_by_date)
    due_soon_amount = sum(float(invoice.get("amount") or 0) for invoice in due_soon)

    return {
        "overdue_by_date_count": len(overdue_by_date),
        "overdue_by_date_amount": overdue_amount,
        "overdue_by_date_amount_label": format_rub_amount(overdue_amount),
        "due_soon_count": len(due_soon),
        "due_soon_amount": due_soon_amount,
        "due_soon_amount_label": format_rub_amount(due_soon_amount),
        "draft_count": sum(
            1 for invoice in invoices if invoice.get("status_code") == "draft"
        ),
        "issued_count": sum(
            1 for invoice in invoices if invoice.get("status_code") == "issued"
        ),
    }


def build_platform_billing_monthly_summary(invoices, today=None, limit=6):
    today = today or datetime.now().date()
    buckets = {}

    for invoice in invoices:
        period = str(invoice.get("period") or "Без периода").strip()
        status = normalize_billing_invoice_status(invoice.get("status_code"))
        amount = float(invoice.get("amount") or 0)
        due_date = parse_billing_due_date(invoice.get("due_date"))
        bucket = buckets.setdefault(
            period,
            {
                "period": period,
                "count": 0,
                "total_amount": 0,
                "paid_amount": 0,
                "unpaid_amount": 0,
                "overdue_count": 0,
                "overdue_amount": 0,
            },
        )
        bucket["count"] += 1
        bucket["total_amount"] += amount

        if status == "paid":
            bucket["paid_amount"] += amount
        elif status in {"draft", "issued", "overdue"}:
            bucket["unpaid_amount"] += amount

        if status == "overdue" or (
            status in {"draft", "issued"} and due_date and due_date < today
        ):
            bucket["overdue_count"] += 1
            bucket["overdue_amount"] += amount

    rows = sorted(
        buckets.values(),
        key=lambda item: item["period"],
        reverse=True,
    )

    for row in rows:
        row["total_amount"] = round(row["total_amount"], 2)
        row["paid_amount"] = round(row["paid_amount"], 2)
        row["unpaid_amount"] = round(row["unpaid_amount"], 2)
        row["overdue_amount"] = round(row["overdue_amount"], 2)
        row["total_amount_label"] = format_rub_amount(row["total_amount"])
        row["paid_amount_label"] = format_rub_amount(row["paid_amount"])
        row["unpaid_amount_label"] = format_rub_amount(row["unpaid_amount"])
        row["overdue_amount_label"] = format_rub_amount(row["overdue_amount"])

    return rows[:limit] if limit else rows


def record_platform_billing_activity(
    company_id,
    actor_username,
    action,
    details,
    target_username="",
):
    company_id = int(company_id or 0)

    if company_id <= 0:
        return None

    conn = connect()
    c = conn.cursor()

    if not target_username:
        company = c.execute("""
        SELECT owner_username
        FROM companies
        WHERE id=?
        """, (company_id,)).fetchone()
        target_username = (
            company["owner_username"]
            if company and company["owner_username"]
            else f"Компания #{company_id}"
        )

    user = c.execute("""
    SELECT id
    FROM users
    WHERE company_id=?
      AND username=?
    """, (company_id, target_username)).fetchone()
    user_id = user["id"] if user else 0

    c.execute("""
    INSERT INTO team_activity (
        company_id, user_id, target_username, actor_username,
        action, details, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        user_id,
        target_username,
        actor_username,
        action,
        details,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    activity_id = c.lastrowid
    conn.commit()
    conn.close()

    return activity_id


def fetch_platform_billing_invoice_activity(c, invoice, limit=10):
    invoice_number = str(invoice.get("invoice_number") or "").strip()

    if not invoice_number:
        return []

    rows = c.execute("""
    SELECT *
    FROM team_activity
    WHERE company_id=?
      AND action IN ('Счёт платформы создан', 'Статус счёта платформы')
      AND details LIKE ?
    ORDER BY id DESC
    LIMIT ?
    """, (
        invoice["company_id"],
        f"%{invoice_number}%",
        limit,
    )).fetchall()

    return [dict(row) for row in rows]


def build_platform_billing_invoice_activity_summary(activity):
    activity = list(activity or [])
    status_changes = sum(
        1 for event in activity
        if event.get("action") == "Статус счёта платформы"
    )
    created_events = sum(
        1 for event in activity
        if event.get("action") == "Счёт платформы создан"
    )
    latest = activity[0] if activity else {}

    return {
        "total": len(activity),
        "status_changes": status_changes,
        "created_events": created_events,
        "latest_action": latest.get("action") or "Событий пока нет",
        "latest_at": latest.get("created_at") or "",
        "latest_actor": latest.get("actor_username") or "",
    }


def notify_platform_billing_status_change(invoice, new_status):
    owner_username = str(invoice.get("owner_username") or "").strip()

    if not owner_username:
        return None

    new_status_label = get_billing_invoice_status_meta(new_status)["label"]
    invoice_number = invoice.get("invoice_number") or f"#{invoice.get('id')}"
    title = (
        "Счёт платформы оплачен"
        if new_status == "paid"
        else "Статус счёта платформы обновлён"
    )
    message = (
        f"Счёт {invoice_number}: "
        f"{invoice.get('status_label') or 'статус не указан'} "
        f"→ {new_status_label}. "
        f"Сумма: {invoice.get('amount_label') or format_rub_amount(invoice.get('amount'))}."
    )
    link = f"/billing/invoices/{invoice['id']}"

    create_notification(
        invoice["company_id"],
        owner_username,
        title,
        message,
        link,
    )

    return {
        "title": title,
        "message": message,
        "link": link,
    }


def sync_platform_billing_overdue_invoices(company_id="all", today=None):
    today = today or datetime.now().date()
    selected_company_id = normalize_platform_billing_company_id(company_id)
    today_value = today.strftime("%Y-%m-%d")
    query = """
    UPDATE billing_invoices
    SET status='overdue'
    WHERE status='issued'
      AND COALESCE(due_date, '')!=''
      AND due_date<?
    """
    params = [today_value]

    if selected_company_id != "all":
        query += "\nAND company_id=?"
        params.append(int(selected_company_id))

    conn = connect()
    c = conn.cursor()
    c.execute(query, params)
    updated_count = c.rowcount if c.rowcount is not None else 0
    conn.commit()
    conn.close()

    return {
        "updated": max(int(updated_count or 0), 0),
        "company_id": selected_company_id,
        "today": today_value,
    }


def get_platform_billing_reminder_payload(invoice, today=None):
    today = today or datetime.now().date()
    status = normalize_billing_invoice_status(invoice.get("status_code"))
    due_date = parse_billing_due_date(invoice.get("due_date"))

    if status not in {"issued", "overdue"} or not due_date:
        return None

    invoice_number = invoice.get("invoice_number") or f"#{invoice.get('id')}"
    period = invoice.get("period") or "период не указан"
    amount_label = invoice.get("amount_label") or format_rub_amount(
        invoice.get("amount")
    )
    link = f"/billing/invoices/{invoice['id']}"

    if status == "overdue" or due_date < today:
        return {
            "title": "Просрочен счёт платформы",
            "message": (
                f"Счёт {invoice_number} за {period} просрочен. "
                f"Сумма: {amount_label}. Оплатить до: {invoice['due_date']}."
            ),
            "link": link,
        }

    if today <= due_date <= today + timedelta(days=7):
        return {
            "title": "Скоро оплата счёта платформы",
            "message": (
                f"Счёт {invoice_number} за {period} скоро к оплате. "
                f"Сумма: {amount_label}. Оплатить до: {invoice['due_date']}."
            ),
            "link": link,
        }

    return None


def create_platform_billing_reminders(company_id="all", today=None):
    today = today or datetime.now().date()
    selected_company_id = normalize_platform_billing_company_id(company_id)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    sync_result = sync_platform_billing_overdue_invoices(
        selected_company_id,
        today=today,
    )

    conn = connect()
    c = conn.cursor()
    invoices = fetch_platform_billing_invoices(
        c,
        status_filter="all",
        company_id=selected_company_id,
    )
    created_count = 0
    skipped_count = 0
    checked_count = 0

    for invoice in invoices:
        owner_username = str(invoice.get("owner_username") or "").strip()
        payload = get_platform_billing_reminder_payload(invoice, today=today)

        if not owner_username or not payload:
            continue

        checked_count += 1
        existing_notification = c.execute("""
        SELECT id
        FROM notifications
        WHERE company_id=?
          AND username=?
          AND title=?
          AND link=?
          AND is_read=0
        """, (
            invoice["company_id"],
            owner_username,
            payload["title"],
            payload["link"],
        )).fetchone()

        if existing_notification:
            skipped_count += 1
            continue

        c.execute("""
        INSERT INTO notifications (
            company_id,
            username,
            title,
            message,
            link,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            invoice["company_id"],
            owner_username,
            payload["title"],
            payload["message"],
            payload["link"],
            now,
        ))
        created_count += 1

    conn.commit()
    conn.close()

    return {
        "created": created_count,
        "skipped": skipped_count,
        "checked": checked_count,
        "synced_overdue": sync_result["updated"],
        "company_id": selected_company_id,
    }


def build_billing_invoices_export_url(status_filter):
    if status_filter == "all":
        return "/billing/invoices/export"

    return "/billing/invoices/export?" + urlencode({"status": status_filter})


def normalize_platform_billing_company_id(company_id="all"):
    value = str(company_id or "all").strip().lower()

    if value in ("", "all"):
        return "all"

    try:
        parsed = int(value)
    except ValueError:
        return "all"

    return str(parsed) if parsed > 0 else "all"


def build_platform_billing_url(status_filter="all", company_id="all", export=False):
    status_filter = normalize_billing_invoice_filter(status_filter)
    company_id = normalize_platform_billing_company_id(company_id)
    params = {}

    if status_filter != "all":
        params["status"] = status_filter

    if company_id != "all":
        params["company_id"] = company_id

    base_url = "/platform/billing/export" if export else "/platform/billing"

    if not params:
        return base_url

    return base_url + "?" + urlencode(params)


def build_platform_billing_invoice_links(invoice_id, company_id):
    invoice_id = int(invoice_id or 0)
    company_id = int(company_id or 0)

    return {
        "page": f"/platform/billing/invoices/{invoice_id}",
        "export": f"/platform/billing/invoices/{invoice_id}/export",
        "status": f"/platform/billing/invoices/{invoice_id}/status",
        "company": f"/platform/companies/{company_id}",
        "billing": build_platform_billing_url(company_id=company_id),
    }


def build_platform_billing_links(status_filter="all", company_id="all"):
    status_filter = normalize_billing_invoice_filter(status_filter)
    company_id = normalize_platform_billing_company_id(company_id)

    return {
        "platform": "/platform",
        "base": "/platform/billing",
        "page": build_platform_billing_url(status_filter, company_id),
        "export": build_platform_billing_url(
            status_filter,
            company_id,
            export=True,
        ),
        "generate": "/platform/billing/generate",
        "reminders": "/platform/billing/reminders/send",
        "sync_overdue": "/platform/billing/overdue/sync",
    }


def normalize_billing_period(period=""):
    value = str(period or "").strip()

    try:
        parsed = datetime.strptime(value + "-01", "%Y-%m-%d")
        return parsed.strftime("%Y-%m")
    except ValueError:
        return datetime.now().strftime("%Y-%m")


def get_billing_period_due_date(period):
    normalized_period = normalize_billing_period(period)
    year, month = [int(part) for part in normalized_period.split("-")]
    last_day = calendar.monthrange(year, month)[1]
    return f"{normalized_period}-{last_day:02d}"


def build_billing_invoice_number(company_id, period):
    normalized_period = normalize_billing_period(period).replace("-", "")
    return f"BILL-{int(company_id)}-{normalized_period}"


def fetch_billing_invoices(c, company_id, limit=None, status_filter="all"):
    status_filter = normalize_billing_invoice_filter(status_filter)
    query = """
    SELECT *
    FROM billing_invoices
    WHERE company_id=?
    """
    params = [company_id]

    if status_filter != "all":
        query += "\nAND status=?"
        params.append(status_filter)

    query += "\nORDER BY id DESC"

    if limit:
        query += "\nLIMIT ?"
        params.append(limit)

    rows = c.execute(query, params).fetchall()
    return build_billing_invoice_rows(rows)


def generate_company_billing_invoice(company_id, period="", actor_username=""):
    company_id = int(company_id or 0)
    normalized_period = normalize_billing_period(period)
    invoice_number = build_billing_invoice_number(company_id, normalized_period)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = connect()
    c = conn.cursor()
    existing = c.execute("""
    SELECT *
    FROM billing_invoices
    WHERE company_id=?
      AND period=?
    ORDER BY id DESC
    LIMIT 1
    """, (company_id, normalized_period)).fetchone()

    if existing:
        invoice = build_billing_invoice_rows([existing])[0]
        conn.close()
        return {
            "created": False,
            "invoice": invoice,
        }

    settings = c.execute("""
    SELECT plan
    FROM company_settings
    WHERE company_id=?
    """, (company_id,)).fetchone()
    plan = normalize_plan(settings["plan"] if settings else "basic")
    amount = get_plan_monthly_price(plan)
    due_date = get_billing_period_due_date(normalized_period)
    notes = f"Сформировано автоматически: {actor_username or 'система'}"

    c.execute("""
    INSERT INTO billing_invoices (
        company_id,
        invoice_number,
        period,
        plan,
        amount,
        currency,
        status,
        due_date,
        paid_at,
        notes,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, 'RUB', 'draft', ?, '', ?, ?)
    """, (
        company_id,
        invoice_number,
        normalized_period,
        plan,
        amount,
        due_date,
        notes,
        created_at,
    ))
    invoice_id = c.lastrowid
    conn.commit()
    invoice = c.execute("""
    SELECT *
    FROM billing_invoices
    WHERE id=?
    """, (invoice_id,)).fetchone()
    conn.close()

    return {
        "created": True,
        "invoice": build_billing_invoice_rows([invoice])[0],
    }


def fetch_billing_invoice(c, company_id, invoice_id):
    row = c.execute("""
    SELECT *
    FROM billing_invoices
    WHERE company_id=?
      AND id=?
    """, (company_id, invoice_id)).fetchone()

    if not row:
        return None

    return build_billing_invoice_rows([row])[0]


def get_platform_billing_invoice_summary():
    conn = connect()
    c = conn.cursor()
    rows = c.execute("""
    SELECT *
    FROM billing_invoices
    ORDER BY id DESC
    """).fetchall()
    companies_with_invoices = c.execute("""
    SELECT COUNT(DISTINCT company_id)
    FROM billing_invoices
    """).fetchone()[0]
    conn.close()

    invoices = build_billing_invoice_rows(rows)
    summary = build_billing_invoice_summary(invoices)
    summary["risk_summary"] = build_platform_billing_risk_summary(invoices)
    summary["companies_with_invoices"] = int(companies_with_invoices or 0)
    summary["issued_count"] = sum(
        1 for invoice in invoices if invoice.get("status_code") == "issued"
    )
    summary["paid_count"] = sum(
        1 for invoice in invoices if invoice.get("status_code") == "paid"
    )

    return summary


def fetch_platform_billing_invoices(c, status_filter="all", company_id="all"):
    status_filter = normalize_billing_invoice_filter(status_filter)
    company_id = normalize_platform_billing_company_id(company_id)
    query = """
    SELECT
        billing_invoices.*,
        companies.name AS company_name,
        companies.owner_username AS owner_username
    FROM billing_invoices
    LEFT JOIN companies
      ON companies.id=billing_invoices.company_id
    WHERE 1=1
    """
    params = []

    if status_filter != "all":
        query += "\nAND billing_invoices.status=?"
        params.append(status_filter)

    if company_id != "all":
        query += "\nAND billing_invoices.company_id=?"
        params.append(int(company_id))

    query += "\nORDER BY billing_invoices.id DESC"

    rows = c.execute(query, params).fetchall()
    invoices = []

    for row in rows:
        invoice = build_billing_invoice_rows([row])[0]
        invoice["company_name"] = row["company_name"] or ""
        invoice["owner_username"] = row["owner_username"] or ""
        invoice["links"] = build_platform_billing_invoice_links(
            invoice["id"],
            invoice["company_id"],
        )
        invoices.append(invoice)

    return invoices


def fetch_platform_billing_invoice(c, invoice_id):
    row = c.execute("""
    SELECT
        billing_invoices.*,
        companies.name AS company_name,
        companies.owner_username AS owner_username
    FROM billing_invoices
    LEFT JOIN companies
      ON companies.id=billing_invoices.company_id
    WHERE billing_invoices.id=?
    """, (invoice_id,)).fetchone()

    if not row:
        return None

    invoice = build_billing_invoice_rows([row])[0]
    invoice["company_name"] = row["company_name"] or ""
    invoice["owner_username"] = row["owner_username"] or ""
    invoice["links"] = build_platform_billing_invoice_links(
        invoice["id"],
        invoice["company_id"],
    )
    return invoice


def get_platform_billing_company_options(c):
    rows = c.execute("""
    SELECT
        companies.id,
        companies.name,
        companies.owner_username,
        COALESCE(settings.plan, 'basic') AS plan
    FROM companies
    LEFT JOIN company_settings AS settings
      ON settings.company_id=companies.id
    ORDER BY lower(companies.name), companies.id
    """).fetchall()

    options = []

    for row in rows:
        plan = normalize_plan(row["plan"])
        options.append({
            "id": row["id"],
            "name": row["name"] or f"Компания #{row['id']}",
            "owner_username": row["owner_username"] or "",
            "plan": plan,
            "plan_label": get_plan_label(plan),
            "price_label": get_plan_price_label(plan),
            "links": {
                "page": f"/platform/companies/{row['id']}",
                "billing": build_platform_billing_url(
                    company_id=row["id"],
                ),
            },
        })

    return options
