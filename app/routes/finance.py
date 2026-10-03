"""Finance, finance summary and payroll routes."""

import csv
import io
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.database import connect
from app.deps import (
    get_role,
    get_user,
    get_user_company_id,
    update_last_seen,
)
from app.services.common import (
    build_dashboard_links,
    create_notification,
    format_task_workers,
    get_company_settings,
    get_task_worker_chat_ids,
    get_task_worker_names,
    require_feature,
    role_label,
    worker_task_condition,
    worker_task_params,
)
from app.templating import templates

router = APIRouter()


def run_automation_event(*args, **kwargs):
    from app.main import run_automation_event as _impl

    return _impl(*args, **kwargs)


def send_message(*args, **kwargs):
    from app.main import send_message as _impl

    return _impl(*args, **kwargs)

@router.get("/finance/export")
async def finance_export(
    request: Request,
    month: str = "",
    payment_filter: str = "",
    worker: str = "",
    profit_filter: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    if not month:
        month = datetime.now().strftime("%Y-%m")
    selected_payment_filter = payment_filter if payment_filter in ("paid", "partial", "unpaid") else ""
    selected_worker = str(worker or "").strip()
    selected_profit_filter = profit_filter if profit_filter == "loss" else ""

    conn = connect()
    c = conn.cursor()

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "finance")

    if disabled_response:
        return disabled_response



    workers = c.execute("""
    SELECT id, username, commission_percent
    FROM users
    WHERE role='worker' AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()
    worker_names = [row["username"] for row in workers]
    worker_ids = {
        row["username"]: row["id"]
        for row in workers
    }
    worker_commissions = {
        row["username"]: float(row["commission_percent"] or 0)
        for row in workers
    }
    payroll_payouts = c.execute("""
    SELECT worker_id, amount
    FROM payroll_payouts
    WHERE company_id=? AND month=? AND status='paid'
    """, (company_id, month)).fetchall()
    payroll_payout_map = {
        row["worker_id"]: round(float(row["amount"] or 0), 1)
        for row in payroll_payouts
    }

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0 AND company_id=? AND task_date LIKE ?
    ORDER BY task_date DESC
    """, (company_id, f"{month}%")).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    worker_finance = {}

    writer.writerow([
        "Номер",
        "Дата",
        "Клиент",
        "Телефон",
        "Адрес",
        "Исполнитель",
        "Статус заявки",
        "Статус оплаты",
        "Скидка",
        "Сумма",
        "Расходы",
        "Прибыль",
        "Маржа %"
    ])

    for task in tasks:
        if selected_worker and selected_worker not in get_task_worker_names(task):
            continue

        items = c.execute("""
        SELECT *
        FROM task_items
        WHERE task_id=?
        """, (task["id"],)).fetchall()
        expenses = c.execute("""
        SELECT *
        FROM task_expenses
        WHERE task_id=?
        """, (task["id"],)).fetchall()

        task_total = sum(item["total"] for item in items)
        task_profit = sum(item["profit"] for item in items)
        discount_amount = float(task["discount_amount"] or 0) if "discount_amount" in task.keys() else 0
        task_expenses_total = sum(expense["amount"] for expense in expenses)

        if not items:
            try:
                task_total = float(task["price"] or 0)
            except Exception:
                task_total = 0
            task_profit = 0

        if discount_amount < 0:
            discount_amount = 0

        task_total = max(task_total - discount_amount, 0)
        task_profit = task_profit - discount_amount - task_expenses_total

        payment_status = task["payment_status"] if "payment_status" in task.keys() else "Не оплачено"
        task_margin = round((task_profit / task_total) * 100, 1) if task_total else 0

        if selected_payment_filter == "paid" and payment_status != "Оплачено":
            continue
        if selected_payment_filter == "partial" and payment_status != "Частично оплачено":
            continue
        if selected_payment_filter == "unpaid" and payment_status != "Не оплачено":
            continue
        if selected_profit_filter == "loss" and task_profit >= 0:
            continue

        task_worker_names = [
            worker_name for worker_name in get_task_worker_names(task)
            if worker_name in worker_names
        ]

        if not task_worker_names:
            task_worker_names = ["Не назначены"]

        worker_share_count = len(task_worker_names)

        for worker_name in task_worker_names:
            if worker_name not in worker_finance:
                worker_finance[worker_name] = {
                    "worker_id": worker_ids.get(worker_name),
                    "worker": worker_name,
                    "commission_percent": worker_commissions.get(worker_name, 0),
                    "tasks": 0,
                    "total": 0,
                    "expenses": 0,
                    "profit": 0
                }

            worker_finance[worker_name]["tasks"] += 1
            worker_finance[worker_name]["total"] += task_total / worker_share_count
            worker_finance[worker_name]["expenses"] += task_expenses_total / worker_share_count
            worker_finance[worker_name]["profit"] += task_profit / worker_share_count

        writer.writerow([
            task["id"],
            task["task_date"],
            task["client"],
            task["phone"],
            task["address"],
            format_task_workers(task),
            task["status"],
            payment_status,
            discount_amount,
            task_total,
            task_expenses_total,
            task_profit,
            task_margin
        ])

    worker_finance_rows = []

    for worker_row in worker_finance.values():
        worker_row["total"] = round(worker_row["total"], 1)
        worker_row["expenses"] = round(worker_row["expenses"], 1)
        worker_row["profit"] = round(worker_row["profit"], 1)
        worker_row["payout"] = round(worker_row["profit"] * worker_row["commission_percent"] / 100, 1)
        worker_row["paid_amount"] = payroll_payout_map.get(worker_row["worker_id"], 0)
        worker_row["due_amount"] = round(max(worker_row["payout"] - worker_row["paid_amount"], 0), 1)
        worker_row["payout_status"] = "Не выплачено"
        if worker_row["paid_amount"] > 0:
            worker_row["payout_status"] = "Выплачено" if worker_row["paid_amount"] >= worker_row["payout"] else "Частично"
        worker_finance_rows.append(worker_row)

    worker_finance_rows.sort(key=lambda row: row["profit"], reverse=True)

    if worker_finance_rows:
        total_worker_payout = round(sum(row["payout"] for row in worker_finance_rows), 1)
        total_worker_paid = round(sum(row["paid_amount"] for row in worker_finance_rows), 1)
        total_worker_due = round(sum(row["due_amount"] for row in worker_finance_rows), 1)

        writer.writerow([])
        writer.writerow(["Финансы по исполнителям"])
        writer.writerow([
            "Исполнитель",
            "Заявки",
            "Выручка",
            "Расходы",
            "Прибыль",
            "Процент",
            "Выплата",
            "Статус зарплаты",
            "Выплачено",
            "Остаток"
        ])

        for worker_row in worker_finance_rows:
            writer.writerow([
                worker_row["worker"],
                worker_row["tasks"],
                worker_row["total"],
                worker_row["expenses"],
                worker_row["profit"],
                worker_row["commission_percent"],
                worker_row["payout"],
                worker_row["payout_status"],
                worker_row["paid_amount"],
                worker_row["due_amount"]
            ])

        writer.writerow([])
        writer.writerow(["Итого начислено ЗП", total_worker_payout])
        writer.writerow(["Итого выплачено ЗП", total_worker_paid])
        writer.writerow(["Итого остаток ЗП", total_worker_due])

    conn.close()

    content = output.getvalue()
    output.close()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=finance_{month}.csv"
        }
    )


