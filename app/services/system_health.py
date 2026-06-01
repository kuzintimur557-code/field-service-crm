from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone

from app.database import connect
from app.services.ops_timeline import create_ops_timeline_event


@dataclass
class SystemHealthResult:
    score: int
    status: str
    failed_count: int
    skipped_count: int
    disabled_rules_count: int
    stale_rules_count: int
    retry_risk_count: int

    execution_health: int
    skipped_health: int
    automation_health: int
    stale_health: int
    retry_health: int
    warnings: list[str]
    critical: list[str]
    recommendations: list[str]

    def to_dict(self):
        return asdict(self)


class SystemHealthCalculator:
    def __init__(self, rules=None, events=None):
        self.rules = rules or []
        self.events = events or []

    def _value(self, item, key, default=None):
        if isinstance(item, dict):
            return item.get(key, default)

        try:
            if hasattr(item, "keys") and key in item.keys():
                return item[key]
        except Exception:
            pass

        return getattr(item, key, default)

    def _datetime_value(self, value):
        if not value:
            return None

        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                try:
                    parsed = datetime.strptime(value[:16], "%Y-%m-%d %H:%M")
                except ValueError:
                    return None
            value = parsed

        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        return value

    def calculate(self) -> SystemHealthResult:
        now = datetime.now(timezone.utc)
        since_24h = now - timedelta(hours=24)
        stale_cutoff = now - timedelta(days=7)

        failed_count = 0
        skipped_count = 0
        retry_risk_count = 0

        for event in self.events:
            status = self._value(event, "status", "") or ""
            created_at = self._datetime_value(self._value(event, "created_at"))

            is_recent = created_at is None or created_at >= since_24h

            if is_recent and status == "failed":
                failed_count += 1

            if is_recent and status == "skipped":
                skipped_count += 1

            retry_count = self._value(event, "retry_count", 0) or 0
            if retry_count >= 3:
                retry_risk_count += 1

        disabled_rules_count = 0
        stale_rules_count = 0

        for rule in self.rules:
            enabled = self._value(rule, "enabled", True)
            is_active = self._value(rule, "is_active", self._value(rule, "active", True))

            if enabled in (False, 0) or is_active in (False, 0):
                disabled_rules_count += 1

            last_run_at = self._datetime_value(self._value(rule, "last_run_at"))
            if last_run_at:
                if last_run_at < stale_cutoff:
                    stale_rules_count += 1

        penalty = 0
        penalty += min(30, failed_count * 5)
        penalty += min(20, skipped_count * 2)
        penalty += min(15, disabled_rules_count * 2)
        penalty += min(15, stale_rules_count * 2)
        penalty += min(20, retry_risk_count * 4)

        score = max(0, min(100, 100 - penalty))

        execution_health = max(0, 100 - min(30, failed_count * 5))
        skipped_health = max(0, 100 - min(20, skipped_count * 2))
        automation_health = max(0, 100 - min(15, disabled_rules_count * 2))
        stale_health = max(0, 100 - min(15, stale_rules_count * 2))
        retry_health = max(0, 100 - min(20, retry_risk_count * 4))

        warnings = []
        critical = []

        if failed_count:
            critical.append(f"Ошибок автоматизации за последние 24 часа: {failed_count}")

        if skipped_count:
            warnings.append(f"Пропущенных событий автоматизации за последние 24 часа: {skipped_count}")

        if disabled_rules_count:
            warnings.append(f"Отключённых правил автоматизации: {disabled_rules_count}")

        if stale_rules_count:
            warnings.append(f"Правил без запусков дольше 7 дней: {stale_rules_count}")

        if retry_risk_count:
            critical.append(f"Событий с высоким числом повторов: {retry_risk_count}")

        recommendations = []

        if failed_count:
            recommendations.append("Проверьте ошибочные события автоматизации и логи правил.")

        if skipped_count:
            recommendations.append("Проверьте пропущенные события и повторите корректные автоматизации.")

        if disabled_rules_count:
            recommendations.append("Проверьте отключённые правила и включите важные бизнес-автоматизации.")

        if stale_rules_count:
            recommendations.append("Проверьте правила, которые не запускались больше 7 дней.")

        if retry_risk_count:
            recommendations.append("Разберите события с частыми повторами и сломанные цепочки автоматизации.")

        if not recommendations:
            recommendations.append("Действия не требуются. Система автоматизации работает стабильно.")

        status = "healthy"
        if score < 85:
            status = "warning"
        if score < 70:
            status = "degraded"
        if score < 40:
            status = "critical"

        return SystemHealthResult(
            score=score,
            status=status,
            failed_count=failed_count,
            skipped_count=skipped_count,
            disabled_rules_count=disabled_rules_count,
            stale_rules_count=stale_rules_count,
            retry_risk_count=retry_risk_count,

            execution_health=execution_health,
            skipped_health=skipped_health,
            automation_health=automation_health,
            stale_health=stale_health,
            retry_health=retry_health,

            warnings=warnings,
            critical=critical,
            recommendations=recommendations,
        )


