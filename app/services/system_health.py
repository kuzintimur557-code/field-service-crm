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
    warnings: list[str]
    critical: list[str]
    recommendations: list[str]

    def to_dict(self):
        return asdict(self)


class SystemHealthCalculator:
    def __init__(self, rules=None, events=None):
        self.rules = rules or []
        self.events = events or []

    def calculate(self) -> SystemHealthResult:
        now = datetime.now(timezone.utc)
        since_24h = now - timedelta(hours=24)
        stale_cutoff = now - timedelta(days=7)

        failed_count = 0
        skipped_count = 0
        retry_risk_count = 0

        for event in self.events:
            status = getattr(event, "status", "") or ""
            created_at = getattr(event, "created_at", None)

            if created_at and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)

            is_recent = created_at is None or created_at >= since_24h

            if is_recent and status == "failed":
                failed_count += 1

            if is_recent and status == "skipped":
                skipped_count += 1

            retry_count = getattr(event, "retry_count", 0) or 0
            if retry_count >= 3:
                retry_risk_count += 1

        disabled_rules_count = 0
        stale_rules_count = 0

        for rule in self.rules:
            enabled = getattr(rule, "enabled", True)
            is_active = getattr(rule, "is_active", True)

            if enabled is False or is_active is False:
                disabled_rules_count += 1

            last_run_at = getattr(rule, "last_run_at", None)
            if last_run_at:
                if last_run_at.tzinfo is None:
                    last_run_at = last_run_at.replace(tzinfo=timezone.utc)
                if last_run_at < stale_cutoff:
                    stale_rules_count += 1

        penalty = 0
        penalty += min(30, failed_count * 5)
        penalty += min(20, skipped_count * 2)
        penalty += min(15, disabled_rules_count * 2)
        penalty += min(15, stale_rules_count * 2)
        penalty += min(20, retry_risk_count * 4)

        score = max(0, min(100, 100 - penalty))

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
        if score < 70:
            status = "warning"
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
            warnings=warnings,
            critical=critical,
            recommendations=recommendations,
        )
