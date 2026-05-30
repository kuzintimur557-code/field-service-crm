from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone


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
            critical.append(f"{failed_count} failed automation events in last 24h")

        if skipped_count:
            warnings.append(f"{skipped_count} skipped automation events in last 24h")

        if disabled_rules_count:
            warnings.append(f"{disabled_rules_count} disabled automation rules")

        if stale_rules_count:
            warnings.append(f"{stale_rules_count} stale automation rules")

        if retry_risk_count:
            critical.append(f"{retry_risk_count} events with high retry count")

        recommendations = []

        if failed_count:
            recommendations.append("Review failed automation events and inspect rule detail logs.")

        if skipped_count:
            recommendations.append("Check skipped events and retry valid skipped automations.")

        if disabled_rules_count:
            recommendations.append("Review disabled rules and re-enable business-critical automations.")

        if stale_rules_count:
            recommendations.append("Inspect stale rules that have not executed for more than 7 days.")

        if retry_risk_count:
            recommendations.append("Investigate high retry events and broken automation chains.")

        if not recommendations:
            recommendations.append("No action required. Automation system is operating normally.")

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