def save_system_health_snapshot(company_id, data):
    conn = connect()
    c = conn.cursor()
    now = datetime.now()
    now_text = now.isoformat(timespec="seconds")
    score = data.get("score", 100)
    status = data.get("status", "healthy")

    last_snapshot = c.execute("""
        SELECT score, status, created_at
        FROM system_health_snapshots
        WHERE company_id=?
        ORDER BY id DESC
        LIMIT 1
    """, (company_id,)).fetchone()

    if last_snapshot:
        should_write = (
            last_snapshot["score"] != score
            or last_snapshot["status"] != status
        )

        if not should_write:
            try:
                created_at = datetime.fromisoformat(last_snapshot["created_at"])
                should_write = (now - created_at).total_seconds() >= 300
            except Exception:
                should_write = True

        if not should_write:
            conn.close()
            return False

    c.execute("""
        INSERT INTO system_health_snapshots (
            company_id,
            score,
            status,
            failed_count,
            skipped_count,
            disabled_rules_count,
            stale_rules_count,
            retry_risk_count,
            unhealthy_rules_count,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        score,
        status,
        data.get("failed_count", 0),
        data.get("skipped_count", 0),
        data.get("disabled_rules_count", 0),
        data.get("stale_rules_count", 0),
        data.get("retry_risk_count", 0),
        data.get("unhealthy_rules_count", 0),
        now_text,
    ))

    conn.commit()
    conn.close()

    return True


def calculate_system_health(company_id):
    conn = connect()
    c = conn.cursor()

    rules = c.execute("""
        SELECT
            automation_rules.*,
            MAX(automation_events.created_at) AS last_run_at
        FROM automation_rules
        LEFT JOIN automation_events
          ON automation_events.rule_id=automation_rules.id
          AND automation_events.company_id=automation_rules.company_id
        WHERE automation_rules.company_id=?
        GROUP BY automation_rules.id
    """, (company_id,)).fetchall()

    events = c.execute("""
        SELECT *
        FROM automation_events
        WHERE company_id=?
        ORDER BY id DESC
        LIMIT 500
    """, (company_id,)).fetchall()

    conn.close()

    result = SystemHealthCalculator(rules=rules, events=events).calculate()
    data = result.to_dict()

    data["unhealthy_rules_count"] = (
        data.get("disabled_rules_count", 0)
        + data.get("stale_rules_count", 0)
        + data.get("retry_risk_count", 0)
    )

    if data["status"] == "healthy":
        data["status_title"] = "Система стабильна"
        data["status_message"] = "Движок автоматизации работает нормально."
    elif data["status"] == "warning":
        data["status_title"] = "Требуется внимание"
        data["status_message"] = "Некоторые сигналы автоматизации требуют проверки."
    elif data["status"] == "degraded":
        data["status_title"] = "Стабильность снижена"
        data["status_message"] = "Надёжность автоматизации снизилась."
    else:
        data["status_title"] = "Критичное состояние"
        data["status_message"] = "Движок автоматизации требует срочного внимания."

    save_system_health_snapshot(company_id, data)

    if data["status"] in {"degraded", "critical"}:
        create_ops_timeline_event(
            company_id=company_id,
            event_type="system_health",
            severity=data["status"],
            title="Состояние автоматизации ухудшилось",
            message=data.get("status_message", ""),
        )

    return data


def get_system_health_history(company_id, limit=30):
    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT
            score,
            status,
            failed_count,
            skipped_count,
            disabled_rules_count,
            stale_rules_count,
            retry_risk_count,
            unhealthy_rules_count,
            created_at
        FROM system_health_snapshots
        WHERE company_id=?
        ORDER BY id DESC
        LIMIT ?
    """, (
        company_id,
        limit,
    )).fetchall()

    conn.close()

    return [dict(row) for row in rows][::-1]
