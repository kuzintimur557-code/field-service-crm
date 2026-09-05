from threading import Lock

from app.services.autonomous_actions import process_autonomous_actions
from app.services.decision_engine import get_decision_engine


_cycle_locks = {}
_cycle_locks_guard = Lock()


def require_company_id(company_id):
    if not company_id:
        raise ValueError("company_id is required")


def _get_cycle_lock(company_id):
    with _cycle_locks_guard:
        return _cycle_locks.setdefault(int(company_id), Lock())


def run_a3_autonomous_cycle(
    company_id,
    triggered_by="scheduler",
    retry_events_handler=None,
):
    """Build decisions first, then process the actions allowed by governance."""
    require_company_id(company_id)

    cycle_lock = _get_cycle_lock(company_id)

    if not cycle_lock.acquire(blocking=False):
        return {
            "skipped": True,
            "reason": "cycle_already_running",
            "decision_count": 0,
            "queued_from_decisions": 0,
            "max_actions_per_cycle": 0,
            "pending_action_count": 0,
            "queue_capacity_remaining": 0,
            "result": {
                "processed": 0,
                "triggered_by": triggered_by,
            },
        }

    try:
        decisions = get_decision_engine(company_id, queue_actions=True)
        result = process_autonomous_actions(
            company_id=company_id,
            triggered_by=triggered_by,
            retry_events_handler=retry_events_handler,
        )

        return {
            "skipped": False,
            "decision_count": decisions.get("count", 0),
            "queued_from_decisions": decisions.get("queued_count", 0),
            "max_actions_per_cycle": decisions.get("max_actions_per_cycle", 0),
            "pending_action_count": decisions.get("pending_action_count", 0),
            "queue_capacity_remaining": decisions.get("queue_capacity_remaining", 0),
            "result": result,
        }
    finally:
        cycle_lock.release()