@router.get("/finance/summary/export")
async def finance_summary_export(request: Request, month: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "finance")

    if disabled_response:
        return disabled_response

    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
    SELECT
        month,
        client_name,
        price,
        expense_total,
        payroll_total,
        profit
    FROM finance_summary
    WHERE company_id=?
      AND month=?
    ORDER BY client_name
    """, (company_id, month)).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Месяц",
        "Клиент",
        "Выручка",
        "Расходы",
        "Зарплаты",
        "Прибыль",
        "Чистая прибыль"
    ])

    for row in rows:
        row_profit = float(row["profit"] or 0)
        row_payroll = float(row["payroll_total"] or 0)

        writer.writerow([
            row["month"],
            row["client_name"] or "Без клиента",
            round(float(row["price"] or 0), 2),
            round(float(row["expense_total"] or 0), 2),
            round(row_payroll, 2),
            round(row_profit, 2),
            round(row_profit - row_payroll, 2)
        ])

    conn.close()

    content = output.getvalue()
    output.close()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=finance_summary_{month}.csv"
        }
    )

@router.get("/finance/summary", response_class=HTMLResponse)
async def finance_summary_page(request: Request, month: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "finance")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    finance_rows = c.execute("""
    SELECT
        price,
        expense_total,
        payroll_total,
        profit
    FROM finance_summary
    WHERE company_id=?
      AND month=?
    """, (company_id, month)).fetchall()

    revenue = round(sum(float(row["price"] or 0) for row in finance_rows), 1)
    expenses = round(sum(float(row["expense_total"] or 0) for row in finance_rows), 1)
    payroll_total = round(sum(float(row["payroll_total"] or 0) for row in finance_rows), 1)
    profit = round(sum(float(row["profit"] or 0) for row in finance_rows), 1)
    net_profit = round(profit - payroll_total, 1)

    monthly_rows = c.execute("""
    SELECT
        month,
        SUM(price) as revenue,
        SUM(expense_total) as expenses,
        SUM(payroll_total) as payroll_total,
        SUM(profit) as profit
    FROM finance_summary
    WHERE company_id=?
    GROUP BY month
    ORDER BY month DESC
    LIMIT 12
    """, (company_id,)).fetchall()

    monthly_summary = []

    for row in monthly_rows:
        row_profit = round(float(row["profit"] or 0), 1)
        row_payroll = round(float(row["payroll_total"] or 0), 1)

        monthly_summary.append({
            "month": row["month"],
            "revenue": round(float(row["revenue"] or 0), 1),
            "expenses": round(float(row["expenses"] or 0), 1),
            "payroll_total": row_payroll,
            "profit": row_profit,
            "net_profit": round(row_profit - row_payroll, 1)
        })

    monthly_chart_data = list(reversed(monthly_summary))

    top_profitable_clients = c.execute("""
    SELECT
        client_name,
        SUM(profit) as total_profit,
        SUM(price) as revenue
    FROM finance_summary
    WHERE company_id=?
      AND month=?
    GROUP BY client_name
    ORDER BY total_profit DESC
    LIMIT 10
    """, (company_id, month)).fetchall()

    top_profitable_workers = c.execute("""
    SELECT
        users.username as worker_name,
        SUM(payroll_payouts.amount) as total_paid,
        COUNT(payroll_payouts.id) as payouts_count
    FROM payroll_payouts
    JOIN users ON users.id = payroll_payouts.worker_id
    WHERE payroll_payouts.company_id=?
      AND payroll_payouts.month=?
      AND payroll_payouts.status='paid'
    GROUP BY payroll_payouts.worker_id, users.username
    ORDER BY total_paid DESC
    LIMIT 10
    """, (company_id, month)).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "finance_summary.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "month": month,
            "revenue": revenue,
            "expenses": expenses,
            "payroll_total": payroll_total,
            "profit": profit,
            "net_profit": net_profit,
            "monthly_summary": monthly_summary,
            "monthly_chart_data": monthly_chart_data,
            "top_profitable_clients": top_profitable_clients,
            "top_profitable_workers": top_profitable_workers,
            "settings": settings,
        }
    )




@router.get("/finance", response_class=HTMLResponse)
async def finance_page(
    request: Request,
    month: str = "",
    payment_filter: str = "",
    worker: str = "",
    sort: str = "",
    profit_filter: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "finance")

    if disabled_response:
        return disabled_response

    if not month:
        month = datetime.now().strftime("%Y-%m")
    selected_payment_filter = payment_filter if payment_filter in ("paid", "partial", "unpaid") else ""
    selected_worker = str(worker or "").strip()
    selected_sort = sort if sort in ("total", "profit", "margin", "expenses") else "date"
    selected_profit_filter = profit_filter if profit_filter == "loss" else ""

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0 AND company_id=? AND task_date LIKE ?
    ORDER BY task_date DESC
    """, (company_id, f"{month}%")).fetchall()

    workers = c.execute("""
    SELECT id, username, commission_percent
    FROM users
    WHERE role='worker' AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()
    worker_names = [row["username"] for row in workers]
    worker_ids = {
        row["username"]: row["id"]
        for row in workers
    }
    worker_commissions = {
        row["username"]: float(row["commission_percent"] or 0)
        for row in workers
    }
    payroll_payouts = c.execute("""
    SELECT worker_id, amount
    FROM payroll_payouts
    WHERE company_id=? AND month=? AND status='paid'
    """, (company_id, month)).fetchall()
    payroll_payout_map = {
        row["worker_id"]: round(float(row["amount"] or 0), 1)
        for row in payroll_payouts
    }

    if selected_worker not in worker_names:
        selected_worker = ""

    finance_items_map = {
        row["task_id"]: {
            "total": row["items_total"] or 0,
            "profit": row["items_profit"] or 0,
        }
        for row in c.execute("""
        SELECT task_id, SUM(total) AS items_total, SUM(profit) AS items_profit
        FROM task_items
        WHERE task_id IN (
            SELECT id FROM tasks
            WHERE archived=0 AND company_id=? AND task_date LIKE ?
        )
        GROUP BY task_id
        """, (company_id, f"{month}%")).fetchall()
    }
    finance_expenses_map = {
        row["task_id"]: row["expenses_total"] or 0
        for row in c.execute("""
        SELECT task_id, SUM(amount) AS expenses_total
        FROM task_expenses
        WHERE task_id IN (
            SELECT id FROM tasks
            WHERE archived=0 AND company_id=? AND task_date LIKE ?
        )
        GROUP BY task_id
        """, (company_id, f"{month}%")).fetchall()
    }

    total_estimate = 0
    total_profit = 0
    total_expenses = 0
    total_discounts = 0
    paid_total = 0
    partial_total = 0
    unpaid_total = 0

    rows = []
    worker_finance = {}

    for task in tasks:
        if selected_worker and selected_worker not in get_task_worker_names(task):
            continue

        has_items = task["id"] in finance_items_map
        items_totals = finance_items_map.get(task["id"], {"total": 0, "profit": 0})

        task_total = items_totals["total"]
        task_profit = items_totals["profit"]
        discount_amount = float(task["discount_amount"] or 0) if "discount_amount" in task.keys() else 0
        task_expenses_total = finance_expenses_map.get(task["id"], 0)

        if not has_items:
            try:
                task_total = float(task["price"] or 0)
            except Exception:
                task_total = 0
            task_profit = 0

        if discount_amount < 0:
            discount_amount = 0

        task_total = max(task_total - discount_amount, 0)
        task_profit = task_profit - discount_amount - task_expenses_total

        payment_status = task["payment_status"] if "payment_status" in task.keys() else "Не оплачено"
        task_margin = round((task_profit / task_total) * 100, 1) if task_total else 0

        if selected_payment_filter == "paid" and payment_status != "Оплачено":
            continue
        if selected_payment_filter == "partial" and payment_status != "Частично оплачено":
            continue
        if selected_payment_filter == "unpaid" and payment_status != "Не оплачено":
            continue
        if selected_profit_filter == "loss" and task_profit >= 0:
            continue

        task_worker_names = [
            worker_name for worker_name in get_task_worker_names(task)
            if worker_name in worker_names
        ]

        if not task_worker_names:
            task_worker_names = ["Не назначены"]

        worker_share_count = len(task_worker_names)

        for worker_name in task_worker_names:
            if worker_name not in worker_finance:
                worker_finance[worker_name] = {
                    "worker_id": worker_ids.get(worker_name),
                    "worker": worker_name,
                    "commission_percent": worker_commissions.get(worker_name, 0),
                    "tasks": 0,
                    "total": 0,
                    "expenses": 0,
                    "profit": 0,
                    "payout": 0,
                    "margin": 0
                }

            worker_finance[worker_name]["tasks"] += 1
            worker_finance[worker_name]["total"] += task_total / worker_share_count
            worker_finance[worker_name]["expenses"] += task_expenses_total / worker_share_count
            worker_finance[worker_name]["profit"] += task_profit / worker_share_count

        total_estimate += task_total
        total_profit += task_profit
        total_expenses += task_expenses_total
        total_discounts += discount_amount

        if payment_status == "Оплачено":
            paid_total += task_total
        elif payment_status == "Частично оплачено":
            partial_total += task_total
        else:
            unpaid_total += task_total

        rows.append({
            "id": task["id"],
            "client": task["client"],
            "worker": format_task_workers(task),
            "task_date": task["task_date"],
            "status": task["status"],
            "payment_status": payment_status,
            "discount": discount_amount,
            "total": task_total,
            "expenses": task_expenses_total,
            "profit": task_profit,
            "margin": task_margin
        })

    if selected_sort == "total":
        rows.sort(key=lambda row: row["total"], reverse=True)
    elif selected_sort == "profit":
        rows.sort(key=lambda row: row["profit"], reverse=True)
    elif selected_sort == "margin":
        rows.sort(key=lambda row: row["margin"], reverse=True)
    elif selected_sort == "expenses":
        rows.sort(key=lambda row: row["expenses"], reverse=True)

    worker_finance_stats = []

    for worker_row in worker_finance.values():
        worker_row["total"] = round(worker_row["total"], 1)
        worker_row["expenses"] = round(worker_row["expenses"], 1)
        worker_row["profit"] = round(worker_row["profit"], 1)
        worker_row["payout"] = round(worker_row["profit"] * worker_row["commission_percent"] / 100, 1)
        worker_row["paid_amount"] = payroll_payout_map.get(worker_row["worker_id"], 0)
        worker_row["due_amount"] = round(max(worker_row["payout"] - worker_row["paid_amount"], 0), 1)
        worker_row["payout_status"] = "Не выплачено"
        if worker_row["paid_amount"] > 0:
            worker_row["payout_status"] = "Выплачено" if worker_row["paid_amount"] >= worker_row["payout"] else "Частично"
        worker_row["margin"] = round((worker_row["profit"] / worker_row["total"]) * 100, 1) if worker_row["total"] else 0
        worker_finance_stats.append(worker_row)

    worker_finance_stats.sort(key=lambda row: row["profit"], reverse=True)
    total_worker_payout = round(sum(row["payout"] for row in worker_finance_stats), 1)
    total_worker_paid = round(sum(row["paid_amount"] for row in worker_finance_stats), 1)
    total_worker_due = round(sum(row["due_amount"] for row in worker_finance_stats), 1)

    settings = get_company_settings(company_id)

    conn.close()
    total_margin = round((total_profit / total_estimate) * 100, 1) if total_estimate else 0
    average_estimate = round(total_estimate / len(rows), 1) if rows else 0
    outstanding_total = partial_total + unpaid_total

    return templates.TemplateResponse(
        request,
        "finance.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "month": month,
            "selected_payment_filter": selected_payment_filter,
            "selected_worker": selected_worker,
            "selected_sort": selected_sort,
            "selected_profit_filter": selected_profit_filter,
            "workers": workers,
            "worker_finance_stats": worker_finance_stats,
            "rows": rows,
            "total_estimate": total_estimate,
            "total_profit": total_profit,
            "total_expenses": total_expenses,
            "total_discounts": total_discounts,
            "total_margin": total_margin,
            "average_estimate": average_estimate,
            "outstanding_total": outstanding_total,
            "paid_total": paid_total,
            "partial_total": partial_total,
            "unpaid_total": unpaid_total,
            "total_worker_payout": total_worker_payout,
            "total_worker_paid": total_worker_paid,
            "total_worker_due": total_worker_due,
            "settings": settings
        }
    )


@router.get("/payroll", response_class=HTMLResponse)
async def payroll_page(request: Request, month: str = "", payout_filter: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "payroll")

    if disabled_response:
        return disabled_response

    if not month:
        month = datetime.now().strftime("%Y-%m")
    selected_payout_filter = payout_filter if payout_filter in ("positive", "paid", "partial", "unpaid") else ""

    conn = connect()
    c = conn.cursor()

    workers = c.execute("""
    SELECT id, username, full_name, commission_percent
    FROM users
    WHERE role='worker' AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()
    worker_map = {
        worker["username"]: worker
        for worker in workers
    }

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0 AND company_id=? AND task_date LIKE ?
    """, (company_id, f"{month}%")).fetchall()

    paid_payouts = c.execute("""
    SELECT worker_id, amount, paid_at, paid_by, note
    FROM payroll_payouts
    WHERE company_id=? AND month=? AND status='paid'
    """, (company_id, month)).fetchall()
    paid_payout_map = {
        payout["worker_id"]: payout
        for payout in paid_payouts
    }
    payout_history_rows = c.execute("""
    SELECT
        p.worker_id,
        p.amount,
        p.paid_at,
        p.paid_by,
        p.note,
        u.username,
        u.full_name
    FROM payroll_payouts p
    JOIN users u ON u.id=p.worker_id
    WHERE p.company_id=? AND p.month=? AND p.status='paid'
    ORDER BY p.paid_at DESC
    """, (company_id, month)).fetchall()
    payout_history = [
        {
            "worker_id": row["worker_id"],
            "worker_name": row["full_name"] or row["username"],
            "worker_username": row["username"],
            "amount": round(float(row["amount"] or 0), 1),
            "paid_at": row["paid_at"],
            "paid_by": row["paid_by"],
            "note": row["note"] or ""
        }
        for row in payout_history_rows
    ]

    payroll_rows = {
        worker["username"]: {
            "id": worker["id"],
            "username": worker["username"],
            "name": worker["full_name"] or worker["username"],
            "commission_percent": float(worker["commission_percent"] or 0),
            "tasks": 0,
            "total": 0,
            "profit": 0,
            "payout": 0
        }
        for worker in workers
    }

    for task in tasks:
        task_worker_names = [
            worker_name for worker_name in get_task_worker_names(task)
            if worker_name in worker_map
        ]

        if not task_worker_names:
            continue

        items = c.execute("""
        SELECT *
        FROM task_items
        WHERE task_id=?
        """, (task["id"],)).fetchall()
        expenses = c.execute("""
        SELECT *
        FROM task_expenses
        WHERE task_id=?
        """, (task["id"],)).fetchall()

        task_total = sum(item["total"] for item in items)
        task_profit = sum(item["profit"] for item in items)
        discount_amount = float(task["discount_amount"] or 0) if "discount_amount" in task.keys() else 0
        task_expenses_total = sum(expense["amount"] for expense in expenses)

        if not items:
            try:
                task_total = float(task["price"] or 0)
            except Exception:
                task_total = 0
            task_profit = 0

        if discount_amount < 0:
            discount_amount = 0

        task_total = max(task_total - discount_amount, 0)
        task_profit = task_profit - discount_amount - task_expenses_total
        share_count = len(task_worker_names)

        for worker_name in task_worker_names:
            payroll_rows[worker_name]["tasks"] += 1
            payroll_rows[worker_name]["total"] += task_total / share_count
            payroll_rows[worker_name]["profit"] += task_profit / share_count

    rows = []

    for row in payroll_rows.values():
        row["total"] = round(row["total"], 1)
        row["profit"] = round(row["profit"], 1)
        row["payout"] = round(row["profit"] * row["commission_percent"] / 100, 1)
        paid_payout = paid_payout_map.get(row["id"])
        row["payout_paid"] = bool(paid_payout)
        row["paid_at"] = paid_payout["paid_at"] if paid_payout else ""
        row["paid_by"] = paid_payout["paid_by"] if paid_payout else ""
        row["payout_note"] = paid_payout["note"] if paid_payout else ""
        row["paid_amount"] = round(float(paid_payout["amount"] or 0), 1) if paid_payout else 0
        row["due_amount"] = round(max(row["payout"] - row["paid_amount"], 0), 1)
        row["payout_status"] = "Не выплачено"
        if row["payout_paid"]:
            row["payout_status"] = "Выплачено" if row["paid_amount"] >= row["payout"] else "Частично"
        rows.append(row)

    if selected_payout_filter == "positive":
        rows = [row for row in rows if row["payout"] > 0]
    if selected_payout_filter == "paid":
        rows = [row for row in rows if row["payout"] > 0 and row["payout_paid"] and row["paid_amount"] >= row["payout"]]
    if selected_payout_filter == "partial":
        rows = [row for row in rows if row["payout"] > 0 and row["payout_paid"] and row["paid_amount"] < row["payout"]]
    if selected_payout_filter == "unpaid":
        rows = [row for row in rows if row["payout"] > 0 and not row["payout_paid"]]

    rows.sort(key=lambda row: row["payout"], reverse=True)
    total_payout = round(sum(row["payout"] for row in rows), 1)
    total_paid = round(sum(row["paid_amount"] for row in rows if row["payout_paid"]), 1)
    total_due = round(sum(row["due_amount"] for row in rows), 1)
    total_profit = round(sum(row["profit"] for row in rows), 1)
    settings = get_company_settings(company_id)

    conn.close()

    return templates.TemplateResponse(
        request,
        "payroll.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "month": month,
            "selected_payout_filter": selected_payout_filter,
            "rows": rows,
            "total_payout": total_payout,
            "total_paid": total_paid,
            "total_due": total_due,
            "total_profit": total_profit,
            "payout_history": payout_history,
            "settings": settings
        }
    )


@router.get("/payroll/history", response_class=HTMLResponse)
async def payroll_history_page(request: Request, month: str = "", worker: str = "", paid_by: str = "", date_from: str = "", date_to: str = "", sort: str = "date_desc"):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "payroll")

    if disabled_response:
        return disabled_response

    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    query = """
    SELECT
        p.id,
        p.worker_id,
        p.amount,
        p.paid_at,
        p.paid_by,
        p.note,
        u.full_name as worker_name,
        u.username as worker_username
    FROM payroll_payouts p
    JOIN users u ON u.id=p.worker_id
    WHERE p.company_id=?
      AND p.month=?
    """

    params = [company_id, month]

    if worker:
        query += """
          AND (
            lower(u.username) LIKE ?
            OR lower(u.full_name) LIKE ?
          )
        """
        search = f"%{worker.lower()}%"
        params.extend([search, search])

    if paid_by:
        query += """
          AND lower(p.paid_by) LIKE ?
        """
        params.append(f"%{paid_by.lower()}%")

    if date_from:
        query += """
          AND p.paid_at >= ?
        """
        params.append(date_from)

    if date_to:
        query += """
          AND p.paid_at <= ?
        """
        params.append(date_to + " 23:59")

    if sort == "date_asc":
        query += """
        ORDER BY p.paid_at ASC
        """
    elif sort == "amount_desc":
        query += """
        ORDER BY p.amount DESC
        """
    elif sort == "amount_asc":
        query += """
        ORDER BY p.amount ASC
        """
    elif sort == "worker":
        query += """
        ORDER BY u.username ASC
        """
    else:
        sort = "date_desc"
        query += """
        ORDER BY p.paid_at DESC
        """

    payout_history_rows = c.execute(query, params).fetchall()

    payout_history = [
        dict(row)
        for row in payout_history_rows
    ]

    total_paid = round(sum(
        float(row["amount"] or 0)
        for row in payout_history
    ), 1)

    payouts_count = len(payout_history)

    workers_count = len(set(
        row["worker_id"]
        for row in payout_history
    ))

    average_payout = round(
        total_paid / payouts_count,
        1
    ) if payouts_count else 0

    top_workers_map = {}

    for row in payout_history:
        key = row["worker_id"]

        if key not in top_workers_map:
            top_workers_map[key] = {
                "worker_id": row["worker_id"],
                "worker_name": row["worker_name"],
                "worker_username": row["worker_username"],
                "amount": 0
            }

        top_workers_map[key]["amount"] += float(row["amount"] or 0)

    top_workers = sorted(
        top_workers_map.values(),
        key=lambda item: item["amount"],
        reverse=True
    )[:3]

    for item in top_workers:
        item["amount"] = round(item["amount"], 1)

    conn.close()
    settings = get_company_settings(company_id)

    return templates.TemplateResponse(
        request,
        "payroll_history.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "month": month,
            "worker": worker,
            "paid_by": paid_by,
            "date_from": date_from,
            "date_to": date_to,
            "sort": sort,
            "payout_history": payout_history,
            "total_paid": total_paid,
            "payouts_count": payouts_count,
            "workers_count": workers_count,
            "average_payout": average_payout,
            "top_workers": top_workers,
            "settings": settings
        }
    )


@router.get("/payroll/history/export")
async def payroll_history_export(
    request: Request,
    month: str = "",
    worker: str = "",
    paid_by: str = "",
    date_from: str = "",
    date_to: str = "",
    sort: str = "date_desc"
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "payroll")

    if disabled_response:
        return disabled_response


    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    query = """
    SELECT
        p.month,
        p.amount,
        p.paid_at,
        p.paid_by,
        p.note,
        u.username,
        u.full_name,
        u.position
    FROM payroll_payouts p
    JOIN users u ON u.id=p.worker_id
    WHERE p.company_id=?
      AND p.month=?
    """

    params = [company_id, month]

    if worker:
        query += """
          AND (
            lower(u.username) LIKE ?
            OR lower(u.full_name) LIKE ?
          )
        """
        search = f"%{worker.lower()}%"
        params.extend([search, search])

    if paid_by:
        query += """
          AND lower(p.paid_by) LIKE ?
        """
        params.append(f"%{paid_by.lower()}%")

    if date_from:
        query += """
          AND p.paid_at >= ?
        """
        params.append(date_from)

    if date_to:
        query += """
          AND p.paid_at <= ?
        """
        params.append(date_to + " 23:59")

    if sort == "date_asc":
        query += """
        ORDER BY p.paid_at ASC
        """
    elif sort == "amount_desc":
        query += """
        ORDER BY p.amount DESC
        """
    elif sort == "amount_asc":
        query += """
        ORDER BY p.amount ASC
        """
    elif sort == "worker":
        query += """
        ORDER BY u.username ASC
        """
    else:
        sort = "date_desc"
        query += """
        ORDER BY p.paid_at DESC
        """

    payouts = c.execute(query, params).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Журнал выплат"])
    writer.writerow(["Месяц", month])
    writer.writerow(["Фильтр исполнитель", worker or ""])
    writer.writerow(["Фильтр кем выплачено", paid_by or ""])
    writer.writerow(["Дата от", date_from or ""])
    writer.writerow(["Дата до", date_to or ""])
    writer.writerow(["Сортировка", sort])
    writer.writerow([])

    writer.writerow([
        "Исполнитель",
        "ФИО",
        "Должность",
        "Месяц",
        "Сумма выплаты",
        "Дата выплаты",
        "Кем выплачено",
        "Комментарий"
    ])

    total_paid = 0

    for payout in payouts:
        amount = round(float(payout["amount"] or 0), 1)
        total_paid += amount

        writer.writerow([
            payout["username"],
            payout["full_name"] or "",
            payout["position"] or "",
            payout["month"],
            amount,
            payout["paid_at"] or "",
            payout["paid_by"] or "",
            payout["note"] or ""
        ])

    writer.writerow([])
    writer.writerow(["Итого выплачено", round(total_paid, 1)])

    response = Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8"
    )

    response.headers["Content-Disposition"] = f"attachment; filename=payroll_history_{month}.csv"

    return response


@router.get("/payroll/export")
async def payroll_export(request: Request, month: str = "", payout_filter: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    if not month:
        month = datetime.now().strftime("%Y-%m")
    selected_payout_filter = payout_filter if payout_filter in ("positive", "paid", "partial", "unpaid") else ""

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "payroll")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    workers = c.execute("""
    SELECT id, username, full_name, commission_percent
    FROM users
    WHERE role='worker' AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()
    worker_map = {
        worker["username"]: worker
        for worker in workers
    }

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0 AND company_id=? AND task_date LIKE ?
    """, (company_id, f"{month}%")).fetchall()

    paid_payouts = c.execute("""
    SELECT worker_id, amount, paid_at, paid_by, note
    FROM payroll_payouts
    WHERE company_id=? AND month=? AND status='paid'
    """, (company_id, month)).fetchall()
    paid_payout_map = {
        payout["worker_id"]: payout
        for payout in paid_payouts
    }

    payroll_rows = {
        worker["username"]: {
            "id": worker["id"],
            "username": worker["username"],
            "name": worker["full_name"] or worker["username"],
            "commission_percent": float(worker["commission_percent"] or 0),
            "tasks": 0,
            "total": 0,
            "profit": 0,
            "payout": 0
        }
        for worker in workers
    }

    for task in tasks:
        task_worker_names = [
            worker_name for worker_name in get_task_worker_names(task)
            if worker_name in worker_map
        ]

        if not task_worker_names:
            continue

        items = c.execute("""
        SELECT *
        FROM task_items
        WHERE task_id=?
        """, (task["id"],)).fetchall()
        expenses = c.execute("""
        SELECT *
        FROM task_expenses
        WHERE task_id=?
        """, (task["id"],)).fetchall()

        task_total = sum(item["total"] for item in items)
        task_profit = sum(item["profit"] for item in items)
        discount_amount = float(task["discount_amount"] or 0) if "discount_amount" in task.keys() else 0
        task_expenses_total = sum(expense["amount"] for expense in expenses)

        if not items:
            try:
                task_total = float(task["price"] or 0)
            except Exception:
                task_total = 0
            task_profit = 0

        if discount_amount < 0:
            discount_amount = 0

        task_total = max(task_total - discount_amount, 0)
        task_profit = task_profit - discount_amount - task_expenses_total
        share_count = len(task_worker_names)

        for worker_name in task_worker_names:
            payroll_rows[worker_name]["tasks"] += 1
            payroll_rows[worker_name]["total"] += task_total / share_count
            payroll_rows[worker_name]["profit"] += task_profit / share_count

    rows = []

    for row in payroll_rows.values():
        row["total"] = round(row["total"], 1)
        row["profit"] = round(row["profit"], 1)
        row["payout"] = round(row["profit"] * row["commission_percent"] / 100, 1)
        paid_payout = paid_payout_map.get(row["id"])
        row["payout_paid"] = bool(paid_payout)
        row["paid_at"] = paid_payout["paid_at"] if paid_payout else ""
        row["paid_by"] = paid_payout["paid_by"] if paid_payout else ""
        row["payout_note"] = paid_payout["note"] if paid_payout else ""
        row["paid_amount"] = round(float(paid_payout["amount"] or 0), 1) if paid_payout else 0
        row["due_amount"] = round(max(row["payout"] - row["paid_amount"], 0), 1)
        row["payout_status"] = "Не выплачено"
        if row["payout_paid"]:
            row["payout_status"] = "Выплачено" if row["paid_amount"] >= row["payout"] else "Частично"
        rows.append(row)

    if selected_payout_filter == "positive":
        rows = [row for row in rows if row["payout"] > 0]
    if selected_payout_filter == "paid":
        rows = [row for row in rows if row["payout"] > 0 and row["payout_paid"] and row["paid_amount"] >= row["payout"]]
    if selected_payout_filter == "partial":
        rows = [row for row in rows if row["payout"] > 0 and row["payout_paid"] and row["paid_amount"] < row["payout"]]
    if selected_payout_filter == "unpaid":
        rows = [row for row in rows if row["payout"] > 0 and not row["payout_paid"]]

    rows.sort(key=lambda row: row["payout"], reverse=True)
    total_payout = round(sum(row["payout"] for row in rows), 1)
    total_paid = round(sum(row["paid_amount"] for row in rows if row["payout_paid"]), 1)
    total_due = round(sum(row["due_amount"] for row in rows), 1)
    total_profit = round(sum(row["profit"] for row in rows), 1)

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Исполнитель",
        "Логин",
        "Заявки",
        "Выручка",
        "Прибыль",
        "Процент",
        "Выплата",
        "Фактически выплачено",
        "Осталось выплатить",
        "Статус выплаты",
        "Дата выплаты",
        "Кем выплачено",
        "Комментарий"
    ])

    for row in rows:
        writer.writerow([
            row["name"],
            row["username"],
            row["tasks"],
            row["total"],
            row["profit"],
            row["commission_percent"],
            row["payout"],
            row["paid_amount"],
            row["due_amount"],
            row["payout_status"],
            row["paid_at"],
            row["paid_by"],
            row["payout_note"]
        ])

    writer.writerow([])
    writer.writerow(["Итого прибыль", total_profit])
    writer.writerow(["Итого выплаты", total_payout])
    writer.writerow(["Итого выплачено", total_paid])
    writer.writerow(["Итого осталось", total_due])

    content = output.getvalue()
    output.close()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=payroll_{month}.csv"
        }
    )


@router.post("/payroll/{worker_id}/mark-paid")
async def mark_payroll_paid(request: Request, worker_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/payroll?error=only_boss", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "payroll")

    if disabled_response:
        return disabled_response


    form = await request.form()
    month = (form.get("month") or datetime.now().strftime("%Y-%m")).strip()
    amount = form.get("amount") or "0"
    note = (form.get("note") or "").strip()
    payout_filter = form.get("payout_filter") or ""
    selected_payout_filter = payout_filter if payout_filter in ("positive", "paid", "partial", "unpaid") else ""

    try:
        amount = float(str(amount).replace(",", "."))
    except Exception:
        amount = 0

    if amount < 0:
        amount = 0

    conn = connect()
    c = conn.cursor()

    worker = c.execute("""
    SELECT *
    FROM users
    WHERE id=? AND company_id=? AND role='worker'
    """, (worker_id, company_id)).fetchone()

    if not worker:
        conn.close()
        redirect_url = f"/payroll?month={month}"
        if selected_payout_filter:
            redirect_url += f"&payout_filter={selected_payout_filter}"
        return RedirectResponse(redirect_url, status_code=302)

    paid_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    c.execute("""
    INSERT INTO payroll_payouts (
        company_id,
        worker_id,
        month,
        amount,
        status,
        paid_at,
        paid_by,
        note
    )
    VALUES (?, ?, ?, ?, 'paid', ?, ?, ?)
    ON CONFLICT(company_id, worker_id, month)
    DO UPDATE SET
        amount=excluded.amount,
        status='paid',
        paid_at=excluded.paid_at,
        paid_by=excluded.paid_by,
        note=excluded.note
    """, (company_id, worker_id, month, amount, paid_at, username, note))

    conn.commit()
    conn.close()

    run_automation_event(
        company_id,
        "payroll_payout_paid",
        "worker",
        worker_id,
        (
            f"Выплата сотруднику {worker['username']} отмечена: "
            f"{amount:g} за {month}"
        ),
        f"/workers/{worker_id}?month={month}",
    )

    redirect_url = f"/payroll?month={month}&payout_paid=1"
    if selected_payout_filter:
        redirect_url += f"&payout_filter={selected_payout_filter}"
    return RedirectResponse(redirect_url, status_code=302)


@router.post("/payroll/{worker_id}/note")
async def update_payroll_payout_note(request: Request, worker_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/payroll?error=only_boss", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "payroll")

    if disabled_response:
        return disabled_response


    form = await request.form()
    month = (form.get("month") or datetime.now().strftime("%Y-%m")).strip()
    note = (form.get("note") or "").strip()
    payout_filter = form.get("payout_filter") or ""
    selected_payout_filter = payout_filter if payout_filter in ("positive", "paid", "partial", "unpaid") else ""

    conn = connect()
    c = conn.cursor()

    worker = c.execute("""
    SELECT username
    FROM users
    WHERE id=? AND company_id=? AND role='worker'
    """, (worker_id, company_id)).fetchone()
    payout = c.execute("""
    SELECT note
    FROM payroll_payouts
    WHERE company_id=? AND worker_id=? AND month=? AND status='paid'
    """, (company_id, worker_id, month)).fetchone()
    previous_note = str(payout["note"] or "") if payout else ""

    c.execute("""
    UPDATE payroll_payouts
    SET note=?
    WHERE company_id=? AND worker_id=? AND month=? AND status='paid'
    """, (note, company_id, worker_id, month))

    conn.commit()
    conn.close()

    if worker and payout and previous_note != note:
        run_automation_event(
            company_id,
            "payroll_payout_note_updated",
            "worker",
            worker_id,
            f"Комментарий выплаты сотрудника {worker['username']} обновлён за {month}",
            f"/workers/{worker_id}?month={month}",
        )

    redirect_url = f"/payroll?month={month}&payout_note_updated=1"
    if selected_payout_filter:
        redirect_url += f"&payout_filter={selected_payout_filter}"
    return RedirectResponse(redirect_url, status_code=302)


@router.post("/payroll/{worker_id}/mark-unpaid")
async def mark_payroll_unpaid(request: Request, worker_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/payroll?error=only_boss", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "payroll")

    if disabled_response:
        return disabled_response


    form = await request.form()
    month = (form.get("month") or datetime.now().strftime("%Y-%m")).strip()
    payout_filter = form.get("payout_filter") or ""
    selected_payout_filter = payout_filter if payout_filter in ("positive", "paid", "partial", "unpaid") else ""

    conn = connect()
    c = conn.cursor()

    worker = c.execute("""
    SELECT username
    FROM users
    WHERE id=? AND company_id=? AND role='worker'
    """, (worker_id, company_id)).fetchone()
    payout = c.execute("""
    SELECT amount
    FROM payroll_payouts
    WHERE company_id=? AND worker_id=? AND month=?
    """, (company_id, worker_id, month)).fetchone()

    c.execute("""
    DELETE FROM payroll_payouts
    WHERE company_id=? AND worker_id=? AND month=?
    """, (company_id, worker_id, month))

    conn.commit()
    conn.close()

    if worker and payout:
        run_automation_event(
            company_id,
            "payroll_payout_unpaid",
            "worker",
            worker_id,
            f"Выплата сотруднику {worker['username']} отменена за {month}",
            f"/workers/{worker_id}?month={month}",
        )

    redirect_url = f"/payroll?month={month}&payout_unpaid=1"
    if selected_payout_filter:
        redirect_url += f"&payout_filter={selected_payout_filter}"
    return RedirectResponse(redirect_url, status_code=302)
