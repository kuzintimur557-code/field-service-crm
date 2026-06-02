def calculate_workflow_health(workflow):
    rule = workflow.get("rule") or workflow
    actions = workflow.get("actions") or []
    events = workflow.get("events") or []

    score = 100
    issues = []
    recommendations = []

    if not rule.get("active", 1):
        score -= 35
        issues.append("Цепочка выключена")
        recommendations.append("Проверьте, нужно ли снова включить правило.")

    if not actions:
        score -= 30
        issues.append("Нет действий")
        recommendations.append("Добавьте хотя бы одно действие в цепочку.")

    failed_events = [
        event for event in events
        if event.get("status") == "failed"
    ]

    skipped_events = [
        event for event in events
        if event.get("status") == "skipped"
    ]

    if failed_events:
        score -= min(25, len(failed_events) * 5)
        issues.append(f"Ошибок выполнения: {len(failed_events)}")
        recommendations.append("Откройте события и проверьте ошибки выполнения.")

    if skipped_events:
        score -= min(20, len(skipped_events) * 3)
        issues.append(f"Пропущенных событий: {len(skipped_events)}")
        recommendations.append("Проверьте пропущенные события и условия запуска.")

    score = max(0, min(100, score))

    status = "healthy"
    title = "Стабильно"

    if score < 85:
        status = "warning"
        title = "Требует внимания"

    if score < 70:
        status = "degraded"
        title = "Снижено"

    if score < 40:
        status = "critical"
        title = "Критично"

    if not issues:
        issues.append("Проблем не найдено")

    if not recommendations:
        recommendations.append("Действия не требуются.")

    return {
        "score": score,
        "status": status,
        "title": title,
        "issues": issues,
        "recommendations": recommendations,
    }
