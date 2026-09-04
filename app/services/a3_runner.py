from app.services.autonomous_actions import process_autonomous_actions
from app.services.decision_engine import get_decision_engine


def require_company_id(company_id):
    if not company_id:
        raise ValueError("company_id is required")


def run_a3_autonomous_cycle(company_id, triggered_by="scheduler"):
    """Build decisions first, then process the actions allowed by governance."""
    require_company_id(company_id)

    decisions = get_decision_engine(company_id, queue_actions=True)
    result = process_autonomous_actions(
        company_id=company_id,
        triggered_by=triggered_by,
    )

    return {
        "decision_count": decisions.get("count", 0),
        "queued_from_decisions": decisions.get("queued_count", 0),
        "max_actions_per_cycle": decisions.get("max_actions_per_cycle", 0),
        "pending_action_count": decisions.get("pending_action_count", 0),
        "queue_capacity_remaining": decisions.get("queue_capacity_remaining", 0),
        "result": result,
    }
